from pathlib import Path
from ..message import FileAttachment


class StaticAttachment(FileAttachment):
    def __init__(self, content: bytes | Path, filename: str) -> None:
        super().__init__()
        if isinstance(content, Path):
            content = content.read_bytes()
        self.content = content
        self._filename = filename

    def get_content(self):
        assert self.content is not None
        return self.content


class StaticInlineAttachment(FileAttachment):
    def __init__(self, *, content: bytes | Path, content_id: str) -> None:
        super().__init__()
        if isinstance(content, Path):
            self.content = content.read_bytes()
        else:
            assert isinstance(content, bytes)
            self.content = content
        self.content_id = content_id
        self._filename = "inline_" + content_id

    async def get_content(self) -> bytes:
        assert self.content is not None
        return self.content
