"""Run the real extraction prompt against a model and save outputs as a new run.

Uses OpenAI Structured Outputs (strict JSON schema), so malformed JSON cannot happen.
Requires OPENAI_API_KEY. Model defaults to gpt-5.1; override with GEN_MODEL.
"""
import copy
import hashlib
import json
import os
import time
from pathlib import Path

from .paths import PROMPTS, RUNS, SCHEMA, TRANSCRIPTS

MODEL = os.getenv("GEN_MODEL", "gpt-5.1")
# Keywords some strict-mode implementations reject; validation still enforces them afterwards.
UNSUPPORTED = {"$schema", "title", "pattern", "minimum", "format"}


def _strict_schema(node):
    if isinstance(node, dict):
        return {k: _strict_schema(v) for k, v in node.items() if k not in UNSUPPORTED}
    if isinstance(node, list):
        return [_strict_schema(v) for v in node]
    return node


def generate_run(run_name: str, limit: int | None = None) -> Path:
    from openai import OpenAI

    client = OpenAI()
    system = (PROMPTS / "extraction_system.md").read_text()
    user_tpl = (PROMPTS / "extraction_user.md").read_text()
    schema = _strict_schema(copy.deepcopy(json.loads(SCHEMA.read_text())))
    out_dir = RUNS / run_name
    out_dir.mkdir(parents=True, exist_ok=True)

    meta = {"model": MODEL, "prompt_sha": hashlib.sha256((system + user_tpl).encode()).hexdigest()[:12],
            "schema_sha": hashlib.sha256(SCHEMA.read_bytes()).hexdigest()[:12], "items": []}
    paths = sorted(TRANSCRIPTS.glob("TR-*.txt"))[:limit]
    for path in paths:
        t0 = time.time()
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user_tpl.format(transcript=path.read_text())}],
            response_format={"type": "json_schema",
                             "json_schema": {"name": "news_extraction", "schema": schema, "strict": True}},
        )
        msg = resp.choices[0].message
        content = msg.content if msg.content else json.dumps({"refusal": msg.refusal})
        (out_dir / f"{path.stem}.json").write_text(content)
        meta["items"].append({"id": path.stem, "latency_s": round(time.time() - t0, 2),
                              "input_tokens": resp.usage.prompt_tokens,
                              "output_tokens": resp.usage.completion_tokens})
        print(f"  {path.stem}: {meta['items'][-1]['latency_s']}s, {resp.usage.completion_tokens} output tokens")
    (out_dir / "run_meta.json").write_text(json.dumps(meta, indent=2))
    return out_dir
