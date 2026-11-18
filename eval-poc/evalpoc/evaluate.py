"""Run every check over every output in a run folder and save the results."""
import json
from collections import defaultdict
from pathlib import Path

from . import checks_gold, checks_grounding, checks_structure
from .paths import GOLD, TRANSCRIPTS
from .results import CHECKS, EvalResult
from .shape import flatten
from .transcript import load_transcript


def evaluate_output(raw: dict, example_id: str, use_judge: bool = False) -> list:
    """`raw` is the model output as returned (events and quotes nested in segments).
    The schema is validated on that; every other check runs on the flattened form."""
    tr = load_transcript(TRANSCRIPTS / f"{example_id}.txt")
    results = checks_structure.check_schema(raw, tr)
    out = flatten(raw)
    for check in checks_structure.ALL + checks_grounding.ALL:
        results += check(out, tr)
    gold_path = GOLD / f"{example_id}.json"
    if gold_path.exists():
        gold = flatten(json.loads(gold_path.read_text()))  # gold uses the same nested layout
        for check in checks_gold.ALL:
            results += check(out, gold, tr)
    if use_judge:
        from .judge import check_faithfulness
        results += check_faithfulness(out, tr)
    return results


def evaluate_run(run_dir: Path, use_judge: bool = False) -> list:
    results = []
    for path in sorted(Path(run_dir).glob("TR-*.json")):
        example_id = path.stem  # file name = transcript id, so a wrong id inside the file is detectable
        try:
            out = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            results.append(EvalResult("schema_valid", example_id, "output", False, f"not valid JSON: {exc}"))
            continue
        results += evaluate_output(out, example_id, use_judge)
    out_file = Path(run_dir) / "eval_results.jsonl"
    out_file.write_text("\n".join(json.dumps(r.to_dict()) for r in results) + "\n")
    return results


def summarize(results: list) -> dict:
    """Pass rates per check, plus event precision/recall."""
    per_check = defaultdict(lambda: [0, 0])
    for r in results:
        per_check[r.check][0] += r.passed
        per_check[r.check][1] += 1
    summary = {"checks": {}}
    for name, (passed, total) in per_check.items():
        cat, needs_gold, desc = CHECKS.get(name, ("Other", False, name))
        summary["checks"][name] = {"passed": passed, "total": total, "rate": passed / total,
                                   "category": cat, "needs_gold": needs_gold, "description": desc}
    p = summary["checks"].get("event_precision", {}).get("rate")
    r = summary["checks"].get("event_recall", {}).get("rate")
    if p is not None and r is not None:
        summary["event_f1"] = 2 * p * r / (p + r) if p + r else 0.0
    summary["total_checks"] = len(results)
    summary["failures"] = sum(not r.passed for r in results)
    return summary
