"""tools/scorecard.py - turn one property's findings into a scorecard and an
owned, dated action list. Deterministic, no LLM - see docs/how-it-works.md
"Scoring rubric" and "Porting buildActionList".

Every function here is a pure function over plain dataclasses: no I/O, no
model call, no randomness. Given the same findings you always get the same
scorecard and the same action list - that is what makes a threshold change
provable, and it is why this file is the one most heavily unit-tested (see
tests/test_qa_scorecard.py).

tools/run.py and tools/demo.py both call these functions, so the real loop
and the zero-credential walkthrough exercise exactly the same code.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: The six categories the source spec fixes, in display order. An extra key
#: (e.g. "booking" - see tools/signals.py:booking_flow_findings) is scored
#: and actioned like any other area but never moves `overall` - see
#: docs/how-it-works.md "The open score schema".
FIXED_CATEGORIES = ("arrival", "room", "fnb", "spa", "service", "brand")

DEFAULT_LABELS = {
    "arrival": "Arrival", "room": "Room", "fnb": "Food & drink",
    "spa": "Spa", "service": "Service", "brand": "Brand standards",
}

#: area -> owning role. "rooms" (plural) is kept alongside "room" because the
#: source spec's own table lists both spellings. Anything not listed here -
#: including every extra key - falls to DEFAULT_OWNER.
DEFAULT_OWNER_BY_AREA = {
    "arrival": "Front Office Manager",
    "room": "Executive Housekeeper", "rooms": "Executive Housekeeper",
    "fnb": "F&B Manager", "spa": "Spa Manager",
    "service": "Duty Manager", "brand": "Marketing Lead",
}
DEFAULT_OWNER = "General Manager"

#: Points a finding of each severity costs its category. See "Scoring rubric".
DEDUCTIONS = {"high": 9, "medium": 4, "low": 2, "praise": 0}

BAND_TEAL, BAND_BLUE, BAND_AMBER = "teal", "blue", "amber"


@dataclass
class Finding:
    area: str
    note: str
    severity: str  # high | medium | low | praise

    def as_dict(self) -> dict:
        return {"area": self.area, "note": self.note, "severity": self.severity}


@dataclass
class Action:
    action: str
    owner: str
    due: str

    def as_dict(self) -> dict:
        return {"action": self.action, "owner": self.owner, "due": self.due}


@dataclass
class ScorecardResult:
    property_id: str
    property_name: str
    scores: dict = field(default_factory=dict)     # area -> int (0-100)
    overall: int = 0
    findings: list = field(default_factory=list)     # list[Finding]
    warnings: list = field(default_factory=list)     # list[str]

    def as_dict(self) -> dict:
        return {"property_id": self.property_id, "property_name": self.property_name,
                "scores": self.scores, "overall": self.overall,
                "findings": [f.as_dict() for f in self.findings], "warnings": self.warnings}


def band_for(score: int) -> str:
    """>=90 teal, >=85 blue, else amber - the source scorecard's colour bands."""
    if score >= 90:
        return BAND_TEAL
    if score >= 85:
        return BAND_BLUE
    return BAND_AMBER


def score_from_findings(findings: list[Finding], *,
                        labels: dict[str, str] | None = None) -> tuple[dict[str, int], list[str]]:
    """One 0-100 score per area. Returns (scores, warnings).

    Every fixed category appears even with zero findings (scores 100, with a
    warning - "no news" is not the same claim as "checked and fine"). An
    extra area is only scored if at least one finding names it, and is
    appended after the fixed six in first-seen order.
    """
    labels = labels or DEFAULT_LABELS
    by_area: dict[str, list[Finding]] = {}
    for f in findings:
        by_area.setdefault(f.area, []).append(f)

    scores: dict[str, int] = {}
    warnings: list[str] = []
    for area, label in labels.items():
        area_findings = by_area.get(area, [])
        raw = 100 - sum(DEDUCTIONS.get(f.severity, 0) for f in area_findings)
        scores[area] = max(0, min(100, raw))
        if not area_findings:
            warnings.append(f"no signal touched {label} this week - the score assumes "
                            f"nothing was wrong, not that nothing was checked.")
    for area, area_findings in by_area.items():
        if area in scores:
            continue
        raw = 100 - sum(DEDUCTIONS.get(f.severity, 0) for f in area_findings)
        scores[area] = max(0, min(100, raw))
    return scores, warnings


