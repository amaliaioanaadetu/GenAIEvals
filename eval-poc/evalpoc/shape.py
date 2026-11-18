"""Convert between the nested output shape and the flat shape the checks work on.

The model returns events and quotes nested inside the segment they belong to:

    segments: [{segment_id, ..., events: [...], quotes: [...]}, ...]

The checks, gold matching and fault injection are simpler on flat lists, so outputs are
flattened once after loading: every event and quote moves to a top-level list and gets a
`segment_id` pointing back to its parent segment.
"""
import copy


def flatten(out: dict) -> dict:
    """Nested output -> copy with top-level `events` and `quotes` lists carrying `segment_id`."""
    flat = copy.deepcopy(out)
    events, quotes = [], []
    for seg in flat.get("segments") or []:
        if not isinstance(seg, dict):
            continue
        sid = seg.get("segment_id")
        for key, bucket in (("events", events), ("quotes", quotes)):
            for item in seg.pop(key, None) or []:
                if isinstance(item, dict):
                    bucket.append({**item, "segment_id": sid})
    flat["events"], flat["quotes"] = events, quotes
    return flat


def nest(flat: dict) -> dict:
    """Inverse of `flatten`. Items whose `segment_id` matches no segment are dropped."""
    out = copy.deepcopy(flat)
    events, quotes = out.pop("events", []), out.pop("quotes", [])
    segs = {s.get("segment_id"): s for s in out.get("segments", [])}
    for s in segs.values():
        s["events"], s["quotes"] = [], []
    for key, items in (("events", events), ("quotes", quotes)):
        for item in items:
            seg = segs.get(item.get("segment_id"))
            if seg is not None:
                seg[key].append({k: v for k, v in item.items() if k != "segment_id"})
    return out
