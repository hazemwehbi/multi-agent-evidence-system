import hashlib
import re
from collections.abc import Callable
from pathlib import Path

from app.models.contracts import Contract, EvidenceRef, Passage, SourceDocument

MAX_BYTES = 256 * 1024
MAX_PASSAGE = 1_000
HEADING = re.compile(r"(?m)^ {0,3}#{1,6}[ \t]+([^\r\n]+)")
BLOCK = re.compile(r"\S[\s\S]*?(?=\r?\n[ \t]*\r?\n|\Z)")


class IngestionError(ValueError):
    pass


class ParsedDocument(Contract):
    source: SourceDocument
    media_type: str
    passages: tuple[Passage, ...]


def _decode_utf8(data: bytes) -> str:
    return data.decode("utf-8")


def _spans(text: str, start: int, end: int):
    for block in BLOCK.finditer(text, start, end):
        cursor = block.start()
        while cursor < block.end():
            stop = min(cursor + MAX_PASSAGE, block.end())
            if stop < block.end() and not text[stop].isspace():
                boundary = text.rfind(" ", cursor + 1, stop)
                if boundary > cursor:
                    stop = boundary
            excerpt = text[cursor:stop]
            if excerpt.strip():
                yield cursor, stop
            cursor = stop


class DocumentIngestor:
    """Dispatch file formats before constructing stable, source-relative spans."""

    def __init__(self) -> None:
        self._formats: dict[str, tuple[str, Callable[[bytes], str], bool]] = {
            ".txt": ("text/plain", _decode_utf8, False),
            ".md": ("text/markdown", _decode_utf8, True),
        }

    def read(self, path: Path) -> ParsedDocument:
        try:
            with path.open("rb") as stream:
                data = stream.read(MAX_BYTES + 1)
        except OSError as exc:
            raise IngestionError(f"Could not read {path.name}") from exc
        return self.parse(path.name, data)

    def parse(self, name: str, data: bytes) -> ParsedDocument:
        suffix = Path(name).suffix.lower()
        if suffix not in self._formats:
            raise IngestionError(f"{name}: expected a .txt or .md file")
        if len(data) > MAX_BYTES:
            raise IngestionError(f"{name}: file exceeds {MAX_BYTES} bytes")
        media_type, decode, markdown = self._formats[suffix]
        try:
            original = decode(data)
        except UnicodeDecodeError as exc:
            raise IngestionError(f"{name}: invalid UTF-8") from exc
        if not original.removeprefix("\ufeff").strip() or "\0" in original:
            raise IngestionError(f"{name}: empty or contains NUL characters")
        identity = hashlib.sha256(name.encode("utf-8") + b"\0" + data).hexdigest()
        source = SourceDocument(source_id=identity, document_name=name, text=original)
        boundaries = [(0, None)]
        if markdown:
            boundaries.extend(
                (match.start(), match.group(1).strip().rstrip("#").rstrip() or None)
                for match in HEADING.finditer(original)
            )
        passages = []
        for index, (start, section) in enumerate(boundaries):
            end = boundaries[index + 1][0] if index + 1 < len(boundaries) else len(original)
            for left, right in _spans(original, start, end):
                passages.append(Passage(
                    ref=EvidenceRef(source_id=identity, passage_id=f"{left}-{right}"),
                    text=original[left:right], start=left, end=right, section=section,
                ))
        return ParsedDocument(source=source, media_type=media_type, passages=tuple(passages))
