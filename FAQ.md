# FAQ

Things people ask. Updated when new ones come in.

## Contents

- [Can I just start with OpenAI and add more providers later?](#can-i-just-start-with-openai-and-add-more-providers-later)
- [Can I run OASIS entirely with open-source models?](#can-i-run-oasis-entirely-with-open-source-models)
- [Can I run this on our institutional HPC / GPU cluster?](#can-i-run-this-on-our-institutional-hpc--gpu-cluster)
- [What about European cloud providers instead of on-prem?](#what-about-european-cloud-providers-instead-of-on-prem)
- [Can I keep my data in the EU when using OpenAI?](#can-i-keep-my-data-in-the-eu-when-using-openai)
- [Do I need approval from OpenAI to use the EU endpoint?](#do-i-need-approval-from-openai-to-use-the-eu-endpoint)
- [Why no Azure OpenAI Realtime voice-to-voice?](#why-no-azure-openai-realtime-voice-to-voice)
- [What's the difference between "modular" and "voice-to-voice"?](#whats-the-difference-between-modular-and-voice-to-voice)
- [Can I use NVIDIA PersonaPlex for self-hosted voice-to-voice?](#can-i-use-nvidia-personaplex-for-self-hosted-voice-to-voice)
- [Do I need an OpenAI API key?](#do-i-need-an-openai-api-key)
- [What templates ship with OASIS?](#what-templates-ship-with-oasis)
- [Why are new agents active by default? Can I make them draft instead?](#why-are-new-agents-active-by-default-can-i-make-them-draft-instead)
- [Where does my data go?](#where-does-my-data-go)
- [Can I use this for phone interviews?](#can-i-use-this-for-phone-interviews)
- [How many concurrent interviews can it handle?](#how-many-concurrent-interviews-can-it-handle)
- [How do I update OASIS? Do I need to rebuild containers?](#how-do-i-update-oasis-do-i-need-to-rebuild-containers)
- [Are database migrations applied automatically?](#are-database-migrations-applied-automatically)
- [What's the deal with the license?](#whats-the-deal-with-the-license)
- [Something is broken](#something-is-broken)

---

<details>
<summary><strong>Can I just start with OpenAI and add more providers later?</strong></summary>

Yes, that's the recommended path. With only `OPENAI_API_KEY` set in `.env` you get text chat (gpt-4o-mini), voice interviews (Whisper STT + gpt-4o-mini-tts), and voice-to-voice (gpt-realtime). Run `docker compose up -d`, open `http://localhost`, create a study from one of the four templates, and you have a working interview link in under a minute.

Add Deepgram, ElevenLabs, Cartesia, Google, Anthropic, Scaleway, Azure, GCP, or self-hosted endpoints whenever you want to swap in something different. You don't have to commit upfront.

</details>

<details>
<summary><strong>Can I run OASIS entirely with open-source models?</strong></summary>

For **text interviews**, yes. OASIS uses LiteLLM, so you can point it at Ollama, vLLM, or any OpenAI-API-compatible endpoint. "OpenAI-compatible" just means the server speaks the same HTTP protocol, your data doesn't go to OpenAI.

For **voice interviews** (modular pipeline), mostly yes. The LLM can be any OpenAI-compatible server. STT and TTS support self-hosted providers too, anything that implements `/v1/audio/transcriptions` or `/v1/audio/speech` works (e.g. Speaches/faster-whisper for STT, Kokoro or Piper for TTS).

The gap is **voice-to-voice mode**, which currently needs OpenAI Realtime or Google Gemini Live. These are proprietary streaming audio protocols and there's no open-source equivalent yet.

RAG embeddings (for the knowledge base) can also be self-hosted by pointing `EMBEDDING_API_URL` at any OpenAI-compatible embedding server.

</details>

<details>
<summary><strong>Can I run this on our institutional HPC / GPU cluster?</strong></summary>

Yes, but you'll need your HPC team involved. OASIS itself is just the orchestration layer, it runs in Docker and doesn't need GPUs. What needs GPUs are the model servers (LLM, STT, TTS) that OASIS calls.

HPC setups vary a lot: different job schedulers (SLURM, PBS), network configs, storage mounts, firewall rules. There's no universal setup. Once your HPC team has a model endpoint running and reachable over HTTP, wiring it into OASIS is easy (just set a URL in the config or dashboard).

We don't try to abstract over HPC infrastructure on purpose. Every setup is different, and the people running these clusters know their environment better than we do.

</details>

<details>
<summary><strong>What about European cloud providers instead of on-prem?</strong></summary>

Often the more practical path. Host open-source models on a European provider (Scaleway, Azure EU, GCP EU) and point OASIS at those endpoints. Data stays in European jurisdiction, no GPUs to manage yourself.

OASIS has built-in support for Scaleway and Azure. For others, any OpenAI-compatible endpoint works via LiteLLM or the self-hosted STT/TTS options.

</details>

<details>
<summary><strong>Can I keep my data in the EU when using OpenAI?</strong></summary>

Yes. There's a toggle in **Settings > OpenAI Data Residency** that routes every OpenAI call (chat, Realtime voice-to-voice, Whisper STT, TTS, and embeddings) through `eu.api.openai.com` instead of the default `api.openai.com`. When the toggle is on, customer content (prompts, audio, transcripts) is stored at rest in the EEA region and inference for those endpoints runs in the EEA region too.

You can also set it persistently via `.env`:

```env
OPENAI_USE_EU=true
```

Default is off because it requires extra approval on the OpenAI side (see the next question). Once on, no model code changes, you keep using the same model names like `openai/gpt-4o` and `openai/gpt-realtime`.

OpenAI's full data residency guide: <https://developers.openai.com/api/docs/guides/your-data>

</details>

<details>
<summary><strong>Do I need approval from OpenAI to use the EU endpoint?</strong></summary>

Yes. The EU regional endpoint (`eu.api.openai.com`) requires that the OpenAI **project** your API key belongs to has data residency enabled, plus a Modified Abuse Monitoring or Zero Data Retention amendment in place. Both of those are gated behind a sales conversation with OpenAI, your university or organisation may already have it set up, or might need to request it.

Confirm with whoever manages your OpenAI org before flipping the toggle. If your project isn't approved and you enable it anyway, requests will fail with an error from OpenAI. You won't lose data, but interviews won't work until you either turn it off or get the project approved.

OpenAI also notes a 10% pricing uplift for some models when used through a data residency endpoint. Mention this to your billing person if budgets are tight.

For Realtime voice-to-voice specifically, the EU endpoint supports `gpt-realtime`, `gpt-realtime-1.5`, `gpt-realtime-mini`, and `gpt-4o-realtime-preview-2025-06-03`. Older preview snapshots are US-only.

</details>

<details>
<summary><strong>Why no Azure OpenAI Realtime voice-to-voice?</strong></summary>

Pipecat (the voice pipeline framework OASIS uses) has an `AzureRealtimeLLMService`, but it has unresolved bugs. It sends parameters Azure's API rejects. There's a fix PR but it hasn't been merged, and the Pipecat maintainers themselves don't have an Azure Realtime endpoint to test against. Azure also hasn't made the non-beta Realtime endpoint generally available in most regions.

We don't ship stuff we can't test. The modular pipeline with Azure (separate STT + LLM + TTS) works fine and is the reliable Azure path today.

</details>

<details>
<summary><strong>What's the difference between "modular" and "voice-to-voice"?</strong></summary>

**Modular** chains three separate services: STT > LLM > TTS. You can mix and match providers for each step. Most flexible, supports self-hosted for all three.

**Voice-to-voice** sends audio directly to a single multimodal model that does everything (listening, thinking, speaking). Lower latency, more natural feel, but you're locked to the providers that support it (OpenAI Realtime or Gemini Live right now). No self-hosted option for this yet.

</details>

<details>
<summary><strong>Can I use NVIDIA PersonaPlex for self-hosted voice-to-voice?</strong></summary>

Not today. PersonaPlex is open-source (MIT license, weights on HuggingFace), so it's technically viable. But it uses the Moshi WebSocket protocol, which is different from OpenAI Realtime or Gemini Live. Someone would need to write a new Pipecat service to bridge the two. Probably 1-2 weeks of work.

Also: PersonaPlex v1 is English-only, needs ~24GB VRAM, and can drift during long conversations. Promising but not ready for research interviews yet.

</details>

<details>
<summary><strong>Do I need an OpenAI API key?</strong></summary>

Only if you use OpenAI models. If you run everything through Scaleway, Azure, GCP, Google, or self-hosted endpoints, no OpenAI key needed.

The **knowledge base** (RAG) also supports self-hosted embeddings. By default it uses OpenAI's `text-embedding-3-small`, but you can point it at any OpenAI-compatible embedding server by setting `EMBEDDING_API_URL`. One thing to watch out for: the database schema expects 1536-dimensional vectors (what OpenAI outputs). If your model outputs a different dimension, you'll need a DB migration.

</details>

<details>
<summary><strong>What templates ship with OASIS?</strong></summary>

Five research-oriented templates, available under **New Study > From Template**:

- **Semi-Structured Qualitative Interview (Voice)**: open-ended interview that probes for concrete examples and stays neutral. Good default for lived-experience and attitude research. No fixed question order.
- **Structured Topic-Guide Interview (Voice)**: same neutral stance, but with a fixed three-topic guide and probes asked in order. The agent paraphrases each topic naturally and auto-advances after the configured follow-ups. Use when every participant needs to cover the same topics in the same order (comparative qualitative work).
- **Cognitive Interview / Survey Pretest (Voice)**: runs the standard cognitive interviewing protocol (comprehension, recall, judgment, response probes) to test how participants interpret survey items before you field them. Items are read verbatim.
- **Open-Ended Survey Follow-Up (Text Chat)**: text agent designed to be embedded at the end of a Qualtrics, REDCap, or LimeSurvey questionnaire to collect open-ended reasoning behind quantitative answers.
- **Conversational Phone Survey (Voice-to-Voice)**: low-latency phone survey via Twilio + OpenAI Realtime. Useful when you want to reach participants who don't use the web.

All five use OpenAI defaults so they work with just `OPENAI_API_KEY`. Edit the prompt, swap the model, change the language, etc. after creating from the template.

</details>

<details>
<summary><strong>Why are new agents active by default? Can I make them draft instead?</strong></summary>

Active by default because the most common path is "create the agent, copy the share link, send to a participant". Forcing a manual flip from draft to active was a footgun for first-time users who'd send the link and wonder why nothing loaded.

Existing agents keep their current status (the change only affects newly created ones). If you prefer to review the prompt and provider settings before the link goes live, set the status dropdown to **Draft** in the agent form. Draft and Paused agents return 404 on the widget config and reject all interview connections, the gate is still there, it's just not the default anymore.

</details>

<details>
<summary><strong>Where does my data go?</strong></summary>

OASIS stores everything in your own PostgreSQL database. Transcripts, session metadata, participant IDs, all local.

The only data that leaves your infrastructure is what gets sent to external AI providers (audio/text going to the LLM, STT, or TTS API). If you use fully self-hosted models, nothing leaves your network. If you use cloud APIs, data goes to whichever provider you configured.

For OpenAI specifically, you can route those calls through the EU regional endpoint so customer content stays in the EEA, see [Can I keep my data in the EU when using OpenAI?](#can-i-keep-my-data-in-the-eu-when-using-openai).

</details>

<details>
<summary><strong>Can I use this for phone interviews?</strong></summary>

Yes, via Twilio Media Streams (beta). Provision a Twilio phone number, set the credentials in OASIS, participants call in. Same pipeline as browser-based voice interviews.

Incoming calls only for now. No outbound calling yet.

</details>

<details>
<summary><strong>How many concurrent interviews can it handle?</strong></summary>

Depends on your setup. The OASIS backend is async (FastAPI + WebSockets) and handles many concurrent sessions fine. The bottleneck is usually the AI providers, each voice session holds a persistent connection to STT/LLM/TTS.

Cloud providers: limited by their rate limits and your API tier. Self-hosted: limited by your GPU capacity.

</details>

<details>
<summary><strong>How do I update OASIS? Do I need to rebuild containers?</strong></summary>

Yes, both `backend` and `frontend` images bake the source code at build time, so any code change needs a rebuild:

```bash
git pull
docker compose down
docker compose up -d --build
```

The Postgres and Redis containers don't need rebuilding, your data persists in the named volumes (`pgdata`, `redisdata`). If you ever want a clean slate, `docker compose down -v` wipes the volumes too.

You don't need to manually run database migrations, the backend container does that on startup (see the next question).

API keys you set through the dashboard live in Redis and survive a backend restart. Keys in `.env` are read fresh on every container start.

</details>

<details>
<summary><strong>Are database migrations applied automatically?</strong></summary>

Yes. The backend container's startup command runs `alembic upgrade head` before starting Uvicorn, so any new migrations from a `git pull + docker compose up --build` are applied before the API serves traffic.

If a migration fails, the backend container exits and `docker compose logs backend` will show the Alembic error. Most failures are because the DB has drifted from what Alembic expects (someone ran SQL by hand, or you switched between branches with conflicting migrations). In that case, fix the schema manually or restore from a backup, don't force-skip the migration.

</details>

<details>
<summary><strong>What's the deal with the license?</strong></summary>

OASIS is licensed under the **GNU Affero General Public License v3 (AGPL-3.0)**.

In plain terms: you can use OASIS for anything, including funded research, grant-backed studies, university projects, whatever. No need to ask permission first. NSF grant, Wellcome Trust award, EU Horizon project, doesn't matter. Just use it.

The one thing AGPL requires: if you modify OASIS and deploy it as a network service (i.e. you run a modified version for other people to use over the internet), you need to make your source code available under the same license. This is specifically designed to prevent companies from taking the code, building a paid SaaS on top of it, and not contributing back. If you're running it internally for your own research, this doesn't apply to you.

We previously used a custom non-commercial license (ONCRL) but it created ambiguity around funded academic work, which is exactly the use case we want to support. AGPL fixes that.

If you use OASIS in published research, we'd appreciate a citation. There's a BibTeX entry and Zenodo DOI in the [README](README.md#citation). It's not a legal requirement, just a nice thing to do that helps the project.

Questions? [max.lang@stx.ox.ac.uk](mailto:max.lang@stx.ox.ac.uk)

</details>

<details>
<summary><strong>Something is broken</strong></summary>

[Open an issue](https://github.com/oasis-surveys/oasis-platform/issues/new?template=bug_report.yml). OASIS launched in March 2026, rough edges are expected. We're active on issues.

</details>
