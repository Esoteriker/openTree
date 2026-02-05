# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog, and this project adheres to Semantic Versioning.

## [Unreleased]

### Added
- _None yet._

### Changed
- _None yet._

### Fixed
- _None yet._

## [0.1.1] - 2026-02-05

### Added
- Post-commit summary output to keep commits visible and remind about release notes.
- Repository metadata files for public releases.
- Enforced changelog updates on every commit via pre-commit hook.
- CI workflow for backend tests and compile checks.
- Environment template for backend service configuration.
- Operations runbook for readiness, auth, and storage incidents.
- PR policy workflow that requires `CHANGELOG.md` updates before merge.
- Automated release-cut PR workflow that turns `Unreleased` into versioned sections.
- Local pre-push hook to block direct pushes to `main`.

### Fixed
- CI now runs backend tests from the correct working directory.


## [0.1.0] - 2026-02-04

### Added
- Initial backend and frontend scaffolds.
- FastAPI microservices for dialogue, parser, graph, and suggestion services.
- Docker Compose stack for local development.
