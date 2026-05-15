# Letters of Light

Letters of Light is a weekly, peace-centered spiritual content spine.

The Sunday-ready layer is intentionally text-first:

- canonical weekly letter markdown with JSON frontmatter
- local-only email preview
- printable packet
- jail/in-person discussion packet
- human approval checklist
- append-only weekly letter and transition ledgers

No external sending, scraping, network call, or irreversible action belongs in this layer.

## Commands

```powershell
python -m app.letters_of_light.weekly_cli validate --letter docs/letters_of_light/letters/2026-05-17.md
python -m app.letters_of_light.weekly_cli render --letter docs/letters_of_light/letters/2026-05-17.md --out-dir data/outputs/letters_of_light/2026-05-17
python -m app.letters_of_light.weekly_cli register --letter docs/letters_of_light/letters/2026-05-17.md --actor-id local-operator
```

Use `transition` only after human review:

```powershell
python -m app.letters_of_light.weekly_cli transition --letter-id lol_2026_05_17 --from-state draft --to-state reviewed --actor-id local-operator
```
