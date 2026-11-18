"""LLM-as-judge for free-text fields (segment summaries and event descriptions).

The judge decomposes the text into atomic claims and labels each one against the source
passage. It should be a different model family from the generator (here: generation with
GPT, judging with Claude by default) to reduce self-preference bias.

Enable with --judge. Requires ANTHROPIC_API_KEY (default) or OPENAI_API_KEY with
JUDGE_PROVIDER=openai. Results are cached on disk, so re-running unchanged items is free.
"""
import hashlib
import json
import os
import re

from .paths import ROOT
from .results import EvalResult
from .transcript import Transcript

CACHE = ROOT / ".cache" / "judge"
PROVIDER = os.getenv("JUDGE_PROVIDER", "anthropic")
MODEL = os.getenv("JUDGE_MODEL", "claude-sonnet-5-5" if PROVIDER == "anthropic" else "gpt-5.1")
PROMPT_VERSION = "faithfulness-v1"

JUDGE_PROMPT = """You are checking a news extraction for faithfulness to its source.

SOURCE (transcript lines):
{source}

TEXT TO CHECK:
{text}

Split the text into atomic factual claims. For each claim decide:
- SUPPORTED: the source states it or it follows directly
- CONTRADICTED: the source says something different
- NOT_IN_SOURCE: the source does not mention it

Be strict: a claim that changes the meaning, strength or direction of what was said is CONTRADICTED.
Respond with JSON only, no markdown:
{{"claims": [{{"claim": "...", "verdict": "SUPPORTED|CONTRADICTED|NOT_IN_SOURCE", "evidence": "short excerpt or line number"}}]}}"""


def _call(prompt: str) -> str:
    if PROVIDER == "anthropic":
        import anthropic
        msg = anthropic.Anthropic().messages.create(
            model=MODEL, max_tokens=1500, messages=[{"role": "user", "content": prompt}])
        return "".join(b.text for b in msg.content if b.type == "text")
    from openai import OpenAI
    resp = OpenAI().chat.completions.create(
        model=MODEL, messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"})
    return resp.choices[0].message.content


def judge_text(text: str, source: str) -> dict:
    prompt = JUDGE_PROMPT.format(source=source, text=text)
    key = hashlib.sha256(f"{PROVIDER}|{MODEL}|{PROMPT_VERSION}|{prompt}".encode()).hexdigest()
    path = CACHE / f"{key}.json"
    if path.exists():
        return json.loads(path.read_text())
    raw = _call(prompt)
    data = json.loads(re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M).strip())
    CACHE.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))
    return data


def _source(tr: Transcript, start: int, end: int) -> str:
    return "\n".join(f"[L{n:03d}] {tr.lines[n].speaker}: {tr.lines[n].text}"
                     for n in range(start, end + 1) if n in tr.lines)


def check_faithfulness(out: dict, tr: Transcript) -> list:
    segs = {s.get("segment_id"): s for s in out.get("segments", [])}
    items = [(f"segment:{s.get('segment_id')}", s.get("summary", ""), s) for s in out.get("segments", [])]
    items += [(f"event:{e.get('event_id')}", e.get("description", ""), segs.get(e.get("segment_id")))
              for e in out.get("events", [])]
    res = []
    for ref, text, seg in items:
        if not seg or not text:
            continue
        try:
            verdict = judge_text(text, _source(tr, seg["start_line"], seg["end_line"]))
        except Exception as exc:  # keep the run going; report the failure
            res.append(EvalResult("judge_faithfulness", tr.id, ref, False, f"judge error: {exc}"))
            continue
        claims = verdict.get("claims", [])
        bad = [c for c in claims if c.get("verdict") != "SUPPORTED"]
        score = 1 - len(bad) / len(claims) if claims else 1.0
        res.append(EvalResult("judge_faithfulness", tr.id, ref, not bad,
                              "; ".join(f"{c['verdict']}: {c['claim']}" for c in bad) or
                              f"all {len(claims)} claims supported",
                              score=score, details={"claims": claims, "model": MODEL}))
    return res
