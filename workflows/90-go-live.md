# Workflow: shadow to live

Objective: decide, together with the hotel, whether Guest Journey QA AI is
ready to send weekly digests to GMs on its own instead of only drafting
them - and make the change safely if so.

This is the hotel's decision, never the agent's. Do not suggest it until the
checklist below is genuinely true, and when you do raise it, say plainly
what changes.

## Checklist

- [ ] `make doctor` is clean (no `FAIL` lines). `warn` on `mode` is expected
      until you flip it.
- [ ] `config/hotel.yaml` has the real flagship property's name, address and
      contact details, and `config/agent.yaml: properties` lists every real
      property with a real `gm_email`. `config/agent.yaml: group_name` is
      your real portfolio name, not the shipped "Aurora Hospitality Group" -
      it heads every property's digest, not just the flagship's.
- [ ] `knowledge/property.md`, `knowledge/faq.md` and `knowledge/signature.md`
      exist and are accurate (not the shipped examples).
- [ ] At least one real week of `make run` (or `python3 tools/run.py --once`)
      has gone through the review queue against real imported signals, not
      just the demo fixtures.
- [ ] The hotel has read a few weeks of scorecards and trusts the scoring
      rubric well enough that a GM seeing the number cold would not be
      confused - `docs/how-it-works.md` "Scoring rubric" is worth walking
      through with them once.
- [ ] The hotel has decided on, and added, the disclosure line to
      `knowledge/signature.md` (`docs/safety.md` has suggested wording - this
      agent's output is staff-facing, not guest-facing, so the EU AI Act
      Article 50 guest-disclosure requirement does not apply the same way,
      but saying plainly that the digest was prepared automatically is still
      good practice).
- [ ] A real mailbox is connected (`systems.email.adapter: imap` or `gmail`)
      and `make doctor` shows it healthy - going live on the `mock` adapter
      would only ever touch the fixtures.
- [ ] Run the go-live step itself:
      ```bash
      python3 tools/review.py stale
      ```
      Everything queued during shadow gets marked `stale` rather than sent
      the moment you flip the switch - the shadow-era backlog was never
      reviewed against real send timing and could be out of date. Revive a
      still-relevant one with `python3 tools/review.py approve <id>`.

## Making the change

1. Edit `config/hotel.yaml`:
   ```yaml
   mode: live
   ```
2. `review.require_approval_for` still lists `send_email` by default - it
   should. Going live means **approved digests get sent**, not that this
   agent starts sending unapproved ones.
3. Run `make doctor` again to confirm.
4. Run one real pass and manually watch a send go through:
   ```bash
   python3 tools/run.py --once --property <one-id>
   python3 tools/review.py list
   python3 tools/review.py approve <id>
   python3 tools/review.py send
   ```
5. Tell the hotel exactly what just changed: an approved digest now actually
   emails that property's GM the next time someone (or a scheduled job)
   runs `python3 tools/review.py send` - it is still never automatic before
   that approval, and every scorecard still waits for a person first.

## Going back to shadow

```yaml
mode: shadow
```
in `config/hotel.yaml`, or `AGENT_MODE=shadow` in `.env` for one run. Either
stops every outbound action on the next pass, mid-schedule, with no other
change required.
