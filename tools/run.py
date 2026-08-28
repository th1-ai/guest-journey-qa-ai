#!/usr/bin/env python3
"""tools/run.py - Guest Journey QA AI's main loop.

    python3 tools/run.py --once
    python3 tools/run.py --once --dry-run
    python3 tools/run.py --once --property aurora-ridge
    python3 tools/run.py --once --force
    python3 tools/run.py --watch

One pass: import this week's signal CSVs from `data/imports/` (if present),
build a deterministic scorecard and action list for every property in
`config/agent.yaml: properties`, and queue one GM digest per property
(`kind: qa_audit`) for review. Idempotent per (property, ISO week) - re-run
any time; nothing is drafted twice for the same week unless you pass
--force. Nothing is sent here or anywhere else in this repo -
workflows/80-review.md and docs/safety.md cover the review queue and the
shadow/live switch.

Exit codes: 0 ok, 1 a real error. There is no exit code 3: the only model
call (the portfolio note) is cosmetic and is skipped outright on the
`interactive` provider rather than pausing the run for it - see
docs/how-it-works.md "The one LLM call".
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.adapters.base import AdapterError  # noqa: E402
from core.config import ConfigError, load_settings  # noqa: E402
from core.llm import LLMError, complete  # noqa: E402
from core.log import Run, get_logger, summary_line  # noqa: E402
from core.store import Store  # noqa: E402
from core.templates import build_prompt  # noqa: E402

import scorecard  # noqa: E402
import signals  # noqa: E402
import store_ext  # noqa: E402

log = get_logger("run")
NOTE_SCHEMA = json.loads((REPO_ROOT / "prompts" / "schemas" / "portfolio-note.json")
                        .read_text(encoding="utf-8"))


def current_period_label(today: date | None = None) -> str:
    """ISO week label, e.g. "2026-W35" - see docs/how-it-works.md design
    decision #1 (weekly, not monthly)."""
    iso = (today or date.today()).isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def build_property_scorecard(settings, store, prop: dict
                             ) -> tuple[scorecard.ScorecardResult, list[scorecard.Action], bool]:
    """Returns (result, actions, has_signal). See tools/signals.py for each
    finding-builder and docs/how-it-works.md "The five signals"."""
    property_id = prop["id"]
    room_rows = store_ext.load_room_status(store, property_id)
    touchpoint_rows = store_ext.load_touchpoints(store, property_id)
    review_rows = store_ext.load_reviews(store, property_id)
    ota_rows = store_ext.load_ota_listings(store, property_id)
    booking_rows = store_ext.load_booking_flow(store, property_id)
    has_signal = any((room_rows, touchpoint_rows, review_rows, ota_rows, booking_rows))

    cfg = settings.agent_get("signals", {}) or {}
    rs_cfg = cfg.get("room_status", {}) or {}
    tp_cfg = cfg.get("journey_touchpoints", {}) or {}
    rv_cfg = cfg.get("reviews", {}) or {}
    ota_cfg = cfg.get("ota_listings", {}) or {}
    bf_cfg = cfg.get("booking_flow", {}) or {}

    findings = []
    findings += signals.room_readiness_findings(
        room_rows, ready_by=rs_cfg.get("ready_by", "15:00"),
        medium_if_late_at_most=int(rs_cfg.get("medium_if_late_at_most", 2)))
    findings += signals.touchpoint_findings(
        touchpoint_rows, late_tolerance_hours=float(tp_cfg.get("late_tolerance_hours", 2)))
    findings += signals.review_theme_findings(
        review_rows, window_days=int(rv_cfg.get("window_days", 30)),
        min_count_for_theme=int(rv_cfg.get("min_count_for_theme", 2)),
        low_rating_threshold=float(rv_cfg.get("low_rating_threshold", 3)),
        today=signals.anchor_date(review_rows))
    findings += signals.ota_listing_findings(
        ota_rows, high_impact_fields=tuple(ota_cfg.get("high_impact_fields")
                                           or ("opening_hours", "phone", "price", "address")))
    findings += signals.booking_flow_findings(
        booking_rows, default_max_seconds=float(bf_cfg.get("default_max_seconds", 90)))

    labels = settings.agent_get("score_categories") or scorecard.DEFAULT_LABELS
    owners = settings.agent_get("owners") or scorecard.DEFAULT_OWNER_BY_AREA
    result = scorecard.build_scorecard(property_id, prop.get("name", property_id),
                                       findings, labels=labels)
    if not has_signal:
        result.warnings.insert(0, f"No signal data was found for {result.property_name} "
                                  f"this week - nothing was imported. See "
                                  f"docs/integrations.md.")
    actions = scorecard.build_action_list(findings, owners=owners)
    return result, actions, has_signal


