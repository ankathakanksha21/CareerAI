import pytest

import jobs

MINE = ["Delivery delays report", "Spreadsheet automation"]


def need(text, shown_by=""):
    return {"need": text, "shown_by": shown_by}


# ---------- fit: requirements shown, out of requirements listed ----------

@pytest.mark.parametrize("percent, label", [(0, "none"), (39, "none"), (40, "stretch"), (59, "stretch"),
                                            (60, "near"), (79, "near"), (80, "direct"), (100, "direct")])
def test_fit_label_boundaries(percent, label):
    assert jobs.fit_label(percent) == label


def test_fit_counts_only_achievements_the_user_has():
    f = jobs.fit([need("SQL", "Delivery delays report"), need("Python", "An achievement they do not have"), need("Tableau")], MINE)
    assert f["percent"] == 33 and f["label"] == "none"
    assert f["shown"] == [{"need": "SQL", "achievement": "Delivery delays report"}]
    assert f["gaps"] == ["Python", "Tableau"]


def test_fit_ignores_case_and_outer_spaces_and_keeps_the_users_spelling():
    f = jobs.fit([need("SQL", "  delivery DELAYS report ")], MINE)
    assert f["percent"] == 100 and f["label"] == "direct"
    assert f["shown"] == [{"need": "SQL", "achievement": "Delivery delays report"}]


@pytest.mark.parametrize("requirements", [[], [need("  ")], [need("")]])
def test_fit_is_none_without_requirements(requirements):
    assert jobs.fit(requirements, MINE) is None  # no score, rather than a division by zero


def test_fit_rounds_to_a_whole_percent():
    f = jobs.fit([need("a", MINE[0]), need("b", MINE[1]), need("c")], MINE)
    assert f["percent"] == 67 and f["label"] == "near"


def test_fit_lists_at_most_three_shown_and_three_gaps():
    f = jobs.fit([need(f"s{i}", MINE[0]) for i in range(5)] + [need(f"g{i}") for i in range(4)], MINE)
    assert f["percent"] == 56
    assert [s["need"] for s in f["shown"]] == ["s0", "s1", "s2"] and f["gaps"] == ["g0", "g1", "g2"]


def test_fit_with_no_achievements_is_all_gaps():
    f = jobs.fit([need("SQL", "Delivery delays report")], [])
    assert f["percent"] == 0 and f["label"] == "none" and f["gaps"] == ["SQL"]
