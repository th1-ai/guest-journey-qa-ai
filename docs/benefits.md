# Measuring the benefit

## The business case, from the roster

**Guest Journey QA AI ("The Inspector").** Standards drift silently across
a portfolio. This gives every GM a consistent, objective QA pass every week
instead of an annual audit. ROI: **+8% Brand-standard scores** (guest).

## What actually produces the +8%

Before: a portfolio mystery-audit is an annual (or less) exercise - an
outside firm visits each property once, writes a report, and the findings
are stale before the next visit. Standards drift between visits and nobody
notices until a review says so.

After: `python3 tools/run.py --once` scores every property against the same
six categories every week, from data the portfolio already generates
(housekeeping status, pre-arrival sends, reviews, OTA listings, booking-flow
timing). The claim behind "+8% brand-standard scores" is that a weekly,
comparable scorecard catches drift while it is still one finding, not a
pattern a guest has already noticed and reviewed publicly. This template
does not itself move any score - a human still has to act on the action
list. See "Honest caveats" below.

**Track it with `make report`**, which reads every scorecard on record
directly - no re-computation, just what happened:

```bash
make report
```

Shows: the portfolio average overall score, total actions raised, how many
properties are stuck `needs_human`, the edit rate on digests you have
reviewed, and the LLM spend (near-zero - the only call is the cosmetic
portfolio note).

## What to measure, concretely

| Metric | Where | What it tells you |
|---|---|---|
| Portfolio average overall | `make report` | Trending up over months is the closest proxy this template has for the roster's "+8%" claim - track it yourself over time, this repo does not store a rolling trend. |
| Weakest property, this week | the scorecard ordering itself | The point of the ordering rule - see `docs/how-it-works.md` "Portfolio ordering". |
| Actions raised vs. properties with zero findings | `make report` | A property with consistently zero findings across weeks either genuinely runs clean, or its signals stopped being imported - check the `warnings` list before assuming the former. |
| Human edit rate | `make report` | Falling over time means the digest wording is landing close to what the hotel would say itself. |
| Category with the most `needs_human` warnings | `python3 tools/review.py show <id>` across a few weeks | Which of the five signal sources is least connected right now - the next integration worth doing. |

## Honest caveats

- **This template does not itself close the loop.** `tools/scorecard.py`
  computes findings and actions; nothing here checks whether last week's
  action was actually done, and there is no per-action status - see
  `docs/how-it-works.md` "Design decisions" #4 (deliberately not added: a
  fake "done" checkbox with no real completion signal behind it is worse
  than no checkbox). The "+8%" only becomes attributable once a hotel adds
  its own follow-up step.
- **Two of the five signals are not automatable out of the box.** OTA
  listing comparison and booking-flow timing both need either a manual
  weekly check or a script you (or your Claude session) write - see
  `docs/integrations.md#implement-your-own`. Until then, those two
  categories' scores reflect however recently you last did the check.
- **A category with no findings scores 100.** That is "nothing was flagged
  wrong", not "nothing was wrong" - see `docs/how-it-works.md` "Scoring
  rubric". Do not read a 100 on a category with a coverage warning attached
  as a clean bill of health.
- **The deduction table is a design choice, not a formula from the source
  demo** - the original platform's scores were seeded rows with no rubric at
  all (see the behavioural spec's open question #10). Change
  `scorecard.DEDUCTIONS` if your hotel wants harsher or gentler scoring; the
  ordering rule and the action list stay the same either way.
