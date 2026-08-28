# knowledge/

Unlike most agents in this family, the Inspector does not draft guest-facing
text and does not read this folder to decide anything - scoring and the
action list are pure arithmetic over `data/imports/*.csv` (see
`docs/how-it-works.md`). What lives here shapes only the words around the
GM digest: who reads it, what they already know, and how it signs off.

## What to put here

| File | What it holds |
|---|---|
| `property.md` | Which properties are in the portfolio and who reads this agent's output - useful context for anyone (including your Claude session) working on this repo. Not read by any prompt. |
| `faq.md` | Questions a GM or a group ops person is likely to ask about how a score or an action was produced. Not read by any prompt. |
| `signature.md` | The sign-off on the weekly GM digest email. Plain text - this IS used, by every email `core/adapters/email_*.py` sends. |

Copy the `.example.md` files, rename them without `.example`, and fill them in:

```bash
cp knowledge/property.example.md  knowledge/property.md
cp knowledge/faq.example.md       knowledge/faq.md
cp knowledge/signature.example.md knowledge/signature.md
```

`knowledge/*.md` is gitignored (the `.example.md` files are not), because your
property notes are yours.

## How to write it

**Short sentences, concrete facts, no marketing language.** Nobody but your
own team reads any of this - the digest's numbers come from
`data/imports/*.csv`, not from here.

**Say what this agent does NOT do.** "Scores and reports; fixing is for the
GM" is worth repeating in your own words for anyone new who opens this repo,
including your own Claude session six months from now.

**Keep the signature current.** It is the only free text a GM sees outside
the scores, the findings and the action list themselves.

## Keeping it current

When the portfolio changes - a property added, sold, or a GM's contact
changes - change `config/agent.yaml: properties` first (that is what the
agent actually reads), then update `knowledge/property.md` to match so the
two do not drift apart.
