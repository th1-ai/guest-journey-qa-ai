"""Full-loop tests: tools/run.py:one_pass end to end with provider=mock,
plus the review queue and the shadow guard. Every test uses `isolated_settings`
(tests/conftest.py) so nothing here ever reads a hotel's own config or data."""

from __future__ import annotations

import argparse

import review
import run
import store_ext
from core.review import approve, list_queue, show, stale_backlog
from core.store import Store


def _seeded_store(settings):
    store = Store(settings)
    store_ext.migrate(store)
    store_ext.seed_fixtures(store, settings.root / "fixtures" / "inbound" / "signals")
    return store


def test_one_pass_queues_one_item_per_property(isolated_settings):
    settings = isolated_settings(provider="mock", mode="shadow")
    store = _seeded_store(settings)
    code, stats = run.one_pass(settings, store, only_property=None, force=False,
                               dry_run=False, import_signals=False)
    assert code == 0
    assert stats["processed"] == len(settings.agent_get("properties"))
    assert stats["drafted"] == stats["processed"]
    items = list_queue(store, kind="qa_audit", limit=50)
    assert len(items) == stats["processed"]


def test_flagship_and_weakest_property_are_findable(isolated_settings):
    settings = isolated_settings(provider="mock", mode="shadow")
    store = _seeded_store(settings)
    run.one_pass(settings, store, only_property=None, force=False, dry_run=False,
                import_signals=False)
    items = list_queue(store, kind="qa_audit", limit=50)
    ridge = next(i for i in items if (i.payload or {}).get("property_id") == "aurora-ridge")
    assert ridge.draft["overall"] < 100
    assert len(ridge.draft["action_list"]) > 0


def test_dedup_on_rerun_same_week(isolated_settings):
    settings = isolated_settings(provider="mock", mode="shadow")
    store = _seeded_store(settings)
    run.one_pass(settings, store, only_property=None, force=False, dry_run=False,
                import_signals=False)
    code, stats = run.one_pass(settings, store, only_property=None, force=False,
                               dry_run=False, import_signals=False)
    assert code == 0
    assert stats["processed"] == 0
    assert stats["skipped"] == len(settings.agent_get("properties"))


def test_force_recomputes_the_same_week(isolated_settings):
    settings = isolated_settings(provider="mock", mode="shadow")
    store = _seeded_store(settings)
    run.one_pass(settings, store, only_property=None, force=False, dry_run=False,
                import_signals=False)
    code, stats = run.one_pass(settings, store, only_property=None, force=True,
                               dry_run=False, import_signals=False)
    assert stats["processed"] == len(settings.agent_get("properties"))


def test_dry_run_writes_no_items(isolated_settings):
    settings = isolated_settings(provider="mock", mode="shadow", dry_run=True)
    store = _seeded_store(settings)
    run.one_pass(settings, store, only_property=None, force=False, dry_run=True,
                import_signals=False)
    assert list_queue(store, kind="qa_audit", limit=50) == []


def test_no_signal_property_is_needs_human(isolated_settings):
    settings = isolated_settings(provider="mock", mode="shadow")
    store = Store(settings)
    store_ext.migrate(store)   # no fixtures seeded - every property has zero signal
    code, stats = run.one_pass(settings, store, only_property=None, force=False,
                               dry_run=False, import_signals=False)
    assert stats["needs_human"] == stats["processed"] == len(settings.agent_get("properties"))


def test_demo_is_immune_to_a_decoy_csv_in_data_imports(isolated_settings, tmp_path):
    """The decoy-CSV test: a hotel's own data/imports/*.csv must never change
    what tools/demo.py-style calls (import_signals=False) produce."""
    settings = isolated_settings(provider="mock", mode="shadow")
    imports_dir = settings.root / "data" / "imports"
    imports_dir.mkdir(parents=True, exist_ok=True)
    (imports_dir / "room_status.csv").write_text(
        "property_id,room,status,ready_time\naurora-city,999,out_of_order,\n",
        encoding="utf-8")
    store = _seeded_store(settings)
    run.one_pass(settings, store, only_property=None, force=False, dry_run=False,
                import_signals=False)
    items = list_queue(store, kind="qa_audit", limit=50)
    city = next(i for i in items if (i.payload or {}).get("property_id") == "aurora-city")
    assert city.draft["overall"] == 100   # the decoy row was never imported


