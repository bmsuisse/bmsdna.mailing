from functools import lru_cache
import os
from typing import Any, Optional
from azure.core.credentials import TokenCredential, AccessToken
from azure.core.credentials_async import AsyncTokenCredential

DEFAULT_SENDER = os.getenv("MAIL_DEFAULT_SENDER")
DEFAULT_SENDER_NAME:str | None = os.getenv("MAIL_DEFAULT_SENDER_NAME", DEFAULT_SENDER)

class TokenAdapter(AsyncTokenCredential):
    def __init__(self, sync_cred: TokenCredential):
        super().__init__()
        self.sync_cred = sync_cred

    
    async def get_token(
        self,
        *args,
        **kwargs: Any,
    ) -> AccessToken:
        """Request an access token for `scopes`.

        :param str scopes: The type of access needed.

        :keyword str claims: Additional claims required in the token, such as those returned in a resource
            provider's claims challenge following an authorization failure.
        :keyword str tenant_id: Optional tenant to include in the token request.
        :keyword bool enable_cae: Indicates whether to enable Continuous Access Evaluation (CAE) for the requested
            token. Defaults to False.

        :rtype: AccessToken
        :return: An AccessToken instance containing the token string and its expiration time in Unix time.
        """
        return self.sync_cred.get_token(*args, **kwargs)

    async def close(self) -> None:
        pass

    async def __aexit__(
        self,
        *args,
        **kwargs
    ) -> None:
        pass

def get_async_default_credential() -> AsyncTokenCredential:
    if cred := os.getenv("USE_DR_SERVICE_CREDENTIAL"):
        from databricks.sdk.runtime import dbutils
        
        return  TokenAdapter(dbutils.credentials.getServiceCredentialsProvider(cred)) # type: ignore
    else:
        
        from azure.identity.aio import DefaultAzureCredential
        return DefaultAzureCredential()

@lru_cache(1)
def get_default_credential():
    if cred := os.getenv("USE_DR_SERVICE_CREDENTIAL"):
        from databricks.sdk.runtime import dbutils
        return dbutils.credentials.getServiceCredentialsProvider(cred) # type: ignore
    else:
        
        from azure.identity import DefaultAzureCredential
        return DefaultAzureCredential()
    
