import base64
import mimetypes
import os
from typing import Any, Literal, Optional, Union, cast, Awaitable, TYPE_CHECKING
from dataclasses import dataclass
import dataclasses
import inspect
from abc import ABC, abstractmethod
import logging

import aiohttp

from bmsdna.mailing.config import DEFAULT_SENDER, DEFAULT_SENDER_NAME

if TYPE_CHECKING:
    from .sending import SendResult

logger = logging.getLogger(__name__)


class BaseAttachment(ABC):
    @property
    @abstractmethod
    def filename(self) -> str: ...

    @abstractmethod
    def get_error_message(self) -> str: ...

    @abstractmethod
    async def assure_persisted_content(self) -> int: ...

    @abstractmethod
    def serialize4json(self, flavor: Literal["msgraph", "sendgrid"]) -> dict: ...

    @abstractmethod
    def serialize4bytes(self) -> tuple[str | None, str, bytes]: ...

    @abstractmethod
    def is_inline(self) -> bool: ...


def _remove_none(d: dict) -> dict:
    return {k: v for k, v in d.items() if v is not None}


class FileAttachment(BaseAttachment):
    _filename: str
    # content: Union[bytes, Callable[["FileAttachment"], bytes], Callable[["FileAttachment"], Awaitable[bytes]]]
    content: bytes | None = None
    content_id: Optional[str] = None  # use for in-mail references
    content_type: Optional[str] = None

    @property
    def filename(self):
        return self._filename

    def get_error_message(self) -> str:
        return f"Error loading attachment {self.filename}"

    def is_inline(self) -> bool:
        return self.content_id is not None

    @abstractmethod
    def get_content(self) -> bytes | Awaitable[bytes]: ...

    def serialize4json(self, flavor: Literal["msgraph", "sendgrid"]) -> dict:
        content_type = self.content_type or mimetypes.guess_type(self.filename)[0]
        assert isinstance(self.content, bytes)
        b64_content = base64.b64encode(self.content).decode("ascii")
        if flavor == "msgraph":
            return _remove_none(
                {
                    "@odata.type": "#microsoft.graph.fileAttachment",
                    "name": self.filename,
                    "isInline": True if self.content_id else None,
                    "contentId": self.content_id,
                    "contentType": content_type,
                    "contentBytes": b64_content,
                }
            )
        elif flavor == "sendgrid":
            return _remove_none(
                {
                    "filename": self.filename,
                    "content": b64_content,
                    "type": content_type,
                    "disposition": "attachment" if not self.content_id else "inline",
                    "content_id": self.content_id,
                }
            )
        else:
            raise ValueError(f"Unsupported flavor {flavor}")

    def serialize4bytes(self) -> tuple[str | None, str, bytes]:
        content_type = self.content_type or mimetypes.guess_type(self.filename)[0]
        assert isinstance(self.content, bytes)
        return (self.filename, content_type or "application/octet-stream", self.content)

    async def assure_persisted_content(self) -> int:
        if isinstance(self.content, bytes):
            return len(self.content)
        real_content = self.get_content()
        if inspect.isawaitable(real_content):
            real_content2 = cast(bytes, await real_content)
        else:
            real_content2 = cast(bytes, real_content)
        assert isinstance(real_content2, bytes)
        self.content = real_content2
        return len(self.content)


async def get_loaded_attachment_or_error(att: BaseAttachment) -> tuple[BaseAttachment, bool]:
    real_att = att
    has_error = False
    try:
        await att.assure_persisted_content()
    except Exception as err:
        from bmsdna.mailing.attachments.static_attachment import StaticAttachment

        msg = att.get_error_message()
        real_att = StaticAttachment(msg.encode("utf-8"), f"error_{att.filename}.txt")
        logger.error(f"Error loading attachment {att.filename}: {err}")
        has_error = True
    return real_att, has_error


# see also https://www.rfc-editor.org/rfc/rfc2076
@dataclass(frozen=True)
class MailMessage:
    entity: str
    entity_id: str
    system: str

    subject: str
    body: str
    body_is_html: bool
    to: Union[list[str], str]
    email_id: str | int | None = None
    sender: str | None = DEFAULT_SENDER
    sender_name: str | None = DEFAULT_SENDER_NAME
    cc: Union[list[str], str, None] = None
    bcc: Union[list[str], str, None] = None
    attachments: Union[list[BaseAttachment], None] = None
    importance: Optional[Literal["High", "normal", "low"]] = "normal"

    extra_infos: dict[str, Any] | None = None

    send_method: Optional[Literal["SENDGRID"]] = None

    error_receiver: Optional[str] = None

    async def assure_attachments_loaded(self) -> "MailMessage":
        if not self.attachments:
            return self
        new_atts: list[BaseAttachment] = []
        has_error = False
        for att in self.attachments:
            att2, has_error2 = await get_loaded_attachment_or_error(att)
            new_atts.append(att2)
            has_error = has_error or has_error2
        if has_error and self.error_receiver is not None:
            return dataclasses.replace(self, attachments=new_atts, to=self.error_receiver, bcc=None, cc=None)

        return dataclasses.replace(self, attachments=new_atts)

    async def send(self, session: aiohttp.ClientSession) -> "SendResult":
        from .sending import send_mail

        return await send_mail(self, session)


def mail_message_from_json(json_str: str):
    import json

    d = json.loads(json_str)
    return MailMessage(**d)
