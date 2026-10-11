"""Static guidance shown in the app: how the UK market works, tone phrases, CV rules.
This is product copy, not user data, so it lives in a file and is the same for everyone."""
import json
from pathlib import Path

PATH = Path(__file__).parent / "data" / "content.json"


def load() -> dict:
    return json.loads(PATH.read_text(encoding="utf-8"))
