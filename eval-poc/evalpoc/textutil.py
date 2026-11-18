"""Small text helpers used by the deterministic checks."""
import re
import unicodedata

NUM_RE = re.compile(r"\d+(?:[.,]\d+)*")
PROPER_RE = re.compile(r"\b([A-Z][a-zA-Z]+)(?:'s)?\b")
SENT_SPLIT = re.compile(r"(?<=[.!?;:])\s+")

# Capitalised words that are fine even if the transcript doesn't contain them.
ALLOWED_CAPS = {
    "January", "February", "March", "April", "May", "June", "July", "August", "September",
    "October", "November", "December", "Monday", "Tuesday", "Wednesday", "Thursday",
    "Friday", "Saturday", "Sunday", "I",
}


def normalize(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", '"').replace("\u201d", '"')
    s = re.sub(r"[^\w\s'.%-]", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def numbers(s: str) -> set:
    """Numeric tokens, with thousands separators removed ('4,000' -> '4000')."""
    out = set()
    for tok in NUM_RE.findall(s):
        tok = tok.rstrip(".,")
        if re.fullmatch(r"\d{1,3}(,\d{3})+", tok):
            tok = tok.replace(",", "")
        out.add(tok)
    return out


def proper_nouns(s: str) -> set:
    """Capitalised words that are not the first word of a sentence."""
    found = set()
    for sentence in SENT_SPLIT.split(s):
        words = list(PROPER_RE.finditer(sentence))
        for m in words:
            if m.start() == 0 or sentence[: m.start()].strip() in ('"', "'", "("):
                continue
            if m.group(1) not in ALLOWED_CAPS:
                found.add(m.group(1))
    return found
