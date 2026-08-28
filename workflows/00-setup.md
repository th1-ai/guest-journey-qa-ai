# Workflow: first-run setup

Objective: get Guest Journey QA AI from a fresh clone to a working demo,
then to a real portfolio, in one sitting.

## Steps

1. **Install and check.**
   ```bash
   make setup
   make doctor
   ```
   `make setup` creates the virtualenv, installs `requirements.txt`, and
   copies `.env.example` -> `.env` and every `config/*.example.yaml` ->
   `config/*.yaml` (only if those files do not exist yet). `make doctor`
   will show a `FAIL` on "hotel identity" right after setup - expected, the
   flagship property name is still the shipped placeholder ("Hotel Aurora").
   It will also `WARN` on "this week's signal imports" - also expected,
   there is no real data yet.

2. **Run the demo.** No credentials needed.
   ```bash
   make demo
   ```
   This seeds the bundled fixtures (an invented four-property portfolio,
   "Aurora Hospitality Group") and scores every property. Expect to see one
   line per property (overall score, band, action count), a note that
   nothing was sent (shadow mode), and the line `DEMO OK`. If you do not see
   that, stop and read `workflows/99-troubleshooting.md` before going
   further.

3. **Fill in the portfolio.** Edit `config/hotel.yaml` (your flagship
   property's name, address, contact, currency, timezone) and
   `config/agent.yaml: properties` (every property you audit, with its own
   `gm_email`) plus `config/agent.yaml: group_name` (your portfolio's own
   name - it heads every property's digest; `hotel.yaml: hotel.name` is only
   the flagship's own name and is the wrong thing to use here). Then:
   ```bash
   cp knowledge/property.example.md  knowledge/property.md
   cp knowledge/faq.example.md       knowledge/faq.md
   cp knowledge/signature.example.md knowledge/signature.md
   ```
   Edit the signature to your own sign-off; it is what appears on every
   weekly GM digest email.

4. **Check the six score categories and the owner map still make sense.**
   `config/agent.yaml: score_categories` and `owners` ship with the hotel
   defaults from the behavioural spec (Arrival / Room / Food & drink / Spa /
   Service / Brand standards, owned by Front Office / Executive Housekeeper
   / F&B / Spa / Duty / Marketing). For a restaurant, see "Customising" in
   `README.md`.

5. **Pick how the agent thinks.** `config/agent.yaml`'s `llm.provider`
   starts as `interactive`. The only reasoning step in this whole agent is
   an optional, off-by-default cosmetic portfolio note - everything else
   (every score, every finding, every action) is deterministic. See
   `docs/how-it-works.md` "The one LLM call" for when it is worth turning
   on (`portfolio_note.enabled: true`).

6. **Connect your real data (optional for now).** `docs/integrations.md`
   covers exactly which CSV export goes where for the five signals -
   `data/imports/room_status.csv`, `journey_touchpoints.csv`, `reviews.csv`,
   `ota_listings.csv`, and `booking_flow_checks.csv`. A property with none
   of the five imported this week is queued `needs_human` rather than shown
   a false all-clear score - see `docs/how-it-works.md` "Scoring rubric".
   Run `make doctor` after adding any of them.

7. **Re-check.**
   ```bash
   make doctor
   ```
   Once the flagship's name is real, `knowledge/property.md` exists, and at
   least one property has a signal source connected, move on to
   `workflows/10-qa-audit.md` to run the loop for real.
