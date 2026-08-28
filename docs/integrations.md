# Connecting your systems

Every connector here is one of three things, and the table says which.

| Badge | Means |
|---|---|
| **built** | Written against the real API and tested against it. |
| **universal** | Works with any system through a common protocol: CSV, IMAP/SMTP, a webhook. |
| **stub** | Interface only. Calling it raises a clear error with a recipe for adding it. |

Check what is actually working right now:

```bash
make doctor
```

## What this agent actually reads and writes

The whole audit runs on five weekly exports, not a live API. That mirrors
how a QA pass actually works across a portfolio: someone runs a housekeeping
report, pulls last month's reviews, checks the OTA listings, times the
booking flow - all periodic, all bulk. The five files arrive as CSVs in
`data/imports/` and are loaded into `data/agent.db` by `tools/store_ext.py`,
not through `core/adapters`. The `core/adapters` registry is used for
exactly one thing in this repo: **sending** the GM digest (Email).

### The five signal exports (universal - always works, start here)

<a id="signals"></a>

| File | Feeds | Columns |
|---|---|---|
| `data/imports/room_status.csv` | Room category | `property_id, room, status, ready_time` (`status`: `clean \| dirty \| inspected \| out_of_order`; `ready_time` blank if not yet ready) |
| `data/imports/journey_touchpoints.csv` | Arrival category | `property_id, reservation_ref, touchpoint, expected_offset_hours, sent_offset_hours` (blank `sent_offset_hours` = never sent) |
| `data/imports/reviews.csv` | Fnb / Spa / Service / whatever `category` says | `property_id, rating, category, text, date` |
| `data/imports/ota_listings.csv` | Brand standards category | `property_id, channel, field, canonical_value, listed_value, match` (`match`: `true`/`false`) |
| `data/imports/booking_flow_checks.csv` | Booking (an extra, open category - see `docs/how-it-works.md`) | `property_id, step, seconds, max_seconds, broken` |

`property_id` must match an id in `config/agent.yaml: properties`. Each
file is a **snapshot of "what is true this week"**, not an accumulating
ledger: importing a fresh export replaces that file's table in full (see
`tools/store_ext.py:import_signals_csv`), so overwrite the file in
`data/imports/` with the new week's export rather than appending to it.

**You do not run a separate import command.** `python3 tools/run.py --once`
re-imports every file above automatically, at the start of the pass. A file
that does not exist yet leaves its table untouched - importing just one
fixed file after a bad export does not wipe the other four. `make doctor`
also runs the same loaders (against a throwaway copy, never your real
database) so it can tell you exactly how many rows it found in each file,
not just that the file exists.

**Where the data comes from in practice:**

- `room_status.csv` - export from your housekeeping/PMS system's room-status
  report, or from `list_housekeeping()` if your PMS adapter supports it
  (Cloudbeds does - ask your Claude session to wire a small export script).
