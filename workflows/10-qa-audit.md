# Workflow: the weekly QA audit

Objective: score every property in the portfolio on the same yardstick this
week, and get a fix list in front of each GM.

Every score and every action comes straight from `data/imports/*.csv`
(`tools/signals.py` + `tools/scorecard.py`). No model touches a score or a
finding - see `docs/how-it-works.md` for the exact rubric.

## Steps

1. **Load this week's signals, if you have not already.** Export the five
   CSVs to `data/imports/` (see `docs/integrations.md` for the exact
   columns): `room_status.csv`, `journey_touchpoints.csv`, `reviews.csv`,
   `ota_listings.csv`, `booking_flow_checks.csv`. `make demo` uses the
   bundled fixtures instead - skip this step while you are still exploring.
   A property with none of the five files covering it is queued
   `needs_human` with that reason, not silently scored 100.

2. **Run it.**
   ```bash
   python3 tools/run.py --once
   python3 tools/run.py --once --property aurora-ridge   # just one property
   python3 tools/run.py --once --force                    # recompute this week
   ```
   `--once` is the default; plain `python3 tools/run.py --once` covers every
   property in `config/agent.yaml: properties`, whatever is due. Re-running
   the same ISO week is a no-op unless you pass `--force` - see
   "Idempotency" in `docs/how-it-works.md`.

3. **See what it scored.**
   ```bash
   python3 tools/review.py list --status pending_review
   python3 tools/review.py show <id>
   ```
   The draft has a subject, a markdown digest body (`body_md`), the scores
   by category, every finding, and the action list. Read the ordering back
   to the hotel: flagship first, then weakest overall first - the point is
   the gap between houses, not any one number in isolation.

4. **Decide, per property.**
   ```bash
   python3 tools/review.py approve <id>
   python3 tools/review.py edit <id> --body-file my-version.txt [--subject "New subject"]
   python3 tools/review.py reject <id> --reason "wrong period"
   ```

5. **Send it.**
   ```bash
   python3 tools/review.py send
   ```
   In `mode: shadow` (the default) this is blocked and says so - see
   `docs/safety.md`. In `mode: live`, this actually emails the GM named in
   `config/agent.yaml: properties[].gm_email`.

## If a property says "needs a person to look first"

Either `config/agent.yaml: properties[].gm_email` is blank for that property
(falls back to `contacts.escalation_email`, and is flagged rather than
silently sent to a stranger), or none of the five signal files covered that
property this week. Both are printed on the scorecard's warnings.

## Rules

- One item per `(property, ISO week)` - see "Idempotency" in
  `docs/how-it-works.md`.
- The six score categories, the owner map, and the collector thresholds are
  all in `config/agent.yaml` - a threshold change is provable: change the
  number, re-run, and read the new finding.
- A `praise` finding never becomes an action - see
  `docs/how-it-works.md` "Porting buildActionList".
