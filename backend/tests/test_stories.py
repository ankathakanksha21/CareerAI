import pytest

import ai
import stories


def achievement(n, **kw):
    return {"id": f"a{n}", "title": f"Thing {n}", "uk_version": f"Built thing {n} for 15 users", "outcome": ""} | kw


def story(title="Story"):
    return {"title": title, "competency": "Problem solving", "situation": "s", "task": "t", "action": "a", "result": "r", "strength": "strong", "tip": ""}


@pytest.fixture
def bank(monkeypatch):
    """Replace the model: each batch gets a story for every achievement in it, unless its first
    achievement's id is in `failing`. Returns the batches asked for."""
    def install(failing=()):
        asked = []

        def fake(batch, taken=()):
            asked.append(([a["id"] for a in batch], list(taken)))
            if batch[0]["id"] in failing:
                raise ai.AIError("story bank")
            return {a["n"]: story(f"Story of {a['id']}") for a in batch}
        monkeypatch.setattr(ai, "story_bank", fake)
        return asked
    return install


# ---------- which achievements get a story ----------

def test_pick_fills_the_bank_up_to_eight_and_no_further():
    ten = [achievement(n) for n in range(10)]
    assert len(stories.pick(ten, 0)) == 8
    assert len(stories.pick(ten, 5)) == 3
    assert stories.pick(ten, 8) == [] and stories.pick(ten, 11) == []
    assert stories.pick([], 0) == []


def test_pick_takes_achievements_with_a_number_first_then_the_order_given():
    weak = achievement(1, uk_version="Built a report", outcome="Add a number: how many used it")
    plain = achievement(2, uk_version="Wrote a script")
    strong, strong_too = achievement(3), achievement(4)
    assert [a["id"] for a in stories.pick([weak, strong, plain, strong_too], 5)] == ["a3", "a4", "a1"]


# ---------- writing them ----------

def test_write_asks_in_batches_of_four_and_pairs_each_story_with_its_achievement(bank):
    asked = bank()
    chosen = [achievement(n) for n in range(1, 8)]
    written, missed = stories.write(chosen, ["Teamwork"])
    assert sorted(len(ids) for ids, _ in asked) == [3, 4] and all(taken == ["Teamwork"] for _, taken in asked)
    assert [(a, s["title"]) for a, s in written] == [(f"a{n}", f"Story of a{n}") for n in range(1, 8)]
    assert missed == 0


def test_write_keeps_one_batch_when_the_other_fails(bank):
    bank(failing={"a5"})
    written, missed = stories.write([achievement(n) for n in range(1, 8)], [])
    assert [a for a, _ in written] == ["a1", "a2", "a3", "a4"] and missed == 3


def test_write_fails_when_every_batch_fails(bank):
    bank(failing={"a1", "a5"})
    with pytest.raises(ai.AIError):
        stories.write([achievement(n) for n in range(1, 8)], [])


def test_write_counts_a_story_the_model_left_out(bank, monkeypatch):
    monkeypatch.setattr(ai, "story_bank", lambda batch, taken=(): {batch[0]["n"]: story()})
    written, missed = stories.write([achievement(1), achievement(2)], [])
    assert [a for a, _ in written] == ["a1"] and missed == 1


def test_write_nothing_asks_nothing(bank):
    asked = bank()
    assert stories.write([], []) == ([], 0) and asked == []
