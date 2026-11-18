"""Command-line entry point: python -m evalpoc <command>."""
import argparse
import sys

from . import report
from .evaluate import evaluate_run, summarize
from .faults import inject, score_detection
from .paths import REPORTS, RUNS


def _print_summary(name: str, summary: dict):
    print(f"\n{name}: {summary['total_checks'] - summary['failures']}/{summary['total_checks']} checks passed"
          + (f", event F1 {summary['event_f1']:.0%}" if "event_f1" in summary else ""))
    for check, s in summary["checks"].items():
        if s["passed"] < s["total"]:
            print(f"  {check:<20} {s['passed']:>3}/{s['total']:<3} ({s['rate']:.0%})")


def _write(name: str, html: str):
    REPORTS.mkdir(exist_ok=True)
    path = REPORTS / name
    path.write_text(html, encoding="utf-8")
    print(f"\nReport: {path}")


def cmd_demo(args):
    clean = evaluate_run(RUNS / "baseline", args.judge)
    faults = inject(RUNS / "baseline", RUNS / "faulty")
    faulty = evaluate_run(RUNS / "faulty", args.judge)
    faults = score_detection(faults, clean, faulty)
    runs = {"clean run": {"results": clean, "summary": summarize(clean)},
            "with planted errors": {"results": faulty, "summary": summarize(faulty)}}
    for name, r in runs.items():
        _print_summary(name, r["summary"])
    print(f"\nPlanted errors caught: {sum(f.detected for f in faults)}/{len(faults)}")
    for f in faults:
        status = "caught" if f.detected else "MISSED"
        print(f"  [{status:>6}] {f.example_id}  {f.fault_type:<20} {', '.join(f.detected_by) or '-'}")
    _write("demo_report.html", report.render(runs, faults, "Evaluation demo: planted errors"))


def cmd_evaluate(args):
    results = evaluate_run(RUNS / args.run, args.judge)
    summary = summarize(results)
    _print_summary(args.run, summary)
    _write(f"{args.run}_report.html", report.render({args.run: {"results": results, "summary": summary}},
                                                     title=f"Evaluation of run '{args.run}'"))


def cmd_compare(args):
    runs = {}
    for name in (args.baseline, args.candidate):
        results = evaluate_run(RUNS / name, args.judge)
        runs[name] = {"results": results, "summary": summarize(results)}
        _print_summary(name, runs[name]["summary"])
    _write(f"compare_{args.baseline}_vs_{args.candidate}.html",
           report.render(runs, title=f"{args.candidate} compared with {args.baseline}"))
    # CI gate: fail if any check drops by more than the threshold.
    base, cand = runs[args.baseline]["summary"]["checks"], runs[args.candidate]["summary"]["checks"]
    drops = {c: base[c]["rate"] - cand[c]["rate"] for c in base if c in cand
             and base[c]["rate"] - cand[c]["rate"] > args.max_drop}
    if drops:
        print("\nRegression: " + ", ".join(f"{c} -{d:.0%}" for c, d in drops.items()))
        sys.exit(1)
    print("\nNo regressions beyond threshold.")


def cmd_generate(args):
    from .generate import generate_run
    out = generate_run(args.run, args.limit)
    print(f"Saved outputs to {out}. Next: python -m evalpoc evaluate {args.run}")


def main():
    p = argparse.ArgumentParser(prog="evalpoc", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("demo", help="evaluate clean outputs, plant errors, measure what gets caught")
    d.add_argument("--judge", action="store_true", help="also run the LLM judge (needs an API key)")
    d.set_defaults(fn=cmd_demo)

    e = sub.add_parser("evaluate", help="evaluate one run folder under runs/")
    e.add_argument("run")
    e.add_argument("--judge", action="store_true")
    e.set_defaults(fn=cmd_evaluate)

    c = sub.add_parser("compare", help="compare two runs; exits 1 on regression (use in CI)")
    c.add_argument("baseline")
    c.add_argument("candidate")
    c.add_argument("--max-drop", type=float, default=0.05, help="allowed drop in pass rate per check")
    c.add_argument("--judge", action="store_true")
    c.set_defaults(fn=cmd_compare)

    g = sub.add_parser("generate", help="run the real extraction prompt (needs OPENAI_API_KEY)")
    g.add_argument("run", help="name for the new run folder")
    g.add_argument("--limit", type=int, default=None)
    g.set_defaults(fn=cmd_generate)

    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
