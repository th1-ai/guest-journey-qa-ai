"""tools/signals.py - one finding-builder per guest-journey signal.

Each function takes the rows for ONE property (already filtered - see
tools/store_ext.py loaders) and returns `list[scorecard.Finding]`. Pure
functions: no I/O, no model call, no randomness - see
tests/test_qa_signals.py and docs/how-it-works.md "The five signals".

An empty `rows` list always returns `[]` (no signal this week), never a
finding - the caller (tools/run.py) is what turns "no signal" into a
coverage warning, via scorecard.score_from_findings.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from statistics import mean

from scorecard import Finding

TRUE_STRINGS = {"1", "true", "yes", "y", "t"}


def _truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in TRUE_STRINGS


def _num(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


# --------------------------------------------------------------------------
# 1. room-readiness, from housekeeping data
# --------------------------------------------------------------------------
def room_readiness_findings(rows: list[dict], *, ready_by: str = "15:00",
                            medium_if_late_at_most: int = 2) -> list[Finding]:
    """A room is "late" if it has no ready time, its ready time is after
    ``ready_by``, or it is flagged ``out_of_order``."""
    if not rows:
        return []
    late = [r for r in rows if r.get("status") == "out_of_order"
           or not r.get("ready_time") or str(r["ready_time"]) > ready_by]
    if not late:
        return [Finding("room", f"All {len(rows)} room(s) checked were guest-ready "
                        f"by {ready_by}.", "praise")]
    severity = "medium" if len(late) <= medium_if_late_at_most else "high"
    example = late[0].get("room", "?")
    note = (f"{len(late)} of {len(rows)} room(s) checked were not guest-ready by "
           f"{ready_by} (for example room {example}).")
    return [Finding("room", note, severity)]


# --------------------------------------------------------------------------
# 2. pre-arrival comms, from journey touchpoints
# --------------------------------------------------------------------------
def touchpoint_findings(rows: list[dict], *, late_tolerance_hours: float = 2.0) -> list[Finding]:
    """One finding per touchpoint TYPE (booking_confirmation, welcome_message, ...)."""
    if not rows:
        return []
    by_type: dict[str, list[dict]] = {}
    for r in rows:
        by_type.setdefault(str(r.get("touchpoint", "unknown")), []).append(r)

    findings: list[Finding] = []
    for touchpoint, group in by_type.items():
        total = len(group)
        missing = [r for r in group if r.get("sent_offset_hours") in (None, "")]
        sent = [r for r in group if r not in missing]
        late = [r for r in sent
               if _num(r.get("sent_offset_hours")) - _num(r.get("expected_offset_hours"))
               > late_tolerance_hours]
        if missing:
            findings.append(Finding("arrival",
                f"{len(missing)} of {total} \"{touchpoint}\" message(s) were never sent "
                f"this week.", "high"))
        elif late:
            findings.append(Finding("arrival",
                f"{len(late)} of {total} \"{touchpoint}\" message(s) went out more than "
                f"{late_tolerance_hours:g}h later than planned.", "medium"))
        else:
            findings.append(Finding("arrival",
                f"Every \"{touchpoint}\" message this week went out on time.", "praise"))
    return findings


# --------------------------------------------------------------------------
# 3. review themes - the complaint that keeps coming back
# --------------------------------------------------------------------------
def review_theme_findings(rows: list[dict], *, window_days: int = 30,
                          min_count_for_theme: int = 2, low_rating_threshold: float = 3.0,
                          today: date | None = None) -> list[Finding]:
    """Group recent reviews by `category`; a recurring low rating is a
    finding, a recurring high rating is praise. No LLM: the "theme" is the
    category tag on the review row, and the note quotes the most recent
    example rather than summarising free text."""
    if not rows:
        return []
    cutoff = (today or date.today()) - timedelta(days=window_days)
    recent = [r for r in rows if _parse_date(r.get("date")) and _parse_date(r["date"]) >= cutoff]
    by_category: dict[str, list[dict]] = {}
    for r in recent:
        cat = str(r.get("category") or "").strip()
        if cat:
            by_category.setdefault(cat, []).append(r)

    findings: list[Finding] = []
    for category, group in by_category.items():
        if len(group) < min_count_for_theme:
            continue
        ratings = [_num(r.get("rating")) for r in group]
        low = [r for r in group if _num(r.get("rating")) <= low_rating_threshold]
        avg = mean(ratings)
        if len(low) >= min_count_for_theme:
            severity = "high" if avg <= 2.5 else "medium"
            example = sorted(low, key=lambda r: r.get("date", ""))[-1]
            note = (f"{len(low)} of {len(group)} reviews mentioning {category} in the "
                   f"last {window_days} days rated {low_rating_threshold:g} or below - "
                   f"most recent: \"{example.get('text', '').strip()}\"")
            findings.append(Finding(category, note, severity))
        elif avg >= 4.0:
            note = (f"{len(group)} reviews mentioning {category} in the last "
                   f"{window_days} days averaged {avg:.1f}/5 - consistently praised.")
            findings.append(Finding(category, note, "praise"))
    return findings


def _parse_date(value) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)[:10]).date()
    except ValueError:
        return None


def anchor_date(rows: list[dict]) -> date:
    """The latest review date in `rows`, or today if there are none.

    `review_theme_findings` filters to the last `window_days` before
    `today`. Fixtures carry fixed calendar dates, so anchoring on wall-clock
    `date.today()` would make `make demo` (and a re-run months later) drift
    out of the window and silently stop finding anything - see
    docs/how-it-works.md. Callers (tools/run.py, tools/demo.py) pass this as
    `today=` instead of relying on the default.
    """
    dates = [d for d in (_parse_date(r.get("date")) for r in rows) if d]
    return max(dates) if dates else date.today()


# --------------------------------------------------------------------------
# 4. OTA listing content parity
# --------------------------------------------------------------------------
def ota_listing_findings(rows: list[dict], *,
                         high_impact_fields: tuple[str, ...] = ("opening_hours", "phone",
                                                                "price", "address")) -> list[Finding]:
    """One finding per mismatched (channel, field) pair. A field in
    ``high_impact_fields`` (guests could show up at the wrong time or pay the
    wrong price) is `high`; anything else (photos, description wording) is
    the cosmetic `low` severity - see docs/how-it-works.md for why this repo
    keeps a `low` severity the source demo did not use."""
    if not rows:
        return []
    mismatches = [r for r in rows if not _truthy(r.get("match"))]
    if not mismatches:
        return [Finding("brand", f"All {len(rows)} listing field(s) checked matched your "
                        f"canonical listing across every channel.", "praise")]
    findings = []
    for r in mismatches:
        field = str(r.get("field", "field"))
        severity = "high" if field in high_impact_fields else "low"
        note = (f"{r.get('channel', 'a channel')} lists {field} as "
               f"\"{r.get('listed_value', '')}\", not \"{r.get('canonical_value', '')}\".")
        findings.append(Finding("brand", note, severity))
    return findings


# --------------------------------------------------------------------------
# 5. website and booking flow
# --------------------------------------------------------------------------
def booking_flow_findings(rows: list[dict], *, default_max_seconds: float = 90.0) -> list[Finding]:
    """A broken step is always `high`; a slow-but-working step is `medium`;
    an all-clear run is `praise`. Reported under the area "booking" - an
    extra key the six fixed categories do not cover, appended after them and
    falling to the default owner (General Manager) - see
    docs/how-it-works.md "The open score schema"."""
    if not rows:
        return []
    findings = []
    for r in rows:
        step = str(r.get("step", "step"))
        seconds = _num(r.get("seconds"))
        max_seconds = _num(r.get("max_seconds"), default_max_seconds) or default_max_seconds
        if _truthy(r.get("broken")):
            findings.append(Finding("booking",
                f"The \"{step}\" step of the booking flow did not complete - a guest "
                f"cannot finish a booking there.", "high"))
        elif seconds > max_seconds:
            findings.append(Finding("booking",
                f"The \"{step}\" step took {seconds:.0f}s, over the {max_seconds:.0f}s "
                f"budget.", "medium"))
    if findings:
        return findings
    total = sum(_num(r.get("seconds")) for r in rows)
    return [Finding("booking", f"The booking flow completed in {total:.0f}s across "
                   f"{len(rows)} step(s), inside budget throughout.", "praise")]
