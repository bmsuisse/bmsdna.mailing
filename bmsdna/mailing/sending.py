from typing import NamedTuple, Literal

from bmsdna.mailing.config import DEFAULT_SENDER
from .basicazure import acquire_token
from .message import MailMessage
from .message_io import mail_to_jsondict_graph, mail_to_jsondict_sendgrid
from .storage import save_sent_mail, save_mail_failure
import aiohttp
import json
import os
import logging

logger = logging.getLogger(__name__)

_env_var_send_method = os.getenv("MAILING_SEND_METHOD", "SENDGRID").upper()
assert _env_var_send_method in [
    "SENDGRID",
], f"Invalid value for MAILING_SEND_METHOD: {_env_var_send_method}"
SEND_METHOD: Literal["SENDGRID"] = _env_var_send_method  # type: ignore


class SendResult(NamedTuple):  # noqa: F821
    ok: bool
    status: int
    content: str | bytes
    content_type: str


async def send_mail(mail: MailMessage, http_session: aiohttp.ClientSession) -> SendResult:
    mail = await mail.assure_attachments_loaded()
    method = send_mail_using_sendgrid  # for now
    return await method(mail, http_session)


async def send_mail_using_sendgrid(m: MailMessage, http_session: aiohttp.ClientSession) -> SendResult:
    if os.getenv("IS_DEV", "0") == "1" or os.getenv("IS_TEST", "0") == "1":
        return SendResult(True, 200, "fake".encode("utf-8"), "text/plain")
    assert m.subject is not None
    assert m.body is not None
    headers = {
        "Authorization": "Bearer " + os.environ["SENDGRID_API_KEY"],
        "Content-Type": "application/json",
    }
    jsd = await mail_to_jsondict_sendgrid(m)
    rsp = await http_session.post("https://api.sendgrid.com/v3/mail/send", data=json.dumps(jsd), headers=headers)
    bcontent = await rsp.content.read()
    if rsp.ok:
        logger.info(f"Mail sent: {m.subject}", extra={"system": m.system, "entity": m.entity, "entity_id": m.entity_id, "to": m.to, "cc": m.cc, "bcc": m.bcc})
        await save_sent_mail(m)
    else:
        logger.warning(f"Mail sent: {m.subject}", extra={"system": m.system,
                                                         "status": rsp.status,
                                                         "content": bcontent.decode("utf-8"),
                                                          "entity": m.entity, "entity_id": m.entity_id, "to": m.to, "cc": m.cc, "bcc": m.bcc},
                       )
        await save_mail_failure(m, rsp.status, bcontent, rsp.content_type, json_data=json.dumps(jsd))
    return SendResult(rsp.ok, rsp.status, bcontent, rsp.content_type)


async def send_mail_using_js(m: MailMessage, http_session: aiohttp.ClientSession) -> SendResult:
    if os.getenv("IS_DEV", "0") == "1" or os.getenv("IS_TEST", "0") == "1":
        return SendResult(True, 200, "fake".encode("utf-8"), "text/plain")
    assert m.subject is not None
    assert m.body is not None
    base_url = f"https://graph.microsoft.com/v1.0/users/{m.sender or DEFAULT_SENDER}/"

    token, expiry = await acquire_token()
    headers = {
        "Authorization": "Bearer " + token,
        "Content-Type": "application/json",
    }  # see https://learn.microsoft.com/en-us/graph/api/user-sendmail?view=graph-rest-1.0&tabs=http#example-4-send-a-new-message-using-mime-format

    jsd = await mail_to_jsondict_graph(m)
    rsp = await http_session.post(base_url + "sendMail", data=json.dumps(jsd), headers=headers)
    bcontent = await rsp.content.read()
    if rsp.ok:
        await save_sent_mail(m)
    else:
        await save_mail_failure(m, rsp.status, bcontent, rsp.content_type, json_data=json.dumps(jsd))
    return SendResult(rsp.ok, rsp.status, bcontent, rsp.content_type)
