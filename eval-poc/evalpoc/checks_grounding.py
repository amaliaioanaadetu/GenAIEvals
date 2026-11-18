"""Grounding checks: is everything in the output actually in the transcript?

These need no gold labels, so they also work on live production output.
"""
from rapidfuzz import fuzz

from .results import EvalResult
from .textutil import normalize, numbers, proper_nouns
from .transcript import Transcript

QUOTE_THRESHOLD = 95   # quotes must be (almost) verbatim
ENTITY_THRESHOLD = 90  # names may vary slightly ("St Brigid's" vs "St. Brigid's")


def _segment_text(out: dict, tr: Transcript, segment_id: str) -> str:
    for s in out.get("segments", []):
        if s.get("segment_id") == segment_id:
            return tr.text(s.get("start_line", 0), s.get("end_line", -1))
    return ""


def check_quotes(out: dict, tr: Transcript) -> list:
    res = []
    speakers = {s.get("speaker_id"): s.get("name") for s in out.get("speakers", [])}
    for q in out.get("quotes", []):
        ref = f"quote:{q.get('quote_id')}"
        line = tr.lines.get(q.get("line"))
        if line is None:
            res.append(EvalResult("quote_verbatim", tr.id, ref, False, f"cited line L{q.get('line')} does not exist"))
            continue
        quote, source = normalize(q.get("text", "")), normalize(line.text)
        score = 100.0 if quote in source else fuzz.partial_ratio(quote, source)
        res.append(EvalResult("quote_verbatim", tr.id, ref, score >= QUOTE_THRESHOLD,
                              "verbatim" if score == 100 else f"only {score:.0f}% match with L{line.num}: {line.text!r}",
                              score=score / 100))
        claimed = speakers.get(q.get("speaker_id"))
        res.append(EvalResult("quote_speaker", tr.id, ref, claimed == line.speaker,
                              f"attributed to {claimed!r}, L{line.num} is spoken by {line.speaker!r}"))
    return res


def check_entities(out: dict, tr: Transcript) -> list:
    res = []
    full = normalize(tr.full_text)
    for e in out.get("events", []):
        missing = [ent["name"] for ent in e.get("entities", [])
                   if fuzz.partial_ratio(normalize(ent.get("name", "")), full) < ENTITY_THRESHOLD]
        res.append(EvalResult("entity_grounding", tr.id, f"event:{e.get('event_id')}", not missing,
                              f"not found in transcript: {missing}" if missing else "all entities found"))
    return res


def check_figures(out: dict, tr: Transcript) -> list:
    res = []
    for e in out.get("events", []):
        source_nums = numbers(_segment_text(out, tr, e.get("segment_id")))
        bad = [f["value"] for f in e.get("figures", []) if not numbers(f.get("value", "")) <= source_nums]
        res.append(EvalResult("figure_grounding", tr.id, f"event:{e.get('event_id')}", not bad,
                              f"figures not in segment: {bad}" if bad else "all figures found in segment"))
    return res


def _text_grounding(text: str, scope_text: str, tr: Transcript, ref: str) -> EvalResult:
    """Cheap hallucination screen: new numbers or names that the source never mentions."""
    new_nums = sorted(numbers(text) - numbers(scope_text))
    new_names = sorted(n for n in proper_nouns(text) if n not in tr.full_text)
    problems = []
    if new_nums:
        problems.append(f"numbers not in source: {new_nums}")
    if new_names:
        problems.append(f"names not in transcript: {new_names}")
    return EvalResult("text_grounding", tr.id, ref, not problems, "; ".join(problems) or "no unsupported numbers or names")


def check_text(out: dict, tr: Transcript) -> list:
    res = []
    for s in out.get("segments", []):
        scope = tr.text(s.get("start_line", 0), s.get("end_line", -1))
        res.append(_text_grounding(s.get("summary", ""), scope, tr, f"segment:{s.get('segment_id')}"))
    for e in out.get("events", []):
        scope = _segment_text(out, tr, e.get("segment_id"))
        res.append(_text_grounding(e.get("description", ""), scope, tr, f"event:{e.get('event_id')}"))
    return res


ALL = [check_quotes, check_entities, check_figures, check_text]
