# Guardrails and safety

This agent never talks to your guests. It reads signals about the guest
journey (housekeeping status, pre-arrival sends, reviews, OTA listings,
booking-flow timing) and writes a scorecard and an action list for your own
GMs. Everything below is built in, not optional, and this page explains
what it does and what is left for you to decide.

## The hard boundary

**"Scores and reports; fixing is for the GM (or the other agents)."** That
is the roster's own promise, and it is enforced in code, not just in prose:

- `tools/scorecard.py` never writes to a PMS, never posts a review reply,
  never changes a listing. It has no write method for any operational
  system - the only write in this whole repo is the GM digest email.
- `tools/signals.py` only ever reads rows already imported into
  `data/agent.db` - it never calls a live PMS, review platform or OTA API.
- A `praise` finding is never actioned - see `docs/how-it-works.md`
  "Porting buildActionList".

## The two modes

| Mode | What happens |
|---|---|
| `shadow` (default) | The agent reads, thinks, drafts and queues. It **never** sends a message and **never** writes to your PMS. Approving, editing or rejecting a draft records your decision (and teaches the agent) but sends nothing. At go-live, `python3 tools/review.py stale` clears that shadow-era queue so nothing old goes out by surprise. |
| `live` | Items you approved are really sent. Everything else still waits. |

`mode` lives in `config/hotel.yaml`. It is a global kill switch: flipping it back
to `shadow` stops every outbound action immediately, mid-schedule, with no other
change. `config/agent.yaml` can be stricter than `hotel.yaml`, never looser.

Two more brakes:

- `make run ARGS="--dry-run"` computes everything and writes nothing, even in
  live mode. Use it when you change a prompt. It never imports
  `data/imports/*.csv` either (that write counts too) - it previews against
  `data/agent.db` as it already stands, and says so on screen. See
  `docs/how-it-works.md` "Idempotency".
- `review.require_approval_for` in `config/hotel.yaml` lists the actions that
  need a human even in live mode. The defaults are `send_email`, `send_message`,
  `pms_write`, `payment`, `publish`. Shortening that list is how you hand the
  agent more rope, one action at a time.

Every outbound action in the codebase goes through one function,
`core/review.py:assert_write_allowed`. There is no second path.

## The review queue

Nothing reaches a GM without passing through the queue.

```bash
make review                       # what is waiting
python3 tools/review.py show <id>  # the full scorecard, findings and action list
python3 tools/review.py approve <id>
python3 tools/review.py edit <id> --body-file my-version.txt
python3 tools/review.py reject <id> --reason "wrong period"
```

An item moves `new -> pending_review` (or `needs_human`, when no GM contact
is configured or no signal data reached this property this week) and then
waits. Only `tools/review.py` can write `approved`, `edited` or `rejected`;
only `tools/run.py` can write `sent`. A crash between "about to send" and
"sent" is picked up on the next pass and shown to you as failed rather than
silently retried.

**Your edits teach it.** When you rewrite a digest, the before and after are
stored as a `learnings` row. This repo does not ship a coach that reads it
(see `docs/how-it-works.md` "Sub-agents"), but it is there if you add one.

## What the agent will not do

- Send a digest while `mode: shadow`.
- Send a digest a human has not approved, when the action needs approval.
- Take a payment, issue a refund, move money, write to a PMS, or post a
  review reply. This repo has no code path that does any of those.
- Fix anything. `tools/scorecard.py` writes an owned, dated action - never
  the fix itself.
- Score a category from thin air. A category with no signal this week
  scores 100 with a coverage warning attached, never a guessed number - see
  `docs/how-it-works.md` "Scoring rubric".
- Prioritise a property, or bury one, based on anything but its own overall
  score. The ordering rule (flagship first, then weakest first) is fixed -
  see `docs/how-it-works.md` "Portfolio ordering".

## Data handling

**What leaves your machine.** There is exactly one model call in this repo,
the optional portfolio note (off by default) - see `docs/how-it-works.md`
"The one LLM call". With `llm.provider: anthropic` or `claude-code` and the
note turned on, each property's name and its `overall` score go to
Anthropic - never a finding, never a review's text, never a guest's name.
With `llm.provider: mock` or `interactive`, or with the note left off,
nothing leaves the machine at all.

