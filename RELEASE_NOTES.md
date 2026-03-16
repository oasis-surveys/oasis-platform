# OASIS v1.0.0 — First Public Release

**March 2026**

This is the first public release of OASIS (Open Agentic Survey Interview System), a self-hosted platform for running AI-powered conversational interviews.

OASIS was built because existing tools for conversational AI are not designed with research in mind. If you need semi-structured interview guides, participant tracking, diarized transcripts, and full control over your data and models — but don't want to build everything from scratch — this is what OASIS is for.

---

## What's included

### Core platform
- **Study management** — Create studies, add multiple agents per study, organize everything from a single dashboard.
- **Two interview modalities** — Voice interviews (real-time speech with STT → LLM → TTS) and text chat interviews (clean browser-based UI).
- **Flexible AI pipeline** — Chain any combination of speech-to-text, language model, and text-to-speech providers. Or use voice-to-voice models like OpenAI Realtime and Gemini Live for direct audio streaming.

### Semi-structured interview mode
- Define a question guide with preset questions, follow-up probes, and transition logic.
- The agent follows the structure while still having natural conversations — it adapts its probing based on what the participant actually says.
- Import guides via JSON or CSV, or build them directly in the dashboard.

### Model support
- **LLMs:** OpenAI (GPT-4o, GPT-4.1, GPT-5, Realtime), Google Gemini (including native audio), Scaleway, Azure OpenAI, GCP Vertex AI, and any LiteLLM-compatible provider.
- **STT:** Deepgram, Scaleway Whisper.
- **TTS:** ElevenLabs, Cartesia, Scaleway.
- You can also point OASIS at any custom endpoint via LiteLLM — useful if you're running local models on your own hardware.

### Research features
- **Participant identifiers** — Random IDs, predefined lists, or self-reported names. Your choice per agent.
- **Diarized transcripts** — Every interview is transcribed with speaker labels and timestamps.
- **Session analytics** — Duration, word counts, and completion tracking across your study.
- **Data export** — Download transcripts and analytics as CSV or JSON.
- **Knowledge base (RAG)** — Upload documents to ground your agent's responses in specific material. Uses pgvector for semantic retrieval.

### Telephony (beta)
- Twilio Media Streams integration for conducting interviews over the phone.
- Currently supports incoming calls. Outbound dialing is not yet implemented.

### Deployment
- Everything runs in Docker (five containers: Caddy, Frontend, Backend, PostgreSQL, Redis).
- No data leaves your infrastructure unless you explicitly call external APIs.
- Optional basic auth for the admin dashboard.
- All API keys configurable via `.env` or the dashboard settings page.

---

## A note on maturity

OASIS has been tested extensively — across different virtual machines, operating systems, cloud providers, and deployment configurations. The test suite covers the backend API, pipeline orchestration, schemas, and frontend components, and runs automatically on every push and on a recurring schedule.

That said, this is the first public release. The project launched in March 2026, and it is still young. You may run into rough edges, particularly in less common setups or with provider combinations we haven't encountered yet. We've tried to handle edge cases gracefully, but there will be things we missed.

If something breaks or behaves unexpectedly, please [open a bug report](https://github.com/oasis-surveys/oasis-platform/issues/new?template=bug_report.yml). Clear reproduction steps help a lot. Even small issues are worth reporting — they help us improve the platform for everyone.

---

## Getting started

```bash
git clone https://github.com/oasis-surveys/oasis-platform.git
cd oasis-platform
cp .env.example .env
# Add your API keys to .env
docker compose up -d
```

Open `http://localhost` and you're ready to go. The [documentation](https://oasis-surveys.github.io/docs) has a full walkthrough.

---

## What's next

We're actively working on OASIS and have a number of features in the pipeline. If you have ideas or run into limitations, [suggest a feature](https://github.com/oasis-surveys/oasis-platform/issues/new?template=feature_request.yml) or reach out directly at [max.lang@stx.ox.ac.uk](mailto:max.lang@stx.ox.ac.uk).

Contributions are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

## License

OASIS is released under the [Open Non-Commercial Research License (ONCRL) v1.0](LICENSE). Free for non-commercial research use. Commercial use requires written approval.

## Citation

```bibtex
@software{lang2026oasis,
  author       = {Lang, Max M.},
  title        = {{OASIS}: Open Agentic Survey Interview System},
  year         = {2026},
  url          = {https://github.com/oasis-surveys/oasis-platform},
  note         = {Self-hosted platform for AI-powered conversational interviews}
}
```
