from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TRANSCRIPTS = ROOT / "data" / "transcripts"
GOLD = ROOT / "data" / "gold"
RUNS = ROOT / "runs"
REPORTS = ROOT / "reports"
SCHEMA = ROOT / "schema" / "news_extraction.schema.json"
PROMPTS = ROOT / "prompts"
