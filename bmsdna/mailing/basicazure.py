import aiohttp
import os
from azure.identity.aio import ManagedIdentityCredential, ClientSecretCredential
from azure.identity import InteractiveBrowserCredential
from typing import Union
from datetime import datetime, timezone

import logging

logger = logging.getLogger(__name__)

GRAPH_API_SCOPE = "https://graph.microsoft.com/.default"
POWERBI_API_SCOPE = "https://analysis.windows.net/powerbi/api/.default"


async def acquire_token(*, prefix="MAILER", scopes: Union[tuple[str], str, None] = None):
    """
    Acquire token via MSAL
    """
    prefix = prefix.upper()
    client_id = os.getenv(f"{prefix}_CLIENT_ID", None)
    client_secret = os.getenv(f"{prefix}_CLIENT_SECRET", None)
    cred: Union[ManagedIdentityCredential, ClientSecretCredential]
    if scopes is None:
        scopes = (GRAPH_API_SCOPE,)
    elif isinstance(scopes, str):
        scopes = (scopes,)
    assert scopes is not None

    if not client_id:
        if os.getenv("IS_DEV", "0") == "1":
            scred = InteractiveBrowserCredential()
            tk = scred.get_token(*scopes)
            return (tk.token, datetime.fromtimestamp(tk.expires_on, tz=timezone.utc))
        cred = ManagedIdentityCredential()
    elif not client_secret:
        cred = ManagedIdentityCredential(client_id=client_id)
    else:
        tenant_id = os.getenv("TENANT_ID", os.getenv("AZURE_TENANT_ID"))
        assert tenant_id, "AZURE_TENANT_ID must be set"
        cred = ClientSecretCredential(
            tenant_id,
            client_id=client_id,
            client_secret=client_secret,
        )
    async with cred:
        tk = await cred.get_token(*scopes)
        return (tk.token, datetime.fromtimestamp(tk.expires_on, tz=timezone.utc))


async def get_paged_request_data(session: aiohttp.ClientSession, headers: dict, starturl: str, pagesize=900):
    starturl_with_top = starturl + ("&" if "?" in starturl else "?") + "$top=" + str(pagesize)
    url = starturl_with_top  # f"https://api.powerbi.com/v1.0/myorg/groups/{grpid}/users?$top=900"  # paging does not seem to be supported very well
    skip = 0
    total_items = -1
    while url is not None:
        async with session.get(url, headers=headers) as user_dt:
            if not user_dt.ok:
                logger.error(f"Failure calling {url}: \r\n" + (await user_dt.text()))
                user_dt.raise_for_status()
            users: dict = await user_dt.json()
            dtlist = users["value"]
            nrusers = len(dtlist)
            yield dtlist
            url = None
            if "@odata.nextLink" in users:
                url = users["@odata.nextLink"]
            elif "@odata.count" in users:
                total_items = users["@odata.count"]
            if total_items > (skip + nrusers) and url is None:
                skip = skip + pagesize
                url = starturl_with_top + "&$skip=" + str(skip)
