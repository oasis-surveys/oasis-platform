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

When you submit a pull request or other contribution to OASIS, you agree to the following:

1. **Your contribution is licensed under the same terms as the project** — the [GNU Affero General Public License v3 (AGPL-3.0)](LICENSE). This means anyone can use, modify, and distribute it for any purpose, including commercial use, as long as derivative works (including modified versions deployed as network services) are released under the same license.

2. **You retain full copyright over your own work.** You can reuse, republish, or build on your contributions however you wish — just as you would retain copyright over a journal article after granting a publisher a license to distribute it.

3. **You have the right to make the contribution.** The work is your own (or you have permission from your employer or institution), and it does not violate anyone else's intellectual property.

There is no separate CLA to sign. Submitting a pull request constitutes acceptance of these terms (this is the standard "inbound = outbound" model used by most AGPL/GPL projects). See the [LICENSE](LICENSE) file for the formal terms and the [FAQ](FAQ.md#whats-the-deal-with-the-license) for a plain-English explanation.

## A note on scope

OASIS is a research tool, not an enterprise product. Contributions that improve reliability, researcher experience, and methodological flexibility are high priority. Features aimed at commercial use cases (sales bots, customer support, marketing automation) are out of scope.

## Questions?

If you are not sure whether something is worth a PR, or you want to discuss an idea before writing code, feel free to open an issue or email [max.lang@stx.ox.ac.uk](mailto:max.lang@stx.ox.ac.uk).
