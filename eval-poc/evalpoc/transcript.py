"""Parse transcripts in the '[L001] [00:00:00] Speaker: text' format."""
import re
from dataclasses import dataclass
from pathlib import Path

LINE_RE = re.compile(r"^\[L(\d+)\] \[(\d{2}:\d{2}:\d{2})\] ([^:]+): (.*)$")
META_RE = re.compile(r"^#\s*(\w+):\s*(.*)$")


@dataclass
class Line:
    num: int
    time: str
    speaker: str
    text: str


@dataclass
class Transcript:
    id: str
    meta: dict
    lines: dict  # line number -> Line
    raw: str

    @property
    def first_line(self) -> int:
        return min(self.lines)

    @property
    def last_line(self) -> int:
        return max(self.lines)

    def text(self, start: int, end: int) -> str:
        return " ".join(self.lines[n].text for n in range(start, end + 1) if n in self.lines)

    @property
    def full_text(self) -> str:
        return self.text(self.first_line, self.last_line)

    @property
    def speaker_names(self) -> set:
        return {l.speaker for l in self.lines.values()}


def load_transcript(path: Path) -> Transcript:
    raw = Path(path).read_text(encoding="utf-8")
    meta, lines = {}, {}
    for row in raw.splitlines():
        if m := META_RE.match(row):
            meta[m.group(1)] = m.group(2).strip()
        elif m := LINE_RE.match(row):
            n = int(m.group(1))
            lines[n] = Line(n, m.group(2), m.group(3).strip(), m.group(4).strip())
    if "duration_seconds" in meta:
        meta["duration_seconds"] = int(meta["duration_seconds"])
    return Transcript(id=meta.get("transcript_id", Path(path).stem), meta=meta, lines=lines, raw=raw)
