from bmsdna.mailing.config import DEFAULT_SENDER
from .message import BaseAttachment, FileAttachment, MailMessage, get_loaded_attachment_or_error
from email import generator, message_from_binary_file
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.mime.application import MIMEApplication
import mimetypes
import base64
from io import IOBase
from typing import TypeVar, cast
import logging

logger = logging.getLogger(__name__)

# see also https://www.rfc-editor.org/rfc/rfc2076


async def _create_eml_email(m: MailMessage):
    msg = MIMEMultipart()
    to_str = m.to if isinstance(m.to, str) else (", ".join(m.to) if m.to else None)

    if (not to_str or len(to_str) < 4) and (m.cc is not None or m.bcc is not None):
        to_str = DEFAULT_SENDER # azure does require a To Recipient
        assert DEFAULT_SENDER is not None
    real_to = to_str or DEFAULT_SENDER
    real_sender = m.sender or DEFAULT_SENDER
    assert real_to, "Must set a recipient or configure DEFAULT_SENDER"
    assert real_sender, "Must set a sender or configure DEFAULT_SENDER"
    msg["To"] = real_to
    msg["From"] = real_sender
    if m.cc is not None:
        msg["cc"] = m.cc if isinstance(m.cc, str) else ", ".join(m.cc)
    if m.bcc is not None:
        msg["bcc"] = m.bcc if isinstance(m.bcc, str) else ", ".join(m.bcc)
    msg["Subject"] = m.subject
    msg.attach(MIMEText(m.body, "html" if m.body_is_html else "plain"))

    if m.attachments is not None:
        for att in m.attachments:
            real_att, _ = await get_loaded_attachment_or_error(att)

            if not isinstance(real_att, FileAttachment):
                raise ValueError("Can only support file attachments in EML")
            assert isinstance(real_att.content, bytes)

            content_type, encoding = (real_att.content_type, None) or mimetypes.guess_type(real_att.filename)
            if content_type is None:
                content_type = "application/octet-stream"
            content_type_main, content_type_sub = content_type.split("/")
            if content_type_main == "image":  # pdf, excel etc
                msg_att = MIMEImage(real_att.content, content_type_sub)
            elif content_type_main == "text":  # pdf, excel etc
                msg_att = MIMEText(real_att.content.decode("utf-8"), content_type_sub)
            elif content_type_main == "application":  # pdf, excel etc
                msg_att = MIMEApplication(real_att.content, content_type_sub)
            else:  # we don't know this. octet-stream is generic
                msg_att = MIMEApplication(real_att.content)

            if real_att.content_id:
                msg_att.add_header("Content-Disposition", "inline")
                msg_att.add_header("Content-Id", real_att.content_id)
            else:
                msg_att.add_header("Content-Disposition", f'attachment; filename="{real_att.filename}"')
            msg.attach(msg_att)
    return msg


async def mail_to_base64eml(m: MailMessage):
    msg = await _create_eml_email(m)
    return base64.b64encode(msg.as_bytes())


T = TypeVar("T")


def _not_none(v: T | None) -> T:
    assert v is not None
    return v


def mail_from_eml(eml: bytes, entity: str, entity_id: str, system: str):
    import io
    from email.message import Message

    with io.BytesIO(eml) as iop:
        msg = message_from_binary_file(iop)

        payloads: list[Message] = msg.get_payload()  # type: ignore

        body_str: str = ""
        body_is_html = False
        atts: list[BaseAttachment] = []

        for item in payloads:
            if item.is_multipart():
                raise ValueError("Don't know multi part")
            content_dist = item.get_content_disposition()
            if content_dist is None:
                binary = item.get_payload(decode=True)  # type: ignore
                cnttype = item.get_content_type()
                charset = item.get_content_charset("utf-8")
                body_str = binary.decode(charset)
                body_is_html = "html" in cnttype
            elif content_dist == "attachment":
                binary: bytes = item.get_payload(decode=True)  # type: ignore
                filename = item.get_filename() or "file"
                from .attachments.static_attachment import StaticAttachment

                atts.append(StaticAttachment(binary, filename))
            elif content_dist == "inline":
                binary: bytes = item.get_payload(decode=True)  # type: ignore
                content_id = _not_none(item.get("Content-Id"))
                from .attachments.static_attachment import StaticInlineAttachment

                atts.append(StaticInlineAttachment(content=binary, content_id=content_id))
            else:
                raise ValueError(f"Cannot handle this: {content_dist}")
        sender = msg.get("From", DEFAULT_SENDER)
        assert sender is not None, "No sender found, configure DEFAULT_SENDER"
        return MailMessage(
            entity=entity,
            entity_id=entity_id,
            system=system,
            sender=sender,
            subject=_not_none(msg.get("Subject")),
            body=body_str,
            body_is_html=body_is_html,
            attachments=atts,
            bcc=[cast(str, i).strip() for i in msg.get("bcc", "").split(",") if len(i.strip()) > 0],
            cc=[cast(str, i).strip() for i in msg.get("cc", "").split(",") if len(i.strip()) > 0],
            to=_not_none(msg.get("To")),
        )


