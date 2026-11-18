"""Plant known errors in good outputs, then measure how many the pipeline catches.

Each fault mimics a real failure mode of LLM extraction. Faults are applied to a copy of
a run; a fault counts as detected if the faulty run has a *new* failing result (one not
present in the clean run) on the item the fault touched.
"""
import copy
import json
from dataclasses import dataclass, asdict
from pathlib import Path


@dataclass
class Fault:
    example_id: str
    fault_type: str
    item_ref: str
    description: str
    expected_checks: list
    detected: bool = False
    detected_by: list = None


def _find(items, key, value):
    return next(i for i in items if i.get(key) == value)


# Each entry: (example_id, fault_type, item_ref, description, expected_checks, mutation)
PLAN = [
    ("TR-2026-0312-HEB", "altered_quote", "quote:Q-01",
     "Quote reworded: 'groceries' became 'rent'", ["quote_verbatim"],
     lambda o: _find(o["quotes"], "quote_id", "Q-01").update(
         text="People are choosing between a bus ticket and rent. This freeze gives families one less thing to worry about.")),
    ("TR-2026-0312-HEB", "wrong_figure", "event:EVT-01",
     "Lost revenue changed from 6.5 to 8.5 million euros", ["figure_grounding"],
     lambda o: _find(o["events"], "event_id", "EVT-01")["figures"][3].update(value="8.5 million euros")),
    ("TR-2026-0312-HEB", "dropped_event", None,
     "Sports result event removed", ["event_recall"],
     lambda o: o.update(events=[e for e in o["events"] if e["event_id"] != "EVT-05"])),
    ("TR-2026-0312-HEB", "wrong_tone", "segment:SEG-03",
     "Fire report tone changed from 'urgent' to 'positive'", ["segment_tone"],
     lambda o: _find(o["segments"], "segment_id", "SEG-03").update(tone="positive")),
    ("TR-2026-0312-HEB", "wrong_timestamp", "segment:SEG-05",
     "Sports segment start time off by 2 seconds", ["segment_timestamps"],
     lambda o: _find(o["segments"], "segment_id", "SEG-05").update(start_time="00:02:50")),
    ("TR-2026-0312-HEB", "distorted_summary", "segment:SEG-04",
     "Summary reverses the economist's point (no new names or numbers)", ["judge_faithfulness"],
     lambda o: _find(o["segments"], "segment_id", "SEG-04").update(
         summary="Economist Lena Hart says the freeze is good for riders and will lead to more frequent buses on low-traffic routes.")),

    ("TR-2026-0313-ML", "wrong_speaker", "quote:Q-02",
     "Mihai's quote attributed to Greta", ["quote_speaker"],
     lambda o: _find(o["quotes"], "quote_id", "Q-02").update(speaker_id="SPK5")),
    ("TR-2026-0313-ML", "wrong_date", "event:EVT-01",
     "'Next Monday' resolved to the wrong week (2026-03-23)", ["event_date"],
     lambda o: _find(o["events"], "event_id", "EVT-01").update(event_date="2026-03-23")),
    ("TR-2026-0313-ML", "boundary_shift", "segment:SEG-03",
     "Listener-calls segment starts two lines late, leaving a gap", ["segment_coverage", "segment_boundaries"],
     lambda o: _find(o["segments"], "segment_id", "SEG-03").update(start_line=12)),
    ("TR-2026-0313-ML", "hallucinated_name", "event:EVT-03",
     "Description gains an invented quote from a non-existent mayor", ["text_grounding"],
     lambda o: _find(o["events"], "event_id", "EVT-03").update(
         description=_find(o["events"], "event_id", "EVT-03")["description"]
         + " Mayor Viktor Sand called it the worst storm in 40 years.")),
    ("TR-2026-0313-ML", "hallucinated_entity", "event:EVT-02",
     "Invented person added to entities", ["entity_grounding"],
     lambda o: _find(o["events"], "event_id", "EVT-02")["entities"].append(
         {"name": "Dr. Helena Strand", "type": "person"})),

    ("TR-2026-0314-HT", "wrong_id", "transcript_id",
     "Transcript ID mistyped", ["header_fields"],
     lambda o: o.update(transcript_id="TR-2026-0314-HTN")),
    ("TR-2026-0314-HT", "invented_event", "event:EVT-04",
     "Plausible but invented event: developer withdraws application", ["event_precision", "judge_faithfulness"],
     lambda o: o["events"].append({
         "event_id": "EVT-04", "segment_id": "SEG-02", "event_type": "announcement",
         "description": "Coldwater Digital announced it will withdraw its data centre application.",
         "event_date": "2026-03-14", "location": "Halden",
         "entities": [{"name": "Coldwater Digital", "type": "organization"}], "figures": [],
         "evidence": {"start_line": 8, "end_line": 8}})),
    ("TR-2026-0314-HT", "schema_violation", "segment:SEG-02",
     "Segment type 'breaking_news' is not an allowed value", ["schema_valid"],
     lambda o: _find(o["segments"], "segment_id", "SEG-02").update(segment_type="breaking_news")),
    ("TR-2026-0314-HT", "bad_evidence", "event:EVT-03",
     "Court-fine evidence points at the interview lines", ["references"],
     lambda o: _find(o["events"], "event_id", "EVT-03").update(evidence={"start_line": 14, "end_line": 16})),
    ("TR-2026-0314-HT", "wrong_topic", "segment:SEG-04",
     "Topic 'environment' replaced with 'health'", ["segment_topics"],
     lambda o: _find(o["segments"], "segment_id", "SEG-04").update(topics=["health", "business"])),
]


def inject(clean_dir: Path, faulty_dir: Path) -> list:
    faulty_dir.mkdir(parents=True, exist_ok=True)
    outputs = {p.stem: json.loads(p.read_text()) for p in sorted(clean_dir.glob("TR-*.json"))}
    outputs = copy.deepcopy(outputs)
    faults = []
    for example_id, ftype, ref, desc, checks, mutate in PLAN:
        if example_id not in outputs:
            continue
        mutate(outputs[example_id])
        faults.append(Fault(example_id, ftype, ref, desc, checks))
    for example_id, out in outputs.items():
        (faulty_dir / f"{example_id}.json").write_text(json.dumps(out, indent=2))
    (faulty_dir / "faults.json").write_text(json.dumps([asdict(f) for f in faults], indent=2))
    return faults


def score_detection(faults: list, clean_results: list, faulty_results: list) -> list:
    """A fault is detected if a failure appears in the faulty run that wasn't in the clean run."""
    key = lambda r: (r.example_id, r.check, r.item_ref)
    clean_failures = {key(r) for r in clean_results if not r.passed}
    new_failures = [r for r in faulty_results if not r.passed and key(r) not in clean_failures]
    for f in faults:
        hits = [r for r in new_failures if r.example_id == f.example_id and
                (r.item_ref == f.item_ref if f.item_ref else r.check in f.expected_checks)]
        f.detected = bool(hits)
        f.detected_by = sorted({r.check for r in hits})
    return faults