- `journey_touchpoints.csv` - export from whatever sends your pre-arrival
  emails/messages (your PMS, your email platform, or this agent's sibling
  Front Desk AI's own send log).
- `reviews.csv` - export from Google/Booking.com/TripAdvisor/Vrbo, or from
  Review-Response AI's own `reviews` table if you also run that agent.
- `ota_listings.csv` - a manual or scripted comparison of your canonical
  listing (your own website, or a "source of truth" sheet) against each
  channel's live page. There is no crawler in this template - see
  "Implement your own" below if you want to automate the comparison itself.
- `booking_flow_checks.csv` - a manual timed run-through of your booking
  page, or a Playwright/Selenium script that times each step and writes a
  row per step. See "Implement your own" below for the recipe.

### Email - `systems.email.adapter`

<a id="email"></a>

| Adapter | Status | Needs | Notes |
|---|---|---|---|
| `mock` | universal | nothing | Writes to `data/exports/sent_email.jsonl`. What `make demo` uses (and never calls, since demo never sends). |
| `imap` | universal | mailbox + app password | Any provider. **Start here for real sends.** |
| `gmail` | built | Google OAuth desktop client | Adds Gmail labels and threads. |

This agent only ever calls `send()` - it never reads a mailbox.

**`imap` (start here).** In `.env`:

```
EMAIL_ADDRESS=qa@example.com
EMAIL_PASSWORD=            # an APP password, never your login password
IMAP_HOST=imap.example.com
SMTP_HOST=smtp.example.com
SMTP_PORT=587
```

**`gmail` setup (about ten minutes, once).** Choose this over `imap` when
you want Gmail labels and threads, or you are on Google Workspace with IMAP
disabled by policy.

1. In [Google Cloud Console](https://console.cloud.google.com/) create a
   project and enable the **Gmail API**.
2. Configure the OAuth consent screen (**Internal** if you are on Google
   Workspace, **External** + your own address as a test user otherwise).
3. Create an OAuth client of type **Desktop app** and download the JSON.
4. Save it as `credentials.json` in this repo's root folder (it is
   gitignored - never commit it).
5. Install the client libraries:
   ```bash
   .venv/bin/pip install google-api-python-client google-auth-oauthlib
   ```
6. Set `systems.email.adapter: gmail` in `config/hotel.yaml`, then run
   `make doctor`. The first run opens a browser once for you to sign in and
   writes `token.json` next to `credentials.json`.

Both adapters end the same way: the signature (`knowledge/signature.md`) is
appended to every send automatically - see `Email.with_signature()` in
`core/adapters/base.py`.

### PMS, Messaging - configured but not used by the core loop

<a id="pms"></a>
<a id="messaging"></a>

`systems.pms` and `systems.messaging` are configured (mock by default)
because `make doctor` checks every adapter, but neither is called by
`tools/run.py` or `tools/review.py` in v1 - this agent reads reservations
and rates through none of its five signals. Two obvious extensions if you
want them:

- **PMS `list_housekeeping()`** - if your PMS adapter supports it
  (Cloudbeds does), a small script that calls it and writes
  `room_status.csv` replaces the manual export entirely.
- **Messaging** - a WhatsApp/Slack ping to group ops when a property's
  overall score drops below a threshold week over week. `messaging_webhook`
  is the zero-setup way to try it.

### Sheets - `systems.sheets.adapter`

<a id="sheets"></a>

| Adapter | Status | Needs | Notes |
|---|---|---|---|
| `csv` | universal | nothing | `tools/report.py --export` writes `data/exports/qa_report.csv`. |
| `google` | built | service account JSON | A live shared spreadsheet instead. |

For `google`: enable the Sheets API, create a service account and a JSON
key, save it as `service_account.json`, and share your spreadsheet with the
service account's email address as an Editor. Set
`systems.sheets.spreadsheet_id` to the long id from the sheet's URL.

### Everything else

`pos`, `accounting`, `reviews` (the stub, distinct from `reviews.csv`
above), `calendar`, `payments`, `procurement`, `locks` and `courier` are
stubs, unused by this agent.

## Implement your own

<a id="implement-your-own"></a>

The two signals most worth automating are the booking-flow timing and the
OTA listing comparison - both are "run a script, write a CSV" jobs, not
adapter work, so there is no registry entry to add. Open `claude` in this
folder and paste:

> Read `docs/integrations.md#implement-your-own`. I want a script that logs
> into <your booking engine's URL> like a first-time guest, times each step
> from search to confirmation, and writes one row per step to
> `data/imports/booking_flow_checks.csv` in the shape `tools/store_ext.py`
> expects (`property_id, step, seconds, max_seconds, broken`). Use
> Playwright. Put it in `tools/scripts/` (not `tools/`, so it is clearly a
> helper, not part of the reviewed pipeline) and do not wire it into
> `tools/run.py` - I will run it myself and drop the CSV in place.

The same pattern works for `ota_listings.csv`: a script that reads your
canonical listing (your own website, or a small YAML file of true values)
and compares it against what each channel's page actually shows, then
writes one row per `(channel, field)` pair with `match: true/false`.

If you would rather build a real `core/adapters` integration (for example, a
live PMS `list_housekeeping()` call instead of a CSV export), the shape is:

**1. Copy the closest existing adapter.** `core/adapters/pms_cloudbeds.py`
for a real API with OAuth; `core/adapters/pms_csv.py` for the
"export-a-file" shape.

**2. Implement `ping()` and `capabilities()` first.**

```python
def ping(self) -> HealthCheck:
    """Never raises. Returns ok=False with a fix_hint a hotel can act on."""

def capabilities(self) -> set[str]:
    """The method names that actually do something on this adapter."""
```

**3. Implement the read**, mapping vendor fields onto plain dicts (this
agent's signal tables are plain dicts, not the dataclasses in
`core/adapters/base.py` - see `tools/store_ext.py`).

**4. Register it** in `core/adapters/__init__.py`'s `REGISTRY["pms"]` (or
whichever family), set the adapter name in `config/hotel.yaml`, and run
`make doctor`.

### Rules that matter

- **`ping()` never raises.** It returns `HealthCheck(ok=False, ...)` with a
  hint. A broken adapter must still produce a readable doctor table.
- **Every write is decorated** with `@guarded_write("<action>")`. No
  exceptions - see `core/adapters/base.py`.
- **Never log a credential.** `core/log.py` masks anything whose key looks
  like a secret, but do not rely on it.
- **Redact on ingestion.** Any free text a review or a finding carries
  through `tools/signals.py` is never a guest's payment detail - if your own
  review export could contain one, run it through `core.redact.redact()`
  before it reaches `data/imports/reviews.csv`.
- **Write a test.** Copy `tests/test_core_adapters_mock_csv.py`. It should
  run with no network: feed your parser a fixture, check what comes out.

### `core/` is shared

`core/` is identical in all 28 agents in this family. If you change
something in `core/`, keep it generic - a hotel-specific tweak belongs in
`tools/` or in your own adapter file, not in the shared runtime.
