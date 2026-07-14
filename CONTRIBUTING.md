# Contributing to SynthPost

## Workflow

1. Create a focused branch from the current default branch.
2. Run `make doctor` and establish a green `make check` baseline.
3. Refactor incrementally around tests; preserve unrelated working-tree changes.
4. Add a regression/contract test for every behavior or bug changed.
5. Run the proportional checks below and describe exact results in the PR.

## Code organization

- Domain contracts belong in `pipeline/models.py`; HTTP request contracts belong in `pipeline/api/schemas.py`.
- Use-case behavior belongs in the matching feature package. Provider-specific code stays in its adapter.
- Queue stages declare lane/input/output/ownership in `pipeline/stages.py`.
- Avoid new `utils`, `helpers`, manager singletons, direct environment reads, import-time work, and untyped patches.
- Keep the Studio API client typed; presentation components should not call `fetch` directly.
- Follow `avatar-engine/AGENTS.md` inside that subsystem.

## Quality gates

```bash
make config-check
make test
make test-avatar       # when avatar code/contracts change
make typecheck
make build
make smoke             # when manifest/timeline/render behavior changes
```

Default tests are deterministic and offline. Never make full Blender renders or paid provider calls part of `make test`.

## Compatibility expectations

- Do not edit or reorder applied SQLite migrations; add the next migration.
- Keep existing projects, episodes, JSON artifacts, renderer manifests, API routes, and environment names readable whenever reasonable.
- Persisted format changes need an explicit version and legacy fixture/adapter.
- Update Pydantic, JSON Schema, TypeScript, API client, and documentation together.
- API errors keep the `{error: {code, message}}` envelope and must not expose secrets or arbitrary local paths.
- Visual policy cannot silently weaken rights or broadcast-fit gates.

## Pull request checklist

- [ ] Scope and architecture boundary are clear.
- [ ] Working behavior/API/output compatibility is preserved or migration is documented.
- [ ] Tests cover new logic, boundary validation, and discovered regressions.
- [ ] `make check` passed (exact command/results included).
- [ ] Relevant avatar/smoke/manual checks passed or blocker is stated.
- [ ] `.env.example` and configuration docs cover new variables.
- [ ] Architecture/pipeline/troubleshooting docs reflect the implemented code.
- [ ] No secrets, personal absolute paths, caches, node modules, episode data, or generated render output were added.
