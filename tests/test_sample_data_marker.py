"""A scorecard built while a system is still on the `mock` adapter must never
look like the portfolio's own data.

`core/store.py:upsert_item` tags such an item `_sample: True` (see
`core/adapters/__init__.py:is_sample_source`), and the review tools have to
show that. `config/agent.example.yaml: systems_used` narrows the check to
email - the only family this agent calls through `core/adapters` - so a
hotel that has connected its mailbox stops seeing the warning even though
`systems.pms` / `systems.messaging` stay mock forever.
"""

from __future__ import annotations

import argparse

import review
from core.store import Store


def _sample_item(settings, tmp_path):
    store = Store(settings, path=tmp_path / "test.db")
    item = store.upsert_item(
        "email", "aurora-city:2026-W35", kind="qa_audit",
        unique_key="aurora-city:2026-W35",
        payload={"property_id": "aurora-city", "property_name": "Hotel Aurora",
                "period": "2026-W35", "gm_email": "manager@example.com"})
    store.set_fields(item.id, draft={"subject": "Hotel Aurora - Weekly QA scorecard",
                                     "to": "manager@example.com", "overall": 72})
    store.transition(item.id, "pending_review", actor="agent")
    return store, store.get_item(item.id)


def test_mock_adapter_tags_the_scorecard_as_sample(isolated_settings, tmp_path):
    """A real (non-demo) run on a fresh clone reads fixtures, not a property."""
    settings = isolated_settings(provider="mock", mode="shadow")
    store, item = _sample_item(settings, tmp_path)
    try:
        assert item.is_sample is True
    finally:
        store.close()


def test_list_marks_sample_scorecards(isolated_settings, tmp_path, capsys):
    settings = isolated_settings(provider="mock", mode="shadow")
    store, _ = _sample_item(settings, tmp_path)
    try:
        assert review.cmd_list(store, argparse.Namespace(status=None, limit=50)) == 0
    finally:
        store.close()
    out = capsys.readouterr().out
    assert "[SAMPLE DATA]" in out
    assert "docs/integrations.md" in out


def test_show_marks_a_sample_scorecard(isolated_settings, tmp_path, capsys):
    settings = isolated_settings(provider="mock", mode="shadow")
    store, item = _sample_item(settings, tmp_path)
    try:
        assert review.cmd_show(store, argparse.Namespace(id=item.id)) == 0
    finally:
        store.close()
    assert "[SAMPLE DATA]" in capsys.readouterr().out
