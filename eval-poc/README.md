# Evaluation pipeline proof of concept: news extraction from transcripts

A small, runnable simulation of an LLM extraction system and the pipeline that evaluates it.
An LLM receives a broadcast transcript and must return structured JSON with:
- clear fields: IDs, dates, show metadata;
- judgment-heavy fields: segments, topics, tone of speech, events and quotes.

The pipeline then measures how good that JSON is.

## Quick start

```bash
pip install -r requirements.txt
python -m evalpoc demo
```

Open `reports/demo_report.html`. No API key is needed for the demo.

## What's in here

```
prompts/extraction_system.md     the extraction prompt (system message)
prompts/extraction_user.md       user message template, {transcript} is filled in
schema/news_extraction.schema.json  output contract (also used for OpenAI Structured Outputs)
data/transcripts/                3 fictional broadcasts (TV news, radio phone-in, evening show)
data/gold/                       partial human labels: segments, topics, tones, key events, quotes
runs/baseline/                   simulated model outputs: good, with a few realistic disagreements
evalpoc/
  checks_structure.py   schema, metadata, speakers, segment coverage, cross-references
  checks_grounding.py   quotes verbatim, speaker attribution, entities, figures, hallucination screen
  checks_gold.py        matches items to gold, then compares boundaries, types, topics, tone, dates
  judge.py              optional LLM judge for summaries and descriptions (claim by claim, cached)
  faults.py             plants 16 known errors to measure what the pipeline catches
  evaluate.py           runs all checks, saves results, computes pass rates and event F1
  report.py             HTML report
  generate.py           runs the real prompt against GPT-5.1 with strict structured outputs
  cli.py                commands: demo, evaluate, compare, generate
```

## How the evaluation is layered

| Layer | Needs gold labels? | Examples | Runs in production? |
|---|---|---|---|
| Structure & consistency | No | schema valid, IDs/dates match metadata, segments contiguous, timestamps correct, evidence inside its segment | Yes |
| Grounding | No | quotes verbatim on the cited line, right speaker, entities and figures exist in the source, no invented names/numbers in summaries | Yes |
| Accuracy vs gold | Yes | segment boundaries (±1 line), type, topics, tone; event recall/precision, type, date; quote recall and tone | Test set only |
| LLM judge | No | each claim in a summary/description is supported by the segment | Yes (sampled) |

Lists such as events cannot be compared to gold position by position. `checks_gold.py` first
matches each extracted event to a gold event by evidence-line overlap and type. It then scores:
- unmatched gold events as **misses** (recall),
- unmatched extracted events as **extras** (precision),
- matched pairs field by field.

## The demo: showing why this matters

`python -m evalpoc demo` tells a four-step story.

**1. Clean run.** The simulated outputs are good but not perfect. The pipeline raises 3 findings:
- an extra topic,
- an event the gold set didn't include,
- a date the model inferred where gold says "unknown".

Use these to show that findings need human judgment. Sometimes the model is wrong; sometimes the gold label should change.

**2. Planted errors.** 16 realistic errors are injected into the same outputs:
- a reworded quote,
- a quote attributed to the wrong caller,
- "next Monday" resolved to the wrong week,
- a lost-revenue figure changed,
- an invented mayor in a description,
- an invented event,
- a dropped event,
- a segment gap,
- an invalid enum value,
- evidence pointing at the wrong lines,
- a wrong tone, topic, timestamp and transcript ID,
- a summary that reverses an expert's point.

Every one still looks plausible in valid JSON. A human skimming the output would miss most of them.

**3. Detection.** The pipeline catches 15 of 16 in under a second, without any API calls, and points to the exact item and reason for each.

**4. The honest miss.** The reversed summary adds no new names or numbers, so cheap checks can't see it. That is exactly the case for the LLM judge (`--judge`). It also shows why you combine methods rather than relying on one.

Then run `python -m evalpoc compare baseline faulty`. It exits with code 1 and lists the regressed checks. This is what a CI gate on prompt changes looks like.

Talking points for stakeholders:
- **Coverage without humans.** Most checks need no gold labels, so they can screen every production output, not a sample.
- **Specific, actionable findings.** A failure reads "quote Q-02 attributed to 'Greta', L12 is spoken by 'Mihai'", not "quality score 7/10".
- **Safe iteration.** Any prompt or model change gets a before/after scorecard, so improvements are measured and regressions blocked.
- **Measured trust in the checker itself.** Planted-error detection rate is a number you can track as the pipeline grows.

## Running it on the real model

```bash
export OPENAI_API_KEY=...
python -m evalpoc generate gpt51_v1          # runs the prompt on every transcript
python -m evalpoc evaluate gpt51_v1          # report for that run
# edit prompts/extraction_system.md, then:
python -m evalpoc generate gpt51_v2
python -m evalpoc compare gpt51_v1 gpt51_v2  # before/after, exits 1 on regression
```

To add the LLM judge, set `ANTHROPIC_API_KEY`, or set `JUDGE_PROVIDER=openai` to use OpenAI instead. Then add `--judge`.

Using a different model family as the judge reduces self-preference bias. Judge calls are cached in `.cache/judge/`, so re-runs only pay for changed items.

Useful extra experiments once it runs live:
- **Consistency.** Generate the same transcripts 3 to 5 times and compare runs to see how stable segments, topics and tone are.
- **Judge calibration.** Hand-label 30 to 50 judge verdicts and measure agreement before trusting the judge.

## Extending

- **Add a transcript.** Put `TR-....txt` in `data/transcripts/`. Gold labels are optional: without them only the reference-free checks run.
- **Add a check.** Write a function that returns a list of `EvalResult`, append it to the module's `ALL` list, and register it in `results.CHECKS`.
- **Add a fault.** Add an entry to `faults.PLAN`.

## Limitations of this POC

- **Small data.** Three transcripts and hand-written outputs are enough to demonstrate the method, not to measure a real system.
- **Heuristic screen.** `text_grounding` is a cheap hallucination screen based on numbers and capitalised names. It will miss paraphrased errors, as the demo shows.
- **Untested live paths.** `generate.py` and `judge.py` use the OpenAI and Anthropic SDKs but were not run against live APIs when this was built. Check model names and parameters against current API docs.
