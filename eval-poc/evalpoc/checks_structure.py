"""Structural checks: schema, metadata, speaker list, segment layout, cross-references.

None of these need gold labels, so they can run on every production output.
"""
import json
from functools import lru_cache

from jsonschema import Draft202012Validator

from .paths import SCHEMA
from .results import EvalResult
from .transcript import Transcript


@lru_cache(maxsize=1)
def _validator():
    return Draft202012Validator(json.loads(SCHEMA.read_text()))


def _path_to_ref(out: dict, path: list) -> str:
    """Turn a JSON-schema error path into the most specific item ref, e.g.
    ['segments', 2, 'tone'] -> 'segment:SEG-03' and
    ['segments', 1, 'events', 0, 'event_type'] -> 'event:EVT-02'."""
    id_keys = {"segments": ("segment", "segment_id"), "events": ("event", "event_id"),
               "quotes": ("quote", "quote_id"), "speakers": ("speaker", "speaker_id")}
    ref, node = None, out
    for i, step in enumerate(path):
        try:
            child = node[step]
        except (IndexError, KeyError, TypeError):
            break
        if isinstance(step, int) and i > 0 and path[i - 1] in id_keys:
            prefix, key = id_keys[path[i - 1]]
            ref = f"{prefix}:{child.get(key, step) if isinstance(child, dict) else step}"
        node = child
    return ref or ("output" if not path else str(path[0]))


def check_schema(out: dict, tr: Transcript) -> list:
    errors = list(_validator().iter_errors(out))
    if not errors:
        return [EvalResult("schema_valid", tr.id, "output", True, "Valid against schema")]
    return [
        EvalResult("schema_valid", tr.id, _path_to_ref(out, list(e.absolute_path)), False,
                   f"{'/'.join(map(str, e.absolute_path)) or '(root)'}: {e.message}")
        for e in errors
    ]


def check_header(out: dict, tr: Transcript) -> list:
    res = []
    actual = out.get("transcript_id")
    res.append(EvalResult("header_fields", tr.id, "transcript_id", actual == tr.meta.get("transcript_id"),
                          f"transcript_id is {actual!r}, transcript says {tr.meta.get('transcript_id')!r}"))
    b = out.get("broadcast") or {}
    for field in ("show_name", "broadcast_date", "duration_seconds", "language"):
        expected, got = tr.meta.get(field), b.get(field)
        res.append(EvalResult("header_fields", tr.id, f"broadcast.{field}", got == expected,
                              f"{field} is {got!r}, transcript says {expected!r}"))
    return res


def check_speakers(out: dict, tr: Transcript) -> list:
    res = []
    listed = {s.get("name") for s in out.get("speakers", [])}
    for s in out.get("speakers", []):
        ok = s.get("name") in tr.speaker_names
        res.append(EvalResult("speaker_labels", tr.id, f"speaker:{s.get('speaker_id')}", ok,
                              f"{s.get('name')!r} {'appears' if ok else 'does not appear'} as a speaker label"))
    for name in sorted(tr.speaker_names - listed):
        res.append(EvalResult("speaker_labels", tr.id, f"missing_speaker:{name}", False,
                              f"Transcript speaker {name!r} is missing from the speakers list"))
    return res


def check_segments(out: dict, tr: Transcript) -> list:
    res = []
    segs = sorted(out.get("segments", []), key=lambda s: s.get("start_line", 0))
    expected_start = tr.first_line
    for s in segs:
        sid, start, end = s.get("segment_id"), s.get("start_line"), s.get("end_line")
        problems = []
        if start is None or end is None:
            problems.append("missing line range")
        else:
            if end < start:
                problems.append(f"ends (L{end}) before it starts (L{start})")
            if start > expected_start:
                problems.append(f"gap: lines L{expected_start}-L{start - 1} are not in any segment")
            elif start < expected_start:
                problems.append(f"overlaps previous segment (starts L{start}, expected L{expected_start})")
            expected_start = max(expected_start, (end or start) + 1)
        res.append(EvalResult("segment_coverage", tr.id, f"segment:{sid}", not problems,
                              "; ".join(problems) or f"L{start}-L{end} contiguous"))

        line = tr.lines.get(start)
        ok = line is not None and s.get("start_time") == line.time
        res.append(EvalResult("segment_timestamps", tr.id, f"segment:{sid}", ok,
                              f"start_time {s.get('start_time')!r}, line L{start} is at "
                              f"{line.time if line else 'n/a'}"))
    if segs and expected_start <= tr.last_line:
        res.append(EvalResult("segment_coverage", tr.id, "segment:end", False,
                              f"lines L{expected_start}-L{tr.last_line} at the end are not in any segment"))
    return res


def check_references(out: dict, tr: Transcript) -> list:
    res = []
    segs = {s.get("segment_id"): s for s in out.get("segments", [])}
    speakers = {s.get("speaker_id") for s in out.get("speakers", [])}

    for e in out.get("events", []):
        problems = []
        seg = segs.get(e.get("segment_id"))
        ev = e.get("evidence") or {}
        es, ee = ev.get("start_line"), ev.get("end_line")
        if seg is None:
            problems.append(f"segment {e.get('segment_id')!r} does not exist")
        if es is None or ee is None or es > ee or es not in tr.lines or ee not in tr.lines:
            problems.append(f"evidence L{es}-L{ee} is not a valid line range")
        elif seg and not (seg["start_line"] <= es and ee <= seg["end_line"]):
            problems.append(f"evidence L{es}-L{ee} lies outside its segment "
                            f"(L{seg['start_line']}-L{seg['end_line']})")
        res.append(EvalResult("references", tr.id, f"event:{e.get('event_id')}", not problems,
                              "; ".join(problems) or "segment and evidence consistent"))

    for q in out.get("quotes", []):
        problems = []
        seg = segs.get(q.get("segment_id"))
        if seg is None:
            problems.append(f"segment {q.get('segment_id')!r} does not exist")
        elif not (seg["start_line"] <= q.get("line", -1) <= seg["end_line"]):
            problems.append(f"line L{q.get('line')} is outside its segment")
        if q.get("speaker_id") not in speakers:
            problems.append(f"speaker {q.get('speaker_id')!r} is not in the speakers list")
        res.append(EvalResult("references", tr.id, f"quote:{q.get('quote_id')}", not problems,
                              "; ".join(problems) or "segment and speaker consistent"))
    return res


# check_schema is not in ALL: evaluate.py runs it on the raw nested output before flattening.
ALL = [check_header, check_speakers, check_segments, check_references]
