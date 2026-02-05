# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog, and this project adheres to Semantic Versioning.

## [Unreleased]

### Added
- Post-commit summary output to keep commits visible and remind about release notes.
- Repository metadata files for public releases.
- Enforced changelog updates on every commit via pre-commit hook.
- CI workflow for backend tests and compile checks.
- Environment template for backend service configuration.
- Operations runbook for readiness, auth, and storage incidents.

### Fixed
- CI now runs backend tests from the correct working directory.

### Commit Log
- 2026-02-06 04:50 +0800 | pending | Backfill commit log history in changelog
- 2026-02-06 04:44 +0800 | e274468 | Enforce structured changelog entries in hook
- 2026-02-05 07:00 +0800 | cc5257c | Fix CI working directory for tests
- 2026-02-05 06:57 +0800 | 59ba0cb | Add CI workflow, ops runbook, env template
- 2026-02-05 06:10 +0800 | 346397a | Require changelog updates on commit
- 2026-02-05 06:06 +0800 | 7d67161 | Fix post-commit summary on macOS
- 2026-02-05 06:06 +0800 | 190d4fe | Add changelog, license, and commit notes
- 2026-02-05 06:01 +0800 | 512d20d | Add backend updates and secret scan workflow

## [0.1.0] - 2026-02-04

### Added
- Initial backend and frontend scaffolds.
- FastAPI microservices for dialogue, parser, graph, and suggestion services.
- Docker Compose stack for local development.
