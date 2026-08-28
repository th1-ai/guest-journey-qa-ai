"""Unit tests for tools/scorecard.py - the deterministic scoring rubric and
the ported `buildActionList` logic. Pure functions only, no store."""

from __future__ import annotations

import scorecard
from scorecard import Finding


def test_score_from_findings_deducts_by_severity():
    findings = [Finding("room", "two late rooms", "high")]
    scores, warnings = scorecard.score_from_findings(findings)
    assert scores["room"] == 100 - scorecard.DEDUCTIONS["high"]


def test_score_from_findings_floors_at_zero():
    findings = [Finding("room", "a", "high"), Finding("room", "b", "high"),
               Finding("room", "c", "high"), Finding("room", "d", "high"),
               Finding("room", "e", "high"), Finding("room", "f", "high"),
               Finding("room", "g", "high"), Finding("room", "h", "high"),
               Finding("room", "i", "high"), Finding("room", "j", "high"),
               Finding("room", "k", "high"), Finding("room", "l", "high")]
    scores, _ = scorecard.score_from_findings(findings)
    assert scores["room"] == 0


def test_score_from_findings_no_findings_in_a_fixed_category_scores_100_with_a_warning():
    scores, warnings = scorecard.score_from_findings([])
    assert all(v == 100 for v in scores.values())
    assert len(warnings) == len(scorecard.DEFAULT_LABELS)
    assert any("Spa" in w for w in warnings)


def test_score_from_findings_extra_key_is_appended_and_scored():
    findings = [Finding("booking", "broken step", "high")]
    scores, warnings = scorecard.score_from_findings(findings)
    assert scores["booking"] == 100 - scorecard.DEDUCTIONS["high"]
    assert not any("booking" in w.lower() for w in warnings)   # not a fixed category


def test_overall_ignores_extra_keys():
    scores = {**{c: 100 for c in scorecard.FIXED_CATEGORIES}, "booking": 0}
    assert scorecard.overall_from_scores(scores) == 100


def test_overall_is_rounded_mean_of_fixed_six():
    scores = {"arrival": 100, "room": 91, "fnb": 100, "spa": 100, "service": 100, "brand": 100}
    # mean = 98.5 -> banker's/half-up? Python round() is banker's rounding: 98.5 -> 98
    assert scorecard.overall_from_scores(scores) in (98, 99)


def test_band_for_thresholds():
    assert scorecard.band_for(95) == scorecard.BAND_TEAL
    assert scorecard.band_for(90) == scorecard.BAND_TEAL
    assert scorecard.band_for(87) == scorecard.BAND_BLUE
    assert scorecard.band_for(85) == scorecard.BAND_BLUE
    assert scorecard.band_for(84) == scorecard.BAND_AMBER


def test_order_properties_flagship_first_then_weakest():
    results = [
        scorecard.ScorecardResult("a", "A", overall=100),
        scorecard.ScorecardResult("b", "B", overall=60),
        scorecard.ScorecardResult("c", "C", overall=80),
    ]
    ordered = scorecard.order_properties(results, flagship_id="a")
    assert [r.property_id for r in ordered] == ["a", "b", "c"]


def test_order_properties_no_flagship_still_sorts_weakest_first():
    results = [scorecard.ScorecardResult("a", "A", overall=90),
              scorecard.ScorecardResult("b", "B", overall=70)]
    ordered = scorecard.order_properties(results, flagship_id=None)
    assert [r.property_id for r in ordered] == ["b", "a"]


def test_build_action_list_filters_praise():
    findings = [Finding("room", "great", "praise")]
    assert scorecard.build_action_list(findings) == []


def test_build_action_list_verb_and_due_by_severity():
    findings = [Finding("room", "note-h", "high"), Finding("fnb", "note-m", "medium"),
               Finding("brand", "note-l", "low")]
    actions = scorecard.build_action_list(findings)
    by_area = {a.action.split(":")[0]: a for a in actions}
    assert actions[0].action == "Fix: note-h" and actions[0].due == "This week"
    assert actions[1].action == "Close out: note-m" and actions[1].due == "This month"
    assert actions[2].action == "Review: note-l" and actions[2].due == "This month"


def test_build_action_list_owner_map_default_and_plural_room():
    findings = [Finding("arrival", "a", "high"), Finding("rooms", "b", "high"),
               Finding("booking", "c", "high")]
    actions = scorecard.build_action_list(findings)
    owners = {a.action[-1]: a.owner for a in actions}   # last char of note is a/b/c
    assert owners["a"] == "Front Office Manager"
    assert owners["b"] == "Executive Housekeeper"
    assert owners["c"] == scorecard.DEFAULT_OWNER    # unmapped area falls back


def test_build_action_list_respects_configured_owner_map():
    findings = [Finding("sustainability", "x", "medium")]
    custom = {"sustainability": "Facilities Manager", "default": "Someone Else"}
    actions = scorecard.build_action_list(findings, owners=custom)
    assert actions[0].owner == "Facilities Manager"


def test_build_action_list_respects_configured_default_owner():
    findings = [Finding("unknown-area", "x", "high")]
    custom = {"default": "Someone Else"}
    actions = scorecard.build_action_list(findings, owners=custom)
    assert actions[0].owner == "Someone Else"


def test_build_scorecard_end_to_end():
    findings = [Finding("room", "2 late rooms", "medium"),
               Finding("fnb", "great breakfast", "praise")]
    result = scorecard.build_scorecard("p1", "Property One", findings)
    assert result.property_id == "p1"
    assert result.scores["room"] == 96
    assert result.overall < 100


def test_render_digest_md_includes_property_and_actions():
    findings = [Finding("room", "2 late rooms", "high")]
    result = scorecard.build_scorecard("p1", "Property One", findings)
    actions = scorecard.build_action_list(findings)
    body = scorecard.render_digest_md("Aurora Hospitality Group", result, actions, "2026-W35")
    assert "Property One" in body
    assert "Fix: 2 late rooms" in body
    assert "Executive Housekeeper" in body