**What is stored, and where.** Everything lives in `data/` inside this folder:
`agent.db` (SQLite), `logs/*.jsonl`, `exports/`. `data/` is gitignored. There is
no cloud service behind this repo and no telemetry.

**Card numbers are redacted on the way in.** A review's `text` field passes
through `core/redact.py` before it is stored - a payment card number would
be replaced with `[CARD REDACTED ****1234]`, and labelled CVC and expiry
values in the same text go with it. Detection requires a real card prefix
and a valid Luhn checksum, so booking references survive. IBANs are masked
the same way. Nothing you can do in config turns this off. In practice a
guest review almost never contains a card number - this exists because the
`text` field is guest-written free text, and this repo treats all
guest-written free text the same way regardless of source.

**Retention.** `privacy.retention_days` (default 365) is how long processed items
stay in the database. Deleting `data/agent.db` deletes everything the agent knows.

## GDPR, in practice

If you are in the EU or handle EU guests' data, the short version:

- **You are the controller.** This software runs on your machine, under your
  control, on your data. TH1 does not receive it.
- **Your model provider is a processor, when the portfolio note is on.** If
  you use the `anthropic` or `claude-code` provider and
  `portfolio_note.enabled: true`, Anthropic processes a property name and a
  score on your behalf - nothing else in this repo ever reaches a model.
  Check their data processing terms and record them in your processing
  register if this applies to you.
- **Purpose and minimisation.** `data/imports/reviews.csv` is the one signal
  most likely to carry a guest's own words. Export only what
  `tools/signals.py` reads (`property_id, rating, category, text, date`) -
  do not add a guest's name or email to that file.
- **Right to erasure.** A guest asking for their review text to be deleted
  means removing their row from `data/agent.db`'s `qa_reviews` table and
  from `data/imports/reviews.csv`. Ask your Claude session:
  *"Delete the qa_reviews row(s) matching this review text, and tell me how
  many rows you removed."*
- **Retention.** Set `privacy.retention_days` to what your own policy says, not
  to the default.

This is a practical summary, not legal advice.

## AI transparency, in practice

The EU AI Act (Article 50) requires telling a person when they are
interacting with an AI system, unless it is obvious. This agent does not
interact with a person in real time and does not talk to guests at all -
its output goes to your own GMs as a periodic scorecard and action list,
which is a different situation from a guest-facing chat reply. It is still
good practice to say plainly that the digest was prepared automatically, so
`knowledge/signature.md` carries a line to that effect by default:

> Prepared automatically from this week's imported signals ... reviewed by
> our team before it was sent.

If you ever extend this agent to message a guest directly (there is no such
path in v1 - see "The hard boundary" above), add a guest-facing disclosure
line before doing so, along the lines of: *"This message was prepared with
AI assistance and reviewed by our team. Reply any time to reach a person
directly."* Keep an escape hatch in it - a guest who wants a human should
never have to work out how to get one.

## Subscription or API: an honest note

Two ways to pay for the reasoning:

**Your Claude Code subscription** (`llm.provider: claude-code` or `interactive`).
Flat monthly cost, no per-message billing. This is genuinely the cheapest way to
run a small hotel's agent.

The caveat, plainly: a personal Pro or Max subscription is intended for
interactive use, and Anthropic's usage policy and rate limits apply to automated
use of it. A handful of scheduled runs a day is a normal way to work. Pointing
a busy inbox at it around the clock is not, and you will hit rate limits at the
worst moment. Read the terms and decide for yourself.

**The Anthropic API** (`llm.provider: anthropic`). Pay per token, no ambiguity
about automated use, proper rate limits, and usage you can attribute. This is
the right answer for production volume. `make report` shows what you are
spending.

Start on the subscription while you are learning what the agent does. Move to the
API when it becomes part of how the hotel runs.

## If something goes wrong

1. `mode: shadow` in `config/hotel.yaml`, or `AGENT_MODE=shadow` in `.env`. Every
   outbound action stops on the next pass.
2. Remove the schedule (`crontab -e`, `launchctl unload`, or
   `systemctl disable --now <slug>.timer`).
3. `make doctor` to see what the agent thinks its state is.
4. `data/logs/*.jsonl` has every decision, with the run id, in order.
