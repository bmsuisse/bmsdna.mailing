from email import message_from_file
from email.message import Message

with open("out/file.eml") as f:
    msg = message_from_file(f)

for name, t in msg.items():
    print(name)
    print(t)

payloads: list[Message] = msg.get_payload()  # type: ignore
for item in payloads:
    if item.is_multipart():
        raise ValueError("Don't know that one")
    content_dist = item.get_content_disposition()
    if content_dist is None:
        binary = item.get_payload(decode=True)  # type: ignore
        cnttype = item.get_content_type()
        charset = item.get_content_charset("utf-8")
        strvl = binary.decode(charset)
        print(strvl)
    elif content_dist == "attachment":
        binary: bytes = item.get_payload(decode=True)[:10]  # type: ignore
        print(binary)
    elif content_dist == "inline":
        # well, how to handle that?
        print(item.get_payload(decode=True)[:10])  # type: ignore
