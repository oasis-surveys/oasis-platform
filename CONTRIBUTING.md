# Contributing to OASIS

Thanks for your interest in contributing. OASIS is an open-source research tool, and contributions from the community help make it better for everyone.

## How to get involved

### Reporting bugs

If you run into something broken, please [open a bug report](https://github.com/oasis-surveys/oasis-platform/issues/new?template=bug_report.yml). Include as much detail as you can: what you did, what happened, what you expected, and any relevant logs. The issue template will walk you through it.

### Suggesting features

If there is something OASIS does not do yet that would help your research, [open a feature request](https://github.com/oasis-surveys/oasis-platform/issues/new?template=feature_request.yml). We are especially interested in requests that come from real study workflows.

### Contributing code

If you want to fix a bug or build a feature:

1. **Open an issue first** (or comment on an existing one) so we can discuss the approach before you write code. This avoids duplicated effort and makes sure the change fits the project direction.
2. **Fork the repository** and create a branch from `main`.
3. **Make your changes.** Try to keep pull requests focused on one thing. A PR that fixes a bug should not also refactor unrelated code.
4. **Test your changes.** Run the existing test suites and add tests for new functionality where reasonable:
   ```bash
   # Backend
   cd backend && pip install -r requirements.txt && pytest tests/ -v

   # Frontend
   cd frontend && npm install && npx vitest run
   ```
5. **Open a pull request** with a clear description of what the change does and why.

### Code style

- **Python (backend):** Follow PEP 8. Use type hints. Keep functions short and well-named.
- **TypeScript (frontend):** Use the existing component patterns. Prefer functional React components with hooks. Avoid `any` types where possible.
- **Commits:** Write clear commit messages. Use conventional prefixes when they fit (`feat:`, `fix:`, `docs:`, `test:`, `chore:`), but do not overthink it.

### Documentation

If you notice something in the docs that is wrong, unclear, or missing, a PR to fix it is always welcome. The website lives in a [separate repository](https://github.com/oasis-surveys/oasis-surveys.github.io).

## Project structure at a glance

| Directory | What it does |
|-----------|-------------|
| `backend/app/api/` | REST and WebSocket endpoints |
| `backend/app/models/` | SQLAlchemy ORM models |
| `backend/app/schemas/` | Pydantic request/response schemas |
| `backend/app/pipeline/` | Pipecat pipeline runner and custom processors |
| `backend/app/knowledge/` | RAG: document chunking, embedding, retrieval |
| `backend/tests/` | Backend test suite (pytest) |
| `frontend/src/pages/` | Dashboard and interview widget pages |
| `frontend/src/components/` | Shared UI components |
| `frontend/src/lib/` | API client, utilities, constants |
| `docker/` | Caddyfile for reverse proxy |

## By contributing

When you submit a pull request, patch, or any other contribution to OASIS, you agree to the following:

1. **You assign copyright in your contribution to the OASIS project maintainer (Max M. Lang).** This keeps the project under single-owner copyright so the AGPL can be enforced cleanly and so OASIS keeps the option to relicense or dual-license in the future without having to chase down every past contributor for permission. This is the same pattern used by Apache Software Foundation projects, Django (CLA), and many other long-lived open source projects.

2. **Your contribution is published under AGPL-3.0** (the [LICENSE](LICENSE) file), the same as the rest of OASIS. You can keep using your own contribution under AGPL-3.0 just like everyone else, including in your own forks or projects.

3. **You have the right to make the contribution.** The work is your own (or you have explicit permission from your employer / institution to contribute under these terms), and it does not violate anyone else's intellectual property.

There is no separate CLA document to sign. Submitting a pull request constitutes acceptance of these terms. If your employer or institution has an IP policy that prevents you from assigning copyright on contributions, open an issue first so we can discuss alternatives (a license grant rather than assignment, an institutional CLA, etc.).

> **Note for past contributors:** Until 2026-05-07, OASIS used an "inbound = outbound" model where contributors retained copyright over their own work. Past contributions made under that model continue to be governed by it. The terms above apply to contributions made from now on.

See the [FAQ](FAQ.md#whats-the-deal-with-the-license) for a plain-English explanation of what AGPL-3.0 means in practice.

## A note on scope

OASIS is a research tool, not an enterprise product. Contributions that improve reliability, researcher experience, and methodological flexibility are high priority. Features aimed at commercial use cases (sales bots, customer support, marketing automation) are out of scope.

## Questions?

If you are not sure whether something is worth a PR, or you want to discuss an idea before writing code, feel free to open an issue or email [max.lang@stx.ox.ac.uk](mailto:max.lang@stx.ox.ac.uk).
