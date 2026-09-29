# Delivery roadmap

## Milestone 1 — Durable orchestration foundation

- [x] FastAPI service and health endpoint
- [x] PostgreSQL run and approval models
- [x] Alembic migration
- [x] Redis/Celery worker
- [x] PostgreSQL-backed LangGraph checkpoints
- [x] Human approval interrupt and resume
- [x] Redis Streams progress events and SSE endpoint
- [x] Mock graph tests
- [x] Docker Compose with PostgreSQL, Redis, and Qdrant

## Milestone 2 — Live discovery and evidence

- [x] LLM provider protocol and deterministic mock adapter
- [x] Search provider protocol with mock and Tavily adapters
- [x] Concurrent query fan-out and URL deduplication
- [x] SSRF-safe fetcher with redirect revalidation and bounded downloads
- [x] Source, passage, and evidence schema
- [x] Content hashes and sparse Qdrant indexing
- [x] Tool-call/token/cost ledger and usage endpoint
- [ ] OpenAI and Anthropic LLM adapters
- [ ] PDF extraction and browser-rendering fallback
- [ ] Object-store snapshots

## Milestone 3 — Critic and iterative research

- [ ] Source-quality score with explanations
- [ ] Coverage matrix
- [ ] Contradiction records and resolution status
- [ ] Gap analysis and bounded follow-up loops
- [ ] Budget, deadline, and cancellation enforcement

## Milestone 4 — Synthesis and citations

- [ ] Evidence-constrained section synthesis
- [ ] Claim extraction and claim/evidence links
- [ ] Deterministic citation integrity checks
- [ ] LLM entailment verification
- [ ] Repair loop and publication gate
- [ ] Markdown and PDF exports

## Milestone 5 — Product and evaluation

- [ ] React run form, plan approval, timeline, evidence explorer, and report reader
- [ ] Authentication and project isolation
- [ ] OpenTelemetry traces and operational dashboards
- [ ] Golden research dataset and regression runner
- [ ] Failure injection and restart-recovery tests
- [ ] AWS deployment and interview demo
