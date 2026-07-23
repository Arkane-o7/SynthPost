# Python pipeline

The Python package owns domain contracts, editorial use cases, providers, persistence, queue execution, renderer manifest construction, and FastAPI. Follow the dependency direction:

```text
API / CLI / supervised worker pool -> feature service -> domain model + provider/repository
```

Start at `stages.py` for the production lifecycle, `models.py` for data contracts, `config.py` for settings, `db/repository.py` for persistence, and `api/main.py` for app wiring. Feature packages own their logic. `narration/` owns Kokoro synthesis and sample-exact beat alignment; timeline and avatar stages consume its versioned canonical artifacts. Render boundaries consume approved state; they do not perform upstream editorial work.

`jobs/supervisor.py` expands typed per-lane capacity into isolated OS processes. `jobs/worker.py` leases numbered slots; `Repository.claim_next_job()` atomically permits independent project work and the safe narration/visual-search overlap while serializing conflicting same-story mutations and episode assembly.

New environment reads go through typed configuration. New job types need a stage contract. New providers need capability checks and offline tests. See `docs/ARCHITECTURE.md`, `docs/PIPELINE.md`, and `docs/DEVELOPMENT.md`.
