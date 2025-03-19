import aiohttp
from .persistance import PersistanceDB



class GenerationContext:
    _http_sessions: dict[str, aiohttp.ClientSession] = dict()

    db: PersistanceDB

    def __init__(self, read_only: bool = False):
        self.db = PersistanceDB(read_only=read_only)
        self.caption_dict = None

    async def __aenter__(self, *args, **kwargs):
        await self.db.__aenter__(args, kwargs)
        return self

    def get_http_session(self, base_url: str | None = None):
        key = base_url.lower() if base_url else "__default__"
        res = self._http_sessions.get(key, None)
        if res:
            if not res.closed:
                return res
        res = aiohttp.ClientSession(base_url)
        self._http_sessions[key] = res
        return res


    async def __aexit__(self, *args, **kwargs):
        await self.db.__aexit__(*args, **kwargs)
        for _, v in self._http_sessions.items():
            await v.__aexit__(*args, **kwargs)
        self._http_sessions = {}
