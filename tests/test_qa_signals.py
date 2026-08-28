"""Unit tests for tools/signals.py - one finding-builder per guest-journey
signal. Every test feeds plain dict rows and checks the returned
`scorecard.Finding` list; no store, no settings, no I/O."""

from __future__ import annotations

from datetime import date

import signals


def test_room_readiness_no_rows_is_no_signal():
    assert signals.room_readiness_findings([]) == []


def test_room_readiness_all_on_time_is_praise():
    rows = [{"room": "1", "status": "clean", "ready_time": "13:00"},
           {"room": "2", "status": "inspected", "ready_time": "14:30"}]
    out = signals.room_readiness_findings(rows, ready_by="15:00")
    assert len(out) == 1 and out[0].severity == "praise" and out[0].area == "room"


def test_room_readiness_a_couple_late_is_medium():
    rows = [{"room": "1", "ready_time": "13:00"}, {"room": "2", "ready_time": "16:00"}]
    out = signals.room_readiness_findings(rows, ready_by="15:00", medium_if_late_at_most=2)
    assert out[0].severity == "medium"
    assert "1 of 2" in out[0].note


def test_room_readiness_many_late_or_out_of_order_is_high():
    rows = [{"room": "1", "ready_time": None}, {"room": "2", "status": "out_of_order"},
           {"room": "3", "ready_time": "17:00"}]
    out = signals.room_readiness_findings(rows, ready_by="15:00", medium_if_late_at_most=2)
    assert out[0].severity == "high"


def test_touchpoint_missing_is_high_and_beats_late():
    rows = [{"touchpoint": "welcome_message", "expected_offset_hours": 24,
            "sent_offset_hours": None},
           {"touchpoint": "welcome_message", "expected_offset_hours": 24,
            "sent_offset_hours": 30}]
    out = signals.touchpoint_findings(rows, late_tolerance_hours=2)
    assert len(out) == 1 and out[0].severity == "high" and "never sent" in out[0].note


def test_touchpoint_late_only_is_medium():
    rows = [{"touchpoint": "welcome_message", "expected_offset_hours": 24,
            "sent_offset_hours": 30}]
    out = signals.touchpoint_findings(rows, late_tolerance_hours=2)
    assert out[0].severity == "medium"


def test_touchpoint_on_time_is_praise_per_type():
    rows = [{"touchpoint": "booking_confirmation", "expected_offset_hours": 1,
            "sent_offset_hours": 0.5},
           {"touchpoint": "welcome_message", "expected_offset_hours": 24,
            "sent_offset_hours": 24}]
    out = signals.touchpoint_findings(rows)
    assert len(out) == 2 and all(f.severity == "praise" for f in out)
    assert {f.area for f in out} == {"arrival"}


def test_review_theme_recurring_low_rating_is_a_finding():
    rows = [{"category": "fnb", "rating": 3, "text": "cold food", "date": "2026-08-01"},
           {"category": "fnb", "rating": 3, "text": "slow service", "date": "2026-08-05"}]
    out = signals.review_theme_findings(rows, min_count_for_theme=2,
                                        today=date(2026, 8, 10))
    assert len(out) == 1 and out[0].area == "fnb" and out[0].severity == "medium"


def test_review_theme_boundary_average_2_5_is_high():
    rows = [{"category": "service", "rating": 2, "date": "2026-08-01", "text": "a"},
           {"category": "service", "rating": 3, "date": "2026-08-02", "text": "b"}]
    out = signals.review_theme_findings(rows, min_count_for_theme=2,
                                        today=date(2026, 8, 10))
    assert out[0].severity == "high"    # avg 2.5 <= 2.5


def test_review_theme_below_min_count_produces_nothing():
    rows = [{"category": "spa", "rating": 1, "date": "2026-08-01", "text": "a"}]
    out = signals.review_theme_findings(rows, min_count_for_theme=2,
                                        today=date(2026, 8, 10))
    assert out == []