def get_portfolio_note(settings, store, ordered: list[scorecard.ScorecardResult],
                       period: str, *, dry_run: bool) -> str | None:
    """Optional 2-3 sentence note across the whole portfolio. Never gates a
    decision - see docs/how-it-works.md "The one LLM call". Skipped entirely
    (not paused) on the `interactive` provider, and swallowed on any other
    failure, so a run always finishes with or without it."""
    if dry_run or not settings.agent_get("portfolio_note.enabled", False):
        return None
    if settings.llm.provider == "interactive":
        return None
    summary = {"period": period,
              "properties": [{"name": r.property_name, "overall": r.overall} for r in ordered]}
    try:
        prompt = build_prompt("portfolio-note", settings=settings, item=summary,
                              knowledge=settings.agent_get("portfolio_note.knowledge"),
                              fixture_id="portfolio-note")
        result = complete("portfolio-note", prompt, schema=NOTE_SCHEMA, settings=settings,
                          store=store, effort="low", fixture_id="portfolio-note")
        return (result.data or {}).get("note")
    except LLMError as exc:
        log.warn("portfolio note skipped", error=str(exc)[:200])
        return None


def one_pass(settings, store, *, only_property: str | None, force: bool,
            dry_run: bool, import_signals: bool = True) -> tuple[int, dict]:
    """``import_signals=False`` is what tools/demo.py uses: it seeds the five
    tables from fixtures/inbound/signals/ itself and must never also read a hotel's
    own data/imports/*.csv, or `make demo` would stop being immune to
    whatever the hotel has already imported for real."""
    stats = {"processed": 0, "drafted": 0, "needs_human": 0, "sent": 0, "skipped": 0}
    with Run("qa-audit", settings, store) as run:
        if import_signals and not dry_run:
            imports_dir = REPO_ROOT / "data" / "imports"
            imported = store_ext.import_signals_csv(store, imports_dir)
            if any(imported.values()):
                log.info("imported signal csvs", **imported)
        elif import_signals and dry_run:
            # --dry-run never imports (see docs/how-it-works.md "Idempotency" and
            # the module docstring on store_ext.import_signals_csv) - every score
            # below is computed against data/agent.db exactly as it stood before
            # this run, not against today's data/imports/*.csv. Say so plainly:
            # a fresh/empty database previews as a flat 100/100, which reads as
            # "everything's fine" rather than "nothing has been imported yet".
            imports_dir = REPO_ROOT / "data" / "imports"
            waiting = store_ext.preview_import_counts(imports_dir)
            waiting_files = [f for f, n in waiting.items() if n > 0]
            print(f"[dry-run] previewing against data/agent.db as it stands right now - "
                 f"--dry-run never imports data/imports/*.csv. "
                 + (f"{len(waiting_files)}/5 signal file(s) are sitting there unread "
                    f"({', '.join(waiting_files)}) - run `python3 tools/run.py --once` "
                    f"once (without --dry-run) first if you want this preview to reflect "
                    f"them." if waiting_files else
                    "No signal CSVs are waiting there either, so a fresh data/agent.db "
                    "previews as a flat 100/100 for every property - that is a "
                    "placeholder, not a real score."))

        properties = settings.agent_get("properties", []) or []
        flagship = settings.agent_get("flagship")
        group_name = settings.agent_get("group_name") or settings.hotel.name
        period = current_period_label()

        built = {}
        for prop in properties:
            if only_property and prop["id"] != only_property:
                continue
            result, actions, has_signal = build_property_scorecard(settings, store, prop)
            built[prop["id"]] = (prop, result, actions, has_signal)

        ordered = scorecard.order_properties([r for _, r, _, _ in built.values()], flagship)
        labels = settings.agent_get("score_categories") or scorecard.DEFAULT_LABELS

        for sr in ordered:
            prop, result, actions, has_signal = built[sr.property_id]
            unique_key = f"{prop['id']}:{period}"
            existing = store.get_by_external("qa_audit", unique_key)
            if existing is not None and not force:
                stats["skipped"] += 1
                continue
            if existing is not None and existing.review_status not in ("new", "pending_review",
                                                                       "needs_human"):
                # A human has already approved, edited, rejected or sent this
                # week's digest. --force must never rewrite content behind a
                # decision that was already made - see docs/how-it-works.md
                # "Idempotency". Recompute next week, or reject it first.
                stats["skipped"] += 1
                continue
            if dry_run:
                print(f"[dry-run] would draft the {period} scorecard for {prop['name']} "
                     f"(overall {result.overall}/100, {len(actions)} action(s)). No "
                     f"business data is written; the run log records a dry_run entry.")
                stats["processed"] += 1
                continue

            gm_email = prop.get("gm_email") or settings.contacts.escalation_email
            needs_human = (not has_signal) or (not gm_email)
            body = scorecard.render_digest_md(group_name, result, actions, period,
                                              labels=labels)
            draft = {"subject": f"{prop['name']} - Weekly QA scorecard ({period})",
                    "to": gm_email, "body_md": body, "scores": result.scores,
                    "overall": result.overall,
                    "findings": [f.as_dict() for f in result.findings],
                    "action_list": [a.as_dict() for a in actions],
                    "warnings": result.warnings}
            item = store.upsert_item(
                "qa_audit", unique_key, kind="qa_audit", unique_key=unique_key,
                payload={"property_id": prop["id"], "property_name": prop["name"],
                        "period": period, "gm_email": gm_email})
            store.set_fields(item.id, draft=draft)
            status = "needs_human" if needs_human else "pending_review"
            if item.review_status == status:
                updated = item
            elif item.review_status == "new":
                updated = store.transition(item.id, status, actor="agent",
                                           detail={"overall": result.overall})
            else:
                # pending_review <-> needs_human is not a legal FSM edge (see
                # core/store.py TRANSITIONS) - both are actionable states a
                # human already sees in `make review`, so a --force recompute
                # refreshes the draft in place rather than crashing or
                # silently reclassifying it.
                log.warn("recomputed status differs from queued status - left "
                        "as-is, only the draft was refreshed", item_id=item.id,
                        queued_as=item.review_status, recomputed_as=status)
                updated = item
            stats["processed"] += 1
            stats["drafted"] += 1
            if needs_human:
                stats["needs_human"] += 1
            log.info("queued", item_id=updated.id, property=prop["id"],
                     overall=result.overall, status=updated.review_status)

        note = get_portfolio_note(settings, store, ordered, period, dry_run=dry_run)
        if note:
            print(f"\nPortfolio note: {note}")
        reaped = store.reap_stuck_sending()
        if reaped:
            log.warn("reaped stuck sends", count=len(reaped))
        run.stats = dict(stats)
    return 0, stats


