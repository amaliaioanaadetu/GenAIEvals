"""Render evaluation results as a self-contained HTML report."""
import html
from datetime import datetime

from .results import CHECKS

CSS = """
:root{--bg:#F3F5F8;--surface:#FFFFFF;--ink:#1C2430;--muted:#5B6676;--line:#D9DEE5;
--pass:#2E7D5B;--pass-bg:#E3F2EA;--fail:#B23A2E;--fail-bg:#F8E4E1;--accent:#2B5C8A;color-scheme:light}
@media (prefers-color-scheme:dark){:root{--bg:#12161C;--surface:#1A2029;--ink:#E6EAF0;--muted:#9AA5B4;
--line:#2C3440;--pass:#5CC49A;--pass-bg:#173328;--fail:#F07A6B;--fail-bg:#3A1F1C;--accent:#7FB0E0;color-scheme:dark}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1040px;margin:0 auto;padding:48px 24px 80px}
h1,h2,.verdict{font-family:"Source Serif 4",Georgia,"Times New Roman",serif;font-weight:600}
h1{font-size:15px;color:var(--muted);font-family:inherit;font-weight:500;margin:0 0 8px}
.verdict{font-size:clamp(28px,4.4vw,44px);line-height:1.15;margin:0 0 14px;max-width:22ch}
.lede{color:var(--muted);max-width:68ch;margin:0 0 40px}
h2{font-size:22px;margin:48px 0 6px}
h2+p{color:var(--muted);margin:0 0 16px;max-width:70ch}
.wrap{overflow-x:auto;background:var(--surface);border:1px solid var(--line);border-radius:10px}
table{border-collapse:collapse;width:100%;min-width:640px}
th,td{text-align:left;padding:10px 14px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-weight:600;font-size:13px;color:var(--muted)}
tr:last-child td{border-bottom:0}
tr.group td{background:var(--bg);font-weight:600;font-size:13px;padding:8px 14px}
code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12.5px}
.num{font-variant-numeric:tabular-nums;white-space:nowrap}
.meter{display:inline-block;width:64px;height:6px;border-radius:3px;background:var(--fail-bg);margin-right:8px;vertical-align:middle;overflow:hidden}
.meter i{display:block;height:100%;background:var(--pass)}
.down{color:var(--fail);font-weight:600}.same{color:var(--muted)}
.tag{display:inline-block;padding:1px 8px;border-radius:99px;font-size:12.5px;font-weight:600}
.ok{background:var(--pass-bg);color:var(--pass)}.bad{background:var(--fail-bg);color:var(--fail)}
.gold{color:var(--accent);font-size:12.5px}
.desc{color:var(--muted);font-size:13px}
details{margin-top:12px}summary{cursor:pointer;color:var(--accent);font-weight:500}
summary:focus-visible{outline:2px solid var(--accent);outline-offset:3px}
.stats{display:flex;gap:32px;flex-wrap:wrap;margin:0 0 8px}
.stats div{min-width:140px}.stats b{display:block;font-size:22px;font-variant-numeric:tabular-nums}
.stats span{color:var(--muted);font-size:13px}
"""


def _e(s) -> str:
    return html.escape(str(s))


def _meter(rate):
    return f'<span class="meter"><i style="width:{rate * 100:.0f}%"></i></span>{rate * 100:.0f}%'


def _scorecard(runs: dict) -> str:
    names = list(runs)
    head = "".join(f"<th>{_e(n)}</th>" for n in names)
    if len(names) == 2:
        head += "<th>Change</th>"
    rows, current_cat = [], None
    for check, (cat, needs_gold, desc) in CHECKS.items():
        stats = [runs[n]["summary"]["checks"].get(check) for n in names]
        if not any(stats):
            continue
        if cat != current_cat:
            rows.append(f'<tr class="group"><td colspan="{len(names) + 3}">{_e(cat)}</td></tr>')
            current_cat = cat
        cells = "".join(
            f'<td class="num">{_meter(s["rate"])} <span class="desc">{s["passed"]}/{s["total"]}</span></td>'
            if s else "<td>–</td>" for s in stats)
        if len(names) == 2 and all(stats):
            d = stats[1]["rate"] - stats[0]["rate"]
            cells += (f'<td class="num down">{d * 100:+.0f} pts</td>' if d < -1e-9
                      else f'<td class="num same">{d * 100:+.0f} pts</td>')
        elif len(names) == 2:
            cells += "<td>–</td>"
        gold = ' <span class="gold">needs gold</span>' if needs_gold else ""
        rows.append(f"<tr><td><code>{_e(check)}</code>{gold}<div class='desc'>{_e(desc)}</div></td>{cells}</tr>")
    return f'<div class="wrap"><table><tr><th>Check</th>{head}</tr>{"".join(rows)}</table></div>'


