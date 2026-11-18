"""Common result format shared by every check, plus a registry describing each check."""
from dataclasses import dataclass, field, asdict


@dataclass
class EvalResult:
    check: str
    example_id: str
    item_ref: str
    passed: bool
    message: str = ""
    score: float | None = None
    details: dict = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)


STRUCTURE = "Structure & consistency"
GROUNDING = "Grounding in the transcript"
GOLD = "Accuracy against gold labels"
JUDGE = "LLM judge"

# name -> (category, needs_gold, plain-language description)
CHECKS = {
    "schema_valid":         (STRUCTURE, False, "Output matches the JSON schema (types, enums, required fields)"),
    "header_fields":        (STRUCTURE, False, "IDs, show name, date, duration and language match the transcript metadata"),
    "speaker_labels":       (STRUCTURE, False, "Every speaker exists in the transcript and every transcript speaker is listed"),
    "segment_coverage":     (STRUCTURE, False, "Segments are contiguous and cover every line once"),
    "segment_timestamps":   (STRUCTURE, False, "Segment start times match the transcript timestamps"),
    "references":           (STRUCTURE, False, "IDs referenced by events and quotes exist; evidence sits inside its segment"),
    "quote_verbatim":       (GROUNDING, False, "Quote text appears verbatim on the cited line"),
    "quote_speaker":        (GROUNDING, False, "Quote is attributed to the person who spoke the cited line"),
    "entity_grounding":     (GROUNDING, False, "Event entities are mentioned in the transcript"),
    "figure_grounding":     (GROUNDING, False, "Event figures appear in the event's segment"),
    "text_grounding":       (GROUNDING, False, "Numbers and names in summaries and descriptions appear in the source (heuristic)"),
    "segment_boundaries":   (GOLD, True, "Segment boundaries match gold within one line"),
    "segment_type":         (GOLD, True, "Segment type matches gold"),
    "segment_topics":       (GOLD, True, "Segment topics match gold"),
    "segment_tone":         (GOLD, True, "Segment tone matches gold"),
    "event_recall":         (GOLD, True, "Every gold event was extracted"),
    "event_precision":      (GOLD, True, "Every extracted event corresponds to a gold event"),
    "event_type":           (GOLD, True, "Event type matches gold"),
    "event_date":           (GOLD, True, "Event date matches gold"),
    "quote_recall":         (GOLD, True, "Every gold quote was extracted"),
    "quote_tone":           (GOLD, True, "Quote tone matches gold"),
    "judge_faithfulness":   (JUDGE, False, "LLM judge: every claim in a summary or description is supported by the source"),
}
