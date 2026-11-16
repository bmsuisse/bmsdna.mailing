import time

import pytest
from azure.core.credentials import AccessToken

from bmsdna.mailing.basicazure import acquire_token
from bmsdna.mailing.config import (
    get_async_default_credential,
    get_default_credential,
    set_default_credential,
    use_credential,
)


class FakeCredential:
    def __init__(self, token: str) -> None:
        self.token = token

    def get_token(self, *scopes, **kwargs) -> AccessToken:
        return AccessToken(self.token, int(time.time()) + 3600)


class FakeAsyncCredential:
    def __init__(self, token: str) -> None:
        self.token = token

    async def get_token(self, *scopes, **kwargs) -> AccessToken:
        return AccessToken(self.token, int(time.time()) + 3600)

    async def close(self) -> None:
        pass


@pytest.fixture(autouse=True)
def reset_override():
    set_default_credential()
    yield
    set_default_credential()


def test_global_override_sync():
    cred = FakeCredential("a")
    set_default_credential(cred)  # type: ignore
    assert get_default_credential() is cred


@pytest.mark.asyncio
async def test_sync_override_is_adapted_for_async():
    set_default_credential(FakeCredential("a"))  # type: ignore
    tk = await get_async_default_credential().get_token("scope")
    assert tk.token == "a"
    token, _ = await acquire_token()
    assert token == "a"


@pytest.mark.asyncio
async def test_async_only_override():
    set_default_credential(async_credential=FakeAsyncCredential("b"))  # type: ignore
    token, _ = await acquire_token(prefix="POWERBI", scopes="x/.default")
    assert token == "b"
    with pytest.raises(ValueError):
        get_default_credential()


def test_scoped_override_wins_and_is_restored():
    outer = FakeCredential("outer")
    inner = FakeCredential("inner")
    set_default_credential(outer)  # type: ignore
    with use_credential(inner):  # type: ignore
        assert get_default_credential() is inner
    assert get_default_credential() is outer


def test_reset_restores_default():
    set_default_credential(FakeCredential("a"))  # type: ignore
    set_default_credential()
    assert not isinstance(get_default_credential(), FakeCredential)
