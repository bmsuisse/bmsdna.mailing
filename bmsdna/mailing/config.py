from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from functools import lru_cache
import os
from typing import Any, Iterator, Optional
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

@dataclass(frozen=True)
class CredentialOverride:
    sync: Optional[TokenCredential]
    # derived from `sync` via TokenAdapter if not given explicitly
    async_: Optional[AsyncTokenCredential]


_global_override: Optional[CredentialOverride] = None
_scoped_override: ContextVar[Optional[CredentialOverride]] = ContextVar("bmsdna_mailing_credential", default=None)


def _make_override(
    credential: Optional[TokenCredential], async_credential: Optional[AsyncTokenCredential]
) -> Optional[CredentialOverride]:
    if credential is None and async_credential is None:
        return None
    if async_credential is None and credential is not None:
        async_credential = TokenAdapter(credential)
    return CredentialOverride(credential, async_credential)


def set_default_credential(
    credential: Optional[TokenCredential] = None, *, async_credential: Optional[AsyncTokenCredential] = None
) -> None:
    """Replace the credential used for everything this library talks to (blob/table storage, Graph, Power BI),
    process-wide. Pass nothing to restore the default (DefaultAzureCredential / Databricks service credential).

    `credential` is used for sync clients, and for async ones too unless `async_credential` is given.
    With only `async_credential`, the sync code paths (table storage) raise. The caller owns the credential
    and is responsible for closing it.
    """
    global _global_override
    _global_override = _make_override(credential, async_credential)


@contextmanager
def use_credential(
    credential: Optional[TokenCredential] = None, *, async_credential: Optional[AsyncTokenCredential] = None
) -> Iterator[None]:
    """Like `set_default_credential`, but only for the current context (thread / asyncio task) and
    only within the `with` block. Takes precedence over `set_default_credential`."""
    token = _scoped_override.set(_make_override(credential, async_credential))
    try:
        yield
    finally:
        _scoped_override.reset(token)


def get_credential_override() -> Optional[CredentialOverride]:
    return _scoped_override.get() or _global_override


def get_async_default_credential() -> AsyncTokenCredential:
    if (ov := get_credential_override()) is not None:
        assert ov.async_ is not None
        return ov.async_
    if cred := os.getenv("USE_DR_SERVICE_CREDENTIAL"):
        from databricks.sdk.runtime import dbutils

        return TokenAdapter(dbutils.credentials.getServiceCredentialsProvider(cred))  # type: ignore
    else:
        from azure.identity.aio import DefaultAzureCredential

        return DefaultAzureCredential()


@lru_cache(1)
def _get_env_default_credential():
    if cred := os.getenv("USE_DR_SERVICE_CREDENTIAL"):
        from databricks.sdk.runtime import dbutils

        return dbutils.credentials.getServiceCredentialsProvider(cred)  # type: ignore
    else:
        from azure.identity import DefaultAzureCredential

        return DefaultAzureCredential()


def get_default_credential():
    if (ov := get_credential_override()) is not None:
        if ov.sync is None:
            raise ValueError(
                "Only an async credential was provided, but a synchronous one is required here. "
                "Pass a sync TokenCredential to set_default_credential/use_credential."
            )
        return ov.sync
    return _get_env_default_credential()