def test_shadow_blocks_send_and_keeps_the_approval(isolated_settings, capsys):
    settings = isolated_settings(provider="mock", mode="shadow")
    store = _seeded_store(settings)
    run.one_pass(settings, store, only_property=None, force=False, dry_run=False,
                import_signals=False)
    item = list_queue(store, kind="qa_audit", limit=1)[0]
    approve(store, item.id)

    result = review.cmd_send(store, settings, argparse.Namespace(limit=20))
    out = capsys.readouterr().out
    assert result == 1
    assert "approval kept" in out
    reloaded = show(store, item.id)["item"]
    assert reloaded["review_status"] == "approved"   # never moved to sent/failed for good


def test_review_edit_records_a_learning(isolated_settings):
    settings = isolated_settings(provider="mock", mode="shadow")
    store = _seeded_store(settings)
    run.one_pass(settings, store, only_property=None, force=False, dry_run=False,
                import_signals=False)
    item = list_queue(store, kind="qa_audit", limit=1)[0]
    body_file = settings.root / "edited.txt"
    body_file.write_text("A rewritten digest body.", encoding="utf-8")
    review.cmd_edit(store, argparse.Namespace(id=item.id, body_file=str(body_file),
                                              subject=None, note="tightened the wording"))
    reloaded = show(store, item.id)["item"]
    assert reloaded["review_status"] == "edited"
    assert reloaded["draft"]["body_md"] == "A rewritten digest body."


def test_go_live_stale_clears_the_shadow_era_queue(isolated_settings):
    settings = isolated_settings(provider="mock", mode="shadow")
    store = _seeded_store(settings)
    run.one_pass(settings, store, only_property=None, force=False, dry_run=False,
                import_signals=False)
    before = len(list_queue(store, kind="qa_audit", limit=50))
    moved = stale_backlog(store)
    assert len(moved) == before
    assert list_queue(store, kind="qa_audit", status="pending_review", limit=50) == []
    assert list_queue(store, kind="qa_audit", status="needs_human", limit=50) == []
    assert len(list_queue(store, kind="qa_audit", status="stale", limit=50)) == before


def test_portfolio_note_is_skipped_not_paused_on_interactive(isolated_settings):
    """The one LLM call never uses exit-code-3 pending - see docs/how-it-works.md
    "The one LLM call". Proven here rather than only asserted in prose."""
    settings = isolated_settings(provider="interactive", mode="shadow")
    settings.agent["portfolio_note"] = {"enabled": True}
    store = _seeded_store(settings)
    note = run.get_portfolio_note(settings, store, [], "2026-W35", dry_run=False)
    assert note is None
    pending_dir = settings.root / "data" / "pending"
    assert not pending_dir.exists() or list(pending_dir.iterdir()) == []


def test_portfolio_note_mock_provider_returns_the_fixture(isolated_settings):
    settings = isolated_settings(provider="mock", mode="shadow")
    settings.agent["portfolio_note"] = {"enabled": True}
    store = _seeded_store(settings)
    note = run.get_portfolio_note(settings, store, [], "2026-W35", dry_run=False)
    assert note and "Aurora Ridge Lodge" in note


def test_force_never_overwrites_an_already_approved_item(isolated_settings):
    """Regression: --force used to crash with IllegalTransition when an item
    had already moved past pending_review/needs_human (e.g. approved) - see
    docs/how-it-works.md "Idempotency". Now it must skip that item instead."""
    settings = isolated_settings(provider="mock", mode="shadow")
    store = _seeded_store(settings)
    run.one_pass(settings, store, only_property=None, force=False, dry_run=False,
                import_signals=False)
    item = list_queue(store, kind="qa_audit", limit=1)[0]
    approve(store, item.id)

    code, stats = run.one_pass(settings, store, only_property=None, force=True,
                               dry_run=False, import_signals=False)
    assert code == 0   # no IllegalTransition traceback
    assert stats["skipped"] >= 1
    reloaded = show(store, item.id)["item"]
    assert reloaded["review_status"] == "approved"   # never touched


