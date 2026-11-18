"""Accuracy against gold labels.

Gold annotations are deliberately partial: segment boundaries, types, topics and tones;
key events with an evidence range; and notable quotes. Model items are first *matched*
to gold items (by line overlap), then compared field by field.
"""
from .results import EvalResult
from .transcript import Transcript

BOUNDARY_TOLERANCE = 1   # lines
SEGMENT_MIN_IOU = 0.5
EVENT_MIN_SCORE = 0.5


def _iou(a: tuple, b: tuple) -> float:
    sa, sb = set(range(a[0], a[1] + 1)), set(range(b[0], b[1] + 1))
    return len(sa & sb) / len(sa | sb) if sa | sb else 0.0


def _greedy_match(pairs: list) -> dict:
    """pairs: (score, left_idx, right_idx). Returns {left_idx: (right_idx, score)}, one-to-one."""
    used_l, used_r, out = set(), set(), {}
    for score, l, r in sorted(pairs, reverse=True):
        if l not in used_l and r not in used_r:
            out[l] = (r, score)
            used_l.add(l)
            used_r.add(r)
    return out


def check_segments(out: dict, gold: dict, tr: Transcript) -> list:
    res = []
    segs = out.get("segments", [])
    gsegs = gold.get("segments", [])
    pairs = []
    for gi, g in enumerate(gsegs):
        for si, s in enumerate(segs):
            score = _iou((g["start_line"], g["end_line"]), (s.get("start_line", 0), s.get("end_line", -1)))
            if score >= SEGMENT_MIN_IOU:
                pairs.append((score, gi, si))
    matches = _greedy_match(pairs)

    for gi, g in enumerate(gsegs):
        span = f"L{g['start_line']}-L{g['end_line']}"
        if gi not in matches:
            res.append(EvalResult("segment_boundaries", tr.id, f"gold_segment:{span}", False,
                                  f"no extracted segment overlaps gold segment {span} well enough"))
            continue
        s = segs[matches[gi][0]]
        ref = f"segment:{s.get('segment_id')}"
        ds, de = abs(s["start_line"] - g["start_line"]), abs(s["end_line"] - g["end_line"])
        res.append(EvalResult("segment_boundaries", tr.id, ref,
                              ds <= BOUNDARY_TOLERANCE and de <= BOUNDARY_TOLERANCE,
                              f"L{s['start_line']}-L{s['end_line']} vs gold {span}", score=matches[gi][1]))
        res.append(EvalResult("segment_type", tr.id, ref, s.get("segment_type") == g["segment_type"],
                              f"{s.get('segment_type')!r} vs gold {g['segment_type']!r}"))
        got, want = set(s.get("topics", [])), set(g["topics"])
        jacc = len(got & want) / len(got | want) if got | want else 1.0
        res.append(EvalResult("segment_topics", tr.id, ref, got == want,
                              f"{sorted(got)} vs gold {sorted(want)}", score=jacc,
                              details={"extra": sorted(got - want), "missing": sorted(want - got)}))
        res.append(EvalResult("segment_tone", tr.id, ref, s.get("tone") == g["tone"],
                              f"{s.get('tone')!r} vs gold {g['tone']!r}"))
    return res


def check_events(out: dict, gold: dict, tr: Transcript) -> list:
    res = []
    events = out.get("events", [])
    gevents = gold.get("events", [])
    pairs = []
    for gi, g in enumerate(gevents):
        for ei, e in enumerate(events):
            ev = e.get("evidence") or {}
            overlap = _iou((g["evidence"]["start_line"], g["evidence"]["end_line"]),
                           (ev.get("start_line", 0), ev.get("end_line", -1)))
            if overlap == 0:
                continue
            score = 0.7 * overlap + 0.3 * (e.get("event_type") == g["event_type"])
            if score >= EVENT_MIN_SCORE:
                pairs.append((score, gi, ei))
    matches = _greedy_match(pairs)
    matched_events = {ei for ei, _ in matches.values()}

    for gi, g in enumerate(gevents):
        if gi not in matches:
            res.append(EvalResult("event_recall", tr.id, f"gold_event:{g['gold_id']}", False,
                                  f"missed gold event {g['gold_id']} ({g['event_type']}, "
                                  f"L{g['evidence']['start_line']}-L{g['evidence']['end_line']})"))
            continue
        e = events[matches[gi][0]]
        ref = f"event:{e.get('event_id')}"
        res.append(EvalResult("event_recall", tr.id, f"gold_event:{g['gold_id']}", True,
                              f"found as {e.get('event_id')}", score=matches[gi][1]))
        res.append(EvalResult("event_type", tr.id, ref, e.get("event_type") == g["event_type"],
                              f"{e.get('event_type')!r} vs gold {g['event_type']!r}"))
        res.append(EvalResult("event_date", tr.id, ref, e.get("event_date") == g["event_date"],
                              f"{e.get('event_date')!r} vs gold {g['event_date']!r}"))

    for ei, e in enumerate(events):
        ok = ei in matched_events
        res.append(EvalResult("event_precision", tr.id, f"event:{e.get('event_id')}", ok,
                              "matches a gold event" if ok else
                              "no matching gold event: invented, over-split, or missing from gold"))
    return res


def check_quotes(out: dict, gold: dict, tr: Transcript) -> list:
    res = []
    by_line = {q.get("line"): q for q in out.get("quotes", [])}
    for g in gold.get("quotes", []):
        q = by_line.get(g["line"])
        if q is None:
            res.append(EvalResult("quote_recall", tr.id, f"gold_quote:L{g['line']}", False,
                                  f"missed quote by {g['speaker_name']} on L{g['line']}"))
            continue
        ref = f"quote:{q.get('quote_id')}"
        res.append(EvalResult("quote_recall", tr.id, f"gold_quote:L{g['line']}", True, f"found as {q.get('quote_id')}"))
        res.append(EvalResult("quote_tone", tr.id, ref, q.get("tone") == g["tone"],
                              f"{q.get('tone')!r} vs gold {g['tone']!r}"))
    return res


ALL = [check_segments, check_events, check_quotes]