def _split_mails(mails: str) -> list[str]:
    return [m.strip() for m in mails.replace(";", ",").split(",") if m.strip()]


async def mail_to_jsondict_sendgrid(m: MailMessage):
    # see https://www.twilio.com/docs/sendgrid/api-reference/mail-send/mail-send
    tos = _split_mails(m.to) if isinstance(m.to, str) else m.to
    tos = [t.strip() for t in tos if t and "@" in t and t.strip()] if tos else []
    if len(tos) == 0 and (m.cc is not None or m.bcc is not None):
        assert DEFAULT_SENDER is not None, "No sender found, configure DEFAULT_SENDER"
        tos = [DEFAULT_SENDER]  # azure does require a To Recipient
    d = {
        "personalizations": [
            {
                "from": {
                    "email": m.sender,
                    "name": m.sender_name or m.sender,
                },
                "to": [{"email": item.strip()} for item in tos if item.strip()],
            }
        ],
        "from": {
            "email": m.sender,
            "name": m.sender_name or m.sender,
        },
        "subject": m.subject,
        "content": [{"type": "text/html" if m.body_is_html else "text/plain", "value": m.body}],
    }
    has_additional_recipients = False
    d["custom_args"] = {"system": m.system, "entity": m.entity, "entity_id": m.entity_id}
    if m.cc is not None:
        ccs = _split_mails(m.cc) if isinstance(m.cc, str) else m.cc
        d["personalizations"][0]["cc"] = [{"email": item.strip()} for item in ccs if item.strip() and item.strip() not in tos]
        has_additional_recipients = len(d["personalizations"][0]["cc"]) > 0
    if m.bcc is not None:
        bccs = _split_mails(m.bcc) if isinstance(m.bcc, str) else m.bcc
        d["personalizations"][0]["bcc"] = [{"email": item.strip()} for item in bccs if item.strip() and item.strip() not in tos]
        has_additional_recipients = has_additional_recipients or len(d["personalizations"][0]["bcc"]) > 0

    if len(d["personalizations"][0]["to"]) == 0 and has_additional_recipients:
        assert DEFAULT_SENDER is not None, "No sender found, configure DEFAULT_SENDER"
        d["personalizations"][0]["to"] = [{"email": DEFAULT_SENDER}]

    if m.attachments and len(m.attachments) > 0:
        atts = []
        for att in m.attachments:
            r_att, _ = await get_loaded_attachment_or_error(att)
            atts.append(r_att.serialize4json("sendgrid"))
        d["attachments"] = atts
    return d


async def mail_to_jsondict_graph(m: MailMessage):
    tos = _split_mails(m.to) if isinstance(m.to, str) else m.to
    tos = [t for t in tos if t and "@" in t] if tos else []
    if len(tos) == 0 and (m.cc is not None or m.bcc is not None):
        assert DEFAULT_SENDER is not None, "No sender found, configure DEFAULT_SENDER"
        tos = [DEFAULT_SENDER]  # azure does require a To Recipient
    d = {
        "subject": m.subject,
        "body": {"contentType": "Html" if m.body_is_html else "Text", "content": m.body},
        "toRecipients": [{"emailAddress": {"address": item.strip()}} for item in tos if item.strip()],
        "internetMessageHeaders": [
            {"name": "X-Entity", "value": m.entity},
            {"name": "X-Entity-Id", "value": m.entity_id},
            {"name": "X-System", "value": m.system},
        ],
    }
    if m.cc is not None:
        ccs = _split_mails(m.cc) if isinstance(m.cc, str) else m.cc
        d["ccRecipients"] = [{"emailAddress": {"address": item.strip()}} for item in ccs if item.strip()]
    if m.bcc is not None:
        bccs = _split_mails(m.bcc) if isinstance(m.bcc, str) else m.bcc
        d["bccRecipients"] = [{"emailAddress": {"address": item.strip()}} for item in bccs if item.strip()]

    if len(d["toRecipients"]) == 0 and (len(d.get("ccRecipients", [])) > 0 or len(d.get("bccRecipients", [])) > 0):
        assert DEFAULT_SENDER is not None, "No sender found, configure DEFAULT_SENDER"
        d["toRecipients"] = [{"emailAddress": {"address": DEFAULT_SENDER}}]

    if m.importance is not None:
        d["importance"] = m.importance.lower()
    if m.attachments and len(m.attachments) > 0:
        atts = []
        for att in m.attachments:
            r_att, _ = await get_loaded_attachment_or_error(att)
            atts.append(r_att.serialize4json("msgraph"))
        d["attachments"] = atts
    return {"message": d, "saveToSentItems": True}


