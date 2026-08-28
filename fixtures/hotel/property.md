# Property facts - Aurora Hospitality Group (fixture data)

This is sample data for `make demo` and the tests: a shorter copy of the
same invented portfolio described in `knowledge/property.example.md`. A real
clone of this repo fills in `knowledge/property.md` with its own facts.

- Group name: Aurora Hospitality Group
- Flagship: Hotel Aurora, 1 Example Street, 1000-001 Lisbon, Portugal
- Currency: EUR (see `config/hotel.example.yaml`)

## The portfolio (config/agent.example.yaml: properties)

| id | name | character |
|---|---|---|
| aurora-city (flagship) | Hotel Aurora | City hotel, 42 rooms, the group's flagship |
| marlow-house | The Marlow House | Small boutique house, 12 rooms |
| aurora-bay | Aurora Bay Inn | Seaside inn, 28 rooms |
| aurora-ridge | Aurora Ridge Lodge | Mountain lodge, 40 rooms - the property with the most open findings in the bundled fixtures |

## Who reads this agent's output

- Each property's GM: their own weekly scorecard and action list
  (`config/agent.yaml: properties[].gm_email`).
- Group ops: `make report` for the portfolio-wide average and trend.

This repo has no reservation or rate data of its own - the `pms` adapter is
only pinged for `make doctor`'s sake (this agent does not read reservations,
rates or availability). The signals it actually reads live in
`fixtures/inbound/signals/` and `data/imports/` - see `docs/integrations.md`.