def test_review_theme_high_rating_is_praise():
    rows = [{"category": "spa", "rating": 5, "date": "2026-08-01", "text": "a"},
           {"category": "spa", "rating": 5, "date": "2026-08-02", "text": "b"}]
    out = signals.review_theme_findings(rows, min_count_for_theme=2,
                                        today=date(2026, 8, 10))
    assert out[0].severity == "praise"


def test_review_theme_outside_window_is_ignored():
    rows = [{"category": "fnb", "rating": 1, "date": "2026-01-01", "text": "old"},
           {"category": "fnb", "rating": 1, "date": "2026-01-02", "text": "old2"}]
    out = signals.review_theme_findings(rows, min_count_for_theme=2, window_days=30,
                                        today=date(2026, 8, 10))
    assert out == []


def test_anchor_date_uses_latest_row_not_wallclock():
    rows = [{"date": "2020-01-01"}, {"date": "2020-01-15"}, {"date": "2019-12-01"}]
    assert signals.anchor_date(rows) == date(2020, 1, 15)


def test_anchor_date_empty_rows_falls_back_to_today():
    assert signals.anchor_date([]) == date.today()


def test_ota_listing_high_impact_field_mismatch_is_high():
    rows = [{"channel": "Google", "field": "opening_hours", "canonical_value": "24h",
            "listed_value": "9-5", "match": False}]
    out = signals.ota_listing_findings(rows)
    assert out[0].severity == "high" and out[0].area == "brand"


def test_ota_listing_cosmetic_field_mismatch_is_low():
    rows = [{"channel": "TripAdvisor", "field": "photos", "canonical_value": "12",
            "listed_value": "6", "match": False}]
    out = signals.ota_listing_findings(rows)
    assert out[0].severity == "low"


def test_ota_listing_all_match_is_praise():
    rows = [{"channel": "Google", "field": "phone", "canonical_value": "+1", "match": True}]
    out = signals.ota_listing_findings(rows)
    assert len(out) == 1 and out[0].severity == "praise"


def test_booking_flow_broken_step_is_high_regardless_of_timing():
    rows = [{"step": "payment", "seconds": 0, "max_seconds": 60, "broken": True}]
    out = signals.booking_flow_findings(rows)
    assert out[0].severity == "high" and "did not complete" in out[0].note


def test_booking_flow_slow_step_is_medium():
    rows = [{"step": "search", "seconds": 150, "max_seconds": 30, "broken": False}]
    out = signals.booking_flow_findings(rows)
    assert out[0].severity == "medium"


def test_booking_flow_all_within_budget_is_praise():
    rows = [{"step": "search", "seconds": 20, "max_seconds": 30},
           {"step": "payment", "seconds": 25, "max_seconds": 45}]
    out = signals.booking_flow_findings(rows)
    assert len(out) == 1 and out[0].severity == "praise" and out[0].area == "booking"


def test_signals_use_the_bundled_fixtures_and_ridge_is_weakest(signals_dir):
    import json
    import scorecard

    def load(name):
        return json.loads((signals_dir / name).read_text())

    def findings_for(pid):
        rows = {n: [r for r in load(f"{n}.json") if r["property_id"] == pid]
               for n in ("room_status", "journey_touchpoints", "reviews", "ota_listings",
                        "booking_flow_checks")}
        return (signals.room_readiness_findings(rows["room_status"])
               + signals.touchpoint_findings(rows["journey_touchpoints"])
               + signals.review_theme_findings(rows["reviews"],
                                               today=signals.anchor_date(rows["reviews"]))
               + signals.ota_listing_findings(rows["ota_listings"])
               + signals.booking_flow_findings(rows["booking_flow_checks"]))

    scores = {pid: scorecard.build_scorecard(pid, pid, findings_for(pid)).overall
             for pid in ("aurora-city", "marlow-house", "aurora-bay", "aurora-ridge")}
    assert scores["aurora-ridge"] < scores["aurora-city"]
    assert scores["aurora-ridge"] < scores["marlow-house"]
    assert scores["aurora-ridge"] == min(scores.values())