async def write_eml_file(msg: MailMessage, out: IOBase):
    m = await _create_eml_email(msg)
    emlGenerator = generator.BytesGenerator(out)
    emlGenerator.flatten(m)


def replace_cid(msg: MailMessage, body: str):
    if 'src="cid:' in body:
        assert msg.attachments is not None
        ind = body.index('src="cid:')
        endind = body.index('"', ind + 9)
        cid = body[ind + 9 : endind]
        at = next(
            (a for a in msg.attachments if a.is_inline() and isinstance(a, FileAttachment) and a.content_id == cid)
        )
        fn, type_str, bytes = at.serialize4bytes()
        dataurl = "data:" + type_str + ";base64," + base64.b64encode(bytes).decode("ascii")
        body = body.replace('src="cid:' + cid + '"', 'src="' + dataurl + '"')
        return replace_cid(msg, body)

    return body


def get_debug_html(msg: MailMessage):
    from html import escape

    def render_line(title: str, value: str | list[str] | None):
        if value is None:
            return ""
        if isinstance(value, list):
            return "<p>" + escape(title) + ": " + ", ".join((escape(i) for i in value)) + "</p>"
        return "<p>" + escape(title) + ": " + escape(value) + "</p>"

    def render_mail(msg: MailMessage):
        html = ""
        html += "<h3>" + escape(msg.subject) + "</h3>"
        html += render_line("From", msg.sender)
        html += render_line("To", msg.to)
        html += render_line("CC", msg.cc)
        html += render_line("Bcc", msg.bcc)
        html += render_line("System", msg.system)
        html += render_line("entity", msg.entity)
        html += render_line("entity_id", msg.entity_id)
        html += render_line("Importance", msg.importance)
        if msg.attachments and any((a for a in msg.attachments if not a.is_inline())):
            html += "<br/><p>Attachments:</p><div>"
            for at in msg.attachments:
                if not at.is_inline():
                    filename, content_type, content = at.serialize4bytes()
                    data_url = f"data:{content_type};base64," + base64.b64encode(content).decode("ascii")
                    html += f'<a href="{data_url}">{escape(filename or "attachment")}</a>'
            html += "</div><br />"
        if msg.body_is_html:
            html += (
                '<br /> <br /><iframe style="min-height: 500px;width: 100%;min-width: 500px;border: 0" border=0 srcdoc="'
                + escape(replace_cid(msg, msg.body))
                + '"></iframe>'
            )
        else:
            html += "<br /> <br /><p>" + escape(msg.body) + "</p>"
        return html

    html = "<html>"
    html += "<head>"
    html += "<title>" + escape(msg.subject) + "</title>"
    html += """<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.1/dist/css/bootstrap.min.css" rel="stylesheet" integrity="sha384-4bw+/aepP/YC94hEpVNVgiZdgIC5+VKNBQNGCHeKRQN+PtmoHDEXuppvnDJzQIu9" crossorigin="anonymous">
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.1/dist/js/bootstrap.bundle.min.js" integrity="sha384-HwwvtgBNo3bZJJLYd8oVXjrBZt8cqVSpeBNS5n7C8IVInixGAoxmnlMuBnhbgrkm" crossorigin="anonymous"></script>"""
    html += "</head>"
    html += '<body style="padding: 10px">'
    html += render_mail(msg)
    html += "</body>"
    return html