def _print_summary(stats: dict, mode: str) -> None:
    """`core.log.summary_line()` prints processed/drafted/sent only - it has
    no idea about `skipped` (a property this week's scorecard already exists
    for, per `stats["skipped"]` in `one_pass`). Print that count as a second
    line here instead of inside core, since `core/` is shared by every agent
    in the family and most of them have no `skipped` concept at all. See
    README.md "Troubleshooting & FAQ" for the exact text this prints."""
    print(summary_line(stats, mode))
    skipped = stats.get("skipped", 0)
    if skipped:
        print(f"{skipped} skipped - already scored this week for "
             f"{'that property' if skipped == 1 else 'those properties'}. "
             f"Pass --force to recompute.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--once", action="store_true", help="run a single pass (default)")
    mode_group.add_argument("--watch", action="store_true",
                            help="keep running on the configured interval")
    parser.add_argument("--dry-run", action="store_true",
                        help="compute everything, write nothing, even in live mode")
    parser.add_argument("--property", default=None,
                        help="audit only this property id (default: every property)")
    parser.add_argument("--force", action="store_true",
                        help="recompute this week's scorecard even if one is already queued")
    parser.add_argument("--provider", default=None, help="override llm.provider for this run")
    parser.add_argument("--poll-seconds", type=int, default=None,
                        help="override the --watch interval (default: agent.yaml or 21600)")
    args = parser.parse_args(argv)

    try:
        settings = load_settings(provider=args.provider, dry_run=args.dry_run)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 1

    store = Store(settings)
    store_ext.migrate(store)
    try:
        if args.watch:
            poll_seconds = args.poll_seconds or int(settings.agent_get("poll_seconds", 21600))
            while True:
                code, stats = one_pass(settings, store, only_property=args.property,
                                       force=args.force, dry_run=args.dry_run)
                _print_summary(stats, settings.mode)
                if code != 0:
                    return code
                time.sleep(poll_seconds)
        code, stats = one_pass(settings, store, only_property=args.property,
                               force=args.force, dry_run=args.dry_run)
        _print_summary(stats, settings.mode)
        return code
    except AdapterError as exc:
        print(f"integration error: {exc}", file=sys.stderr)
        print("Run `make doctor` to see what is missing and how to fix it.", file=sys.stderr)
        return 1
    except LLMError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
