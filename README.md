# Library for generating and scheduling Email

It allows to send emails using SendGrid or Microsoft Graph.

It also contains certain utils to generate Attachments, eg using Power BI

It does store logs about sent mails in Azure Table Storage to avoid duplicate mails.

```python

from bmsdna.mailing.attachments.static_attachment import StaticAttachment
from bmsdna.mailing.registry import GenerationInfo, daily_mail, TZONE
from datetime import datetime
from bmsdna.mailing import MailMessage
from typing import List
from datetime import time
import polars as pl
from mail_utils import get_unique_id_from_values


@daily_mail(
    "tester",
    "test_mail",
    day_time=time(6, 0, tzinfo=TZONE),
    start_date=datetime(2025, 3, 16, 6, 0, tzinfo=TZONE),
    retry_on_empty_send=False,
)
async def generate_mail(info: GenerationInfo) -> List[MailMessage]:
    return [
        MailMessage(
            entity=info.mail_name,
            subject="Test Mail",
            body="Test Mail",
            to="some_email@other.ch",
            sender="thisisasender@thing.ch",
            attachments=[StaticAttachment(b"Hello World", "test.txt")],
            system=info.system,
            entity_id=get_unique_id_from_values( # if this one is already sent in sendgrid, won't be sent again
                {
                    "mail_name": info.mail_name,
                    "system": info.system,
                    "date": datetime.now().strftime("%Y-%m-%d"),
                }
            ),
            body_is_html=False,
        )
    ]

```


## Using your own identity

By default, Azure Storage and Graph / Power BI are accessed using `DefaultAzureCredential` (or the Databricks service credential if `USE_DR_SERVICE_CREDENTIAL` is set). To use a different identity, e.g. one of your own caller, override it:

```python
from azure.identity import ClientSecretCredential
from bmsdna.mailing.config import set_default_credential, use_credential

# process-wide
set_default_credential(ClientSecretCredential(tenant_id, client_id, client_secret))

# or only inside a block (per thread / asyncio task), takes precedence over the process-wide one
with use_credential(my_credential):
    await run_jobs()
```

A sync `TokenCredential` is used for sync and (wrapped) async clients. You may additionally pass `async_credential=` for a native async one. You own the credential's lifecycle. Call `set_default_credential()` without arguments to reset.