def _failures(results: list) -> str:
    rows = "".join(
        f"<tr><td>{_e(r.example_id)}</td><td><code>{_e(r.check)}</code></td>"
        f"<td><code>{_e(r.item_ref)}</code></td><td>{_e(r.message)}</td></tr>"
        for r in results if not r.passed)
    if not rows:
        return "<p>No failures.</p>"
    return (f'<div class="wrap"><table><tr><th>Transcript</th><th>Check</th><th>Item</th><th>Finding</th></tr>'
            f"{rows}</table></div>")


def _faults_table(faults: list) -> str:
    rows = []
    for f in faults:
        if f.detected:
            tag = '<span class="tag ok">Caught</span>'
            by = ", ".join(f"<code>{_e(c)}</code>" for c in f.detected_by)
        else:
            tag = '<span class="tag bad">Missed</span>'
            by = _e("needs: " + ", ".join(f.expected_checks))
        kind = _e(f.fault_type.replace("_", " "))
        rows.append(f"<tr><td>{_e(f.example_id)}</td><td>{kind}</td><td>{_e(f.description)}</td>"
                    f"<td>{tag}</td><td>{by}</td></tr>")
    rows = "".join(rows)
    return (f'<div class="wrap"><table><tr><th>Transcript</th><th>Planted error</th><th>What changed</th>'
            f"<th>Result</th><th>Caught by</th></tr>{rows}</table></div>")


def _stats(runs: dict) -> str:
    blocks = []
    for name, run in runs.items():
        s = run["summary"]
        f1 = f'{s["event_f1"] * 100:.0f}%' if "event_f1" in s else "–"
        blocks.append(f'<div><b>{s["total_checks"] - s["failures"]}/{s["total_checks"]}</b>'
                      f'<span>checks passed, {_e(name)}</span></div>'
                      f'<div><b>{f1}</b><span>event F1, {_e(name)}</span></div>')
    return f'<div class="stats">{"".join(blocks)}</div>'


def render(runs: dict, faults: list = None, title: str = "Extraction evaluation report") -> str:
    """runs: {name: {"results": [...], "summary": {...}}}, in display order (baseline first)."""
    names = list(runs)
    if faults:
        caught = sum(f.detected for f in faults)
        missed = [f for f in faults if not f.detected]
        verdict = f"The pipeline caught {caught} of {len(faults)} planted errors."
        lede = ("Known errors were planted in otherwise good outputs, the kind LLM extraction actually makes: "
                "reworded quotes, wrong speakers, shifted dates, invented names and events. ")
        if missed:
            lede += ("Missed: " + "; ".join(f.description.lower() for f in missed) +
                     ". Errors that change meaning without adding new names or numbers need the LLM judge "
                     "(run with --judge).")
    else:
        s = runs[names[-1]]["summary"]
        verdict = f"{s['total_checks'] - s['failures']} of {s['total_checks']} checks passed."
        lede = "Every output was checked for structure, grounding in the transcript and, where gold labels exist, accuracy."

    parts = [f"<h1>{_e(title)}</h1>", f'<p class="verdict">{_e(verdict)}</p>',
             f'<p class="lede">{_e(lede)}</p>', _stats(runs),
             "<h2>Scorecard</h2><p>Pass rate per check. Checks without the gold tag need no labelled data, "
             "so they can run on every production output.</p>", _scorecard(runs)]
    if faults:
        parts += ["<h2>Planted errors</h2><p>Each error was injected deliberately. "
                  "A catch means a check failed on that exact item, and it had passed before the error was planted.</p>",
                  _faults_table(faults)]
    first = runs[names[0]]["results"]
    parts += [f"<h2>Findings in {_e(names[0])}</h2>"
              "<p>Even good output produces findings. Some are real errors; others are judgment calls where a "
              "reviewer decides whether the model or the gold label should change.</p>", _failures(first)]
    if len(names) > 1:
        parts += [f"<h2>All findings in {_e(names[-1])}</h2>",
                  f"<details><summary>Show {runs[names[-1]]['summary']['failures']} findings</summary>"
                  f"{_failures(runs[names[-1]]['results'])}</details>"]
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f"<title>{_e(title)}</title>"
            f'<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,600&display=swap">'
            f"<style>{CSS}</style></head><body><main>{''.join(parts)}"
            f'<p class="desc" style="margin-top:48px">Generated {stamp}</p></main></body></html>')
