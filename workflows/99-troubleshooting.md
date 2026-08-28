# Workflow: troubleshooting

Read the whole error before doing anything - every tool here is written to
say what broke and what to do about it. If you fix something not covered
below, add it here.

## `make doctor` shows a FAIL

Each `FAIL` line has a `->` fix hint right under it. Common ones:

- **`hotel identity`: name is still 'Hotel Aurora'.** Expected on a fresh
  clone. Edit `config/hotel.yaml`.
- **`portfolio`: no properties configured.** Copy
  `config/agent.example.yaml` to `config/agent.yaml` - it ships with four
  sample properties.
- **`llm provider`: claude-code selected but `claude` is not on PATH.**
  Install Claude Code, or switch `llm.provider` to `interactive` or
  `anthropic` in `config/hotel.yaml`. This only affects the optional
  portfolio note - every score still works with no provider at all.
- **An adapter shows FAIL, not warn.** `universal`/`built` adapters fail
  loud when misconfigured (a `warn` is reserved for stubs). Read the
  `detail` column - it names the missing file or variable.

## `make demo` does not print `DEMO OK`

- Make sure `make setup` ran first (`.venv` must exist).
- `tools/demo.py` forces `llm.provider=mock` and reads
  `fixtures/inbound/signals/*.json` - if you deleted or renamed those
  files, restore them from git.
- Read the traceback if there is one; `tools/demo.py` does not swallow
  errors on purpose, so a fixture problem shows up immediately.

## `make run` says "0 processed, 4 skipped"

Not an error. This week's scorecard for every property already exists -
see "Idempotency" in `docs/how-it-works.md`. Pass `--force` to recompute
it (useful right after fixing a bad CSV import), or wait for next week.

## A property is always `needs_human`

Either `config/agent.yaml: properties[].gm_email` is blank for it, or none
of the five `data/imports/*.csv` files had a row for that property's id
this week. Both reasons are printed on the scorecard's `warnings`
(`python3 tools/review.py show <id>`).

## A score does not look right

Every score is traceable: read the `findings` on that item
(`python3 tools/review.py show <id>`), then check `config/agent.yaml:
signals` for the threshold that produced it (e.g. `room_status.ready_by`,
`reviews.min_count_for_theme`). Change the threshold, re-run with
`--force`, and read the new finding - this is meant to be provable, not a
black box. See `docs/how-it-works.md` "Scoring rubric".

## An item is stuck at `sending`

A process died between claiming an item and finishing the send.
`tools/run.py` calls `core.store.Store.reap_stuck_sending()` on every pass,
which moves anything stuck for more than 30 minutes to `failed` so you see
it in the queue instead of it vanishing. Use
`python3 tools/review.py retry <id>` once the cause is fixed.

## `python3 tools/*.py` says `ModuleNotFoundError: No module named 'core'`

You ran it with a Python that is not the repo's virtualenv, or from outside
the repo root. Use `make run` / `make doctor` / etc. (they call
`.venv/bin/python` for you), or run `.venv/bin/python tools/run.py` directly
from the repo root.

## Still stuck

`data/logs/*.jsonl` has every decision the agent made, in order, with a run
id. `python3 tools/review.py show <id>` has the full event trail for one
item. If neither explains it, that is a real bug - describe exactly what
you ran and what you expected, and ask.
