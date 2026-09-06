# Live verification contract

The public CareFlow demo and the integration-test stack intentionally serve different purposes.

- Public Render demo: `SQLite` + in-memory transcript store, deterministic note generator, speech input disabled. This keeps the public portfolio instance inexpensive and non-clinical while preserving the full session/review/purge workflow.
- CI integration stack: PostgreSQL 16 + Redis 7. The CI job applies migrations and runs real-service integration tests against both services.

`Deployment Smoke` and `Demo Capture` must therefore verify the public runtime truthfully instead of claiming that the public Render instance uses PostgreSQL or Redis. Both workflows also wait until `/v1/release` reports the exact triggering Git commit before exercising the deployment, which prevents testing the previous Render release during an auto-deploy swap.

The live smoke path verifies both lifecycle outcomes with synthetic data:

1. A normal session reaches `ready`, produces a 3/3 evidence map, and purges the raw transcript.
2. A safety-signal session reaches `review_required`, retains the transcript for human review, and purges it only after explicit approval.

The browser capture additionally verifies the selected product Home, empty consultation entry, explicit scenario creation, Review Queue, model-selection evidence, healthy public data layers, and absence of credential URLs in the UI.
