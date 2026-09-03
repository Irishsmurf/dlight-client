# dlight-client — Claude Code instructions

## Documentation policy

**Any change to the public API (new method, changed signature, new parameter,
behaviour change, or deprecation) MUST be accompanied by a corresponding update
to the documentation in `docs/`.** At minimum update:

- `docs/api/<class>.md` — add or update the method/property entry
- The relevant user guide page (e.g. `docs/user-guide/device-control.md`) —
  update any affected tables or examples

Docs are built with MkDocs Material (`mkdocs build --strict`). Run a build to
confirm there are no broken references before committing.

## Agent skills

### Issue tracker

Issues live as GitHub issues in `Irishsmurf/dlight-client`, managed with the
`gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

The five canonical triage labels are used as-is. See
`docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` and `docs/adr/` at the repo root (created lazily;
neither exists yet). See `docs/agents/domain.md`.
