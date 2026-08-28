# Workflow: working the review queue

Objective: turn a queued scorecard digest into a decision - approve, edit,
or reject - and, once approved and once the hotel is live, actually send it.

Nothing reaches a GM without going through this. `mode: shadow` blocks
`send_email` for every item, approved or not - see `docs/safety.md` for the
full guard. There is no exception: an approval made in shadow is recorded
and stands, ready to send the moment the hotel goes live, but it does not
get sent while shadow is on.

## Steps

1. **See what is waiting.**
   ```bash
   make review
   ```
   Each line shows the item id, its status (`pending_review` or
   `needs_human`), the property name, the ISO week, and the overall score.

2. **Read one in full.**
   ```bash
   python3 tools/review.py show <id>
   ```
   This prints the property, the scores by category, every finding, the
   action list, and the full event history for that item. Read the findings
   and the action list back to the hotel in plain language - do not paste
   the raw JSON at them.

3. **Decide.**
   ```bash
   python3 tools/review.py approve <id>
   python3 tools/review.py edit <id> --body-file my-version.txt [--subject "New subject"]
   python3 tools/review.py reject <id> --reason "wrong period"
   ```
   `edit` records the before/after pair as a `learnings` row - this repo has
   no coach layer that reads it (the roster does not give this agent one;
   see `docs/how-it-works.md` "Sub-agents"), but it is there if you add one.

4. **Send what was approved (live mode only).**
   ```bash
   python3 tools/review.py send
   ```
   This claims everything `approved`/`edited`, calls the email adapter's
   `send()`, and records the result. While `mode: shadow`, every attempt
   prints `blocked ... (approval kept)` and nothing leaves the machine - the
   approval is not lost, it is just waiting for go-live.

5. **A failed send.** `send` marks the item `failed` with the error
   attached.
   ```bash
   python3 tools/review.py retry <id>
   ```
   re-queues it for another attempt after you have fixed the cause (usually
   a mailbox credential - `make doctor` will say which).

## Rules

- Only `tools/review.py` writes `approved` / `edited` / `rejected`.
- A property flagged `needs_human` (no GM contact configured, or no signal
  data this week - see `workflows/10-qa-audit.md`) still shows a full
  scorecard; read it before deciding what to do, it is not an error state.
- Confirm with the hotel before sending anything, even an approved item, the
  first few times. `workflows/90-go-live.md` covers when to stop doing that.
