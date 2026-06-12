## Agent skills

### Issue tracker

Issues tracked as GitHub Issues on `andrewesweet/ropey` via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Five canonical roles use their default label strings (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `CONTEXT.md` + `docs/adr/` at repo root. See `docs/agents/domain.md`.

### Documentation kept current

The README's install and catalogue sections are part of the distribution
contract (PRD "Distribution & human documentation"): update them in the
same change whenever a phase lands, a tool is added/renamed, or an install
mechanism changes.