def test_force_on_an_undecided_item_refreshes_the_draft_without_crashing(isolated_settings):
    """Regression: recomputing an untouched item whose bucket flips between
    pending_review and needs_human is not a legal FSM edge - run.py must
    refresh the draft in place rather than raise IllegalTransition."""
    settings = isolated_settings(provider="mock", mode="shadow")
    store = Store(settings)
    store_ext.migrate(store)   # no signals yet - every property is needs_human
    run.one_pass(settings, store, only_property=None, force=False, dry_run=False,
                import_signals=False)
    item = list_queue(store, kind="qa_audit", limit=1)[0]
    assert item.review_status == "needs_human"

    store_ext.seed_fixtures(store, settings.root / "fixtures" / "inbound" / "signals")
    code, stats = run.one_pass(settings, store, only_property=None, force=True,
                               dry_run=False, import_signals=False)
    assert code == 0
    reloaded = show(store, item.id)["item"]
    assert reloaded["draft"]["overall"] is not None   # draft was refreshed
    assert reloaded["review_status"] in ("pending_review", "needs_human")   # never crashed


def test_digest_header_uses_group_name_not_flagship_hotel_name(isolated_settings):
    """Regression: render_digest_md used to be called with settings.hotel.name
    (the flagship's own guest-facing name), so every property's digest -
    including other properties - was headed with the flagship's name instead
    of the portfolio's. See docs/how-it-works.md design decision #3."""
    settings = isolated_settings(provider="mock", mode="shadow")
    settings.agent["group_name"] = "Test Portfolio Group"
    store = _seeded_store(settings)
    run.one_pass(settings, store, only_property=None, force=False, dry_run=False,
                import_signals=False)
    items = list_queue(store, kind="qa_audit", limit=50)
    for item in items:
        body = item.draft["body_md"]
        assert "Test Portfolio Group" in body
        assert f"· {settings.hotel.name}" not in body


def test_digest_header_falls_back_to_hotel_name_when_group_name_unset(isolated_settings):
    settings = isolated_settings(provider="mock", mode="shadow")
    settings.agent.pop("group_name", None)
    store = _seeded_store(settings)
    run.one_pass(settings, store, only_property=None, force=False, dry_run=False,
                import_signals=False)
    item = list_queue(store, kind="qa_audit", limit=1)[0]
    assert f"· {settings.hotel.name}" in item.draft["body_md"]


def test_dry_run_on_fresh_db_prints_a_clear_no_import_notice(isolated_settings, capsys,
                                                              monkeypatch):
    """Finding 5: --dry-run never imports data/imports/*.csv (see
    docs/how-it-works.md "Idempotency"), so a fresh database must not look
    like a silent, real 100/100 - the run has to say plainly that it never
    read the CSVs sitting there."""
    settings = isolated_settings(provider="mock", mode="shadow", dry_run=True)
    # tools/run.py's REPO_ROOT is a module-level constant (real repo path);
    # match production, where it and settings.root are always the same path.
    monkeypatch.setattr(run, "REPO_ROOT", settings.root)
    imports_dir = settings.root / "data" / "imports"
    imports_dir.mkdir(parents=True, exist_ok=True)
    (imports_dir / "room_status.csv").write_text(
        "property_id,room,status,ready_time\naurora-city,101,dirty,\n", encoding="utf-8")
    store = Store(settings)
    store_ext.migrate(store)
    run.one_pass(settings, store, only_property=None, force=False, dry_run=True,
                import_signals=True)
    out = capsys.readouterr().out
    assert "never imports data/imports" in out
    assert "room_status.csv" in out


def test_print_summary_reports_skipped_count(capsys):
    """Finding 4: core.log.summary_line() never prints `skipped` - run.py's
    own _print_summary() must, since README's FAQ documents that a hotel can
    read it off the terminal."""
    run._print_summary({"processed": 0, "drafted": 0, "sent": 0, "skipped": 3}, "shadow")
    out = capsys.readouterr().out
    assert "0 items processed, 0 drafted, 0 sent (shadow)" in out
    assert "3 skipped" in out


def test_print_summary_omits_skipped_line_when_zero(capsys):
    run._print_summary({"processed": 1, "drafted": 1, "sent": 0, "skipped": 0}, "shadow")
    out = capsys.readouterr().out
    assert "skipped" not in out