def overall_from_scores(scores: dict[str, int],
                        categories: tuple[str, ...] = FIXED_CATEGORIES) -> int:
    """Rounded mean of the fixed categories only - an extra key never moves it."""
    present = [scores[c] for c in categories if c in scores]
    return round(sum(present) / len(present)) if present else 0


def build_scorecard(property_id: str, property_name: str, findings: list[Finding], *,
                    labels: dict[str, str] | None = None) -> ScorecardResult:
    labels = labels or DEFAULT_LABELS
    scores, warnings = score_from_findings(findings, labels=labels)
    overall = overall_from_scores(scores, tuple(labels.keys()))
    return ScorecardResult(property_id=property_id, property_name=property_name,
                           scores=scores, overall=overall, findings=findings, warnings=warnings)


def order_properties(results: list[ScorecardResult], flagship_id: str | None) -> list["ScorecardResult"]:
    """Flagship first, then weakest overall first.

    Ported verbatim from the source comment: "Grand Meridian leads (it is
    the property this demo is about), then weakest first - the Inspector's
    point is the gap between houses, not the winner."
    """
    return sorted(results, key=lambda r: (0 if r.property_id == flagship_id else 1, r.overall))


def build_action_list(findings: list[Finding], *, owners: dict[str, str] | None = None) -> list[Action]:
    """Deterministic action list from a scorecard's findings.

    Every non-praise finding becomes one owned, dated action. High severity
    is this week - ported line for line from the source `buildActionList`,
    see docs/how-it-works.md "Porting buildActionList".
    """
    owner_map = owners or DEFAULT_OWNER_BY_AREA
    default_owner = (owners or {}).get("default", DEFAULT_OWNER) if owners else DEFAULT_OWNER
    actions: list[Action] = []
    for f in findings:
        if f.severity == "praise":
            continue
        verb = "Fix" if f.severity == "high" else "Close out" if f.severity == "medium" else "Review"
        owner = owner_map.get(f.area, default_owner)
        due = "This week" if f.severity == "high" else "This month"
        actions.append(Action(action=f"{verb}: {f.note}", owner=owner, due=due))
    return actions


def render_digest_md(hotel_group_name: str, result: ScorecardResult, actions: list[Action],
                     period_label: str, *, labels: dict[str, str] | None = None) -> str:
    """Plain-markdown email body for one property's weekly GM digest."""
    labels = labels or DEFAULT_LABELS
    lines = [f"# {result.property_name} - Weekly QA scorecard", "",
             f"**{period_label}** · {hotel_group_name}", "",
             f"## Overall: {result.overall}/100 ({band_for(result.overall)})", ""]
    lines.append("## Scores by category")
    for area, label in labels.items():
        if area in result.scores:
            lines.append(f"- {label}: {result.scores[area]}/100 ({band_for(result.scores[area])})")
    for area, score in result.scores.items():
        if area not in labels:
            lines.append(f"- {area.title()}: {score}/100 ({band_for(score)})")
    if result.warnings:
        lines += ["", "## Coverage notes"]
        for w in result.warnings:
            lines.append(f"- {w}")
    lines += ["", "## Findings"]
    if not result.findings:
        lines.append("- No findings this week.")
    for f in result.findings:
        label = labels.get(f.area, f.area.title())
        lines.append(f"- **{label}** ({f.severity}): {f.note}")
    lines += ["", "## Action list"]
    if not actions:
        lines.append("- Nothing to action this week - every finding was praise, or there "
                     "were no findings.")
    for a in actions:
        lines.append(f"- [ ] {a.action} - **{a.owner}** · due {a.due}")
    return "\n".join(lines)
