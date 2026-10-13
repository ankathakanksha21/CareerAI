"""The story bank: which achievements get a STAR story, and writing them a few at a time."""
import ai
from parallel import together

BANK = 8   # stories a candidate needs; the bank never takes the total past this
BATCH = 4  # stories per model call. Eight in one call took about 40 seconds; two calls of four run side by side


def pick(without_story: list[dict], story_count: int) -> list[dict]:
    """The achievements to write for: as many as the bank still has room for, those that already
    carry a number first, otherwise in the order given (newest first)."""
    room = max(0, BANK - story_count)
    return sorted(without_story, key=ai.needs_number)[:room]


def write(chosen: list[dict], taken: list[str]) -> tuple[list[tuple[str, dict]], int]:
    """Stories for the chosen achievements: [(achievement id, story)], and how many could not be
    written. One failed batch loses only its own stories; AIError if every batch fails."""
    numbered = [a | {"n": n} for n, a in enumerate(chosen, start=1)]
    batches = [numbered[i:i + BATCH] for i in range(0, len(numbered), BATCH)]

    def one(batch):
        try:
            return ai.story_bank(batch, taken)
        except ai.AIError:
            return None
    results = together(one, batches)
    if batches and all(r is None for r in results):
        raise ai.AIError("story bank")
    ids = {a["n"]: a["id"] for a in numbered}
    written = [(ids[n], story) for r in results if r for n, story in sorted(r.items())]
    return written, len(chosen) - len(written)
