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
- [What server specs do I need for cloud deployment?](#what-server-specs-do-i-need-for-cloud-deployment)
- [Are API keys hidden from participants?](#are-api-keys-hidden-from-participants)
- [Can I pipe data from Qualtrics into the interview?](#can-i-pipe-data-from-qualtrics-into-the-interview)
- [Can the agent end the interview on its own?](#can-the-agent-end-the-interview-on-its-own)
- [How do I update OASIS? Do I need to rebuild containers?](#how-do-i-update-oasis-do-i-need-to-rebuild-containers)
- [Are database migrations applied automatically?](#are-database-migrations-applied-automatically)
- [What's the deal with the license?](#whats-the-deal-with-the-license)
- [What languages are supported?](#what-languages-are-supported)
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

OASIS itself is lightweight, the backend is async Python (FastAPI + WebSockets) and acts as an orchestration layer, not a compute layer. It forwards audio/text to your self-hosted infrastructure or external AI providers and writes results to Postgres. 

**Text chat:** Straightforward. Each session is one WebSocket plus LLM API calls. OpenAI's Tier 2 rate limits (around 500 RPM for GPT-4o) can handle 300 concurrent text sessions comfortably since each turn is one request and users don't all type at the exact same moment. If you're on Tier 1, request a limit increase before launch.

**Voice interviews:** Harder. Each voice session holds persistent connections to STT, LLM, and TTS services simultaneously. With OpenAI (Whisper + GPT-4o + TTS), you need Tier 3+ rate limits. OpenAI's Realtime voice-to-voice endpoint has its own concurrency limits that vary by account, check your [usage dashboard](https://platform.openai.com/usage). If you hit rate limits, the session fails mid-interview, so budget headroom.

**The OASIS backend itself** is rarely the bottleneck. A single `backend` container on 2 vCPUs / 4 GB RAM can handle several hundred concurrent WebSocket sessions. If you need more, run multiple backend replicas behind a load balancer (you'll need sticky sessions or Redis-backed session state, which OASIS already uses).
</details>

<details>
<summary><strong>What server specs do I need for cloud deployment?</strong></summary>

For hundreds of concurrent users using cloud AI providers (OpenAI, Deepgram, etc.), OASIS is just the orchestrator no GPUs needed. Here's a practical starting point:

| Component | Spec | Notes |
|-----------|------|-------|
| **OASIS (backend + frontend + Caddy)** | 4 vCPU, 8 GB RAM | Single VM is fine. `t3.large` on AWS, `e2-standard-4` on GCP, `Standard_D4s_v3` on Azure, or a Hetzner CPX31 (~€15/mo). |
| **PostgreSQL** | 2 vCPU, 4 GB RAM, 50 GB SSD | Managed DB recommended (RDS, Cloud SQL, Azure Database). Saves you backup and failover headaches. |
| **Redis** | 1 vCPU, 1 GB RAM | Tiny footprint — stores API keys and active session state only. Managed Redis (ElastiCache, Memorystore) or run it on the same VM. |

**Cloud hosting options (all work fine):**

- **AWS:** EC2 instance or ECS Fargate. Use RDS for Postgres, ElastiCache for Redis. Put an ALB in front if you want SSL termination instead of Caddy.
- **GCP:** Compute Engine or Cloud Run (for the stateless frontend). Cloud SQL for Postgres, Memorystore for Redis.
- **Azure:** Container Apps or a VM. Azure Database for PostgreSQL, Azure Cache for Redis.
- **Hetzner / DigitalOcean / OVH:** A single VPS with Docker Compose works. Cheapest option. You manage your own backups.

For any cloud, make sure ports 80/443 are open and you have a domain pointed at the server (Caddy handles TLS automatically with Let's Encrypt). The `docker-compose.yml` ships production-ready — just `docker compose up -d` on your server.

**Cost estimate (cloud AI, 300 users, text chat):** The OASIS infrastructure itself runs for $50–150/month depending on provider (wihtout GPU cost). The dominant cost is the AI API usage. 
If you self-host models (vLLM, faster-whisper, Kokoro), infrastructure cost goes up (GPU VMs) but API cost drops to zero.

</details>

<details>
<summary><strong>Are API keys hidden from participants?</strong></summary>

Yes. API keys never leave the server.

- Keys from `.env` are read by the backend container at startup. Keys set through the **Settings** dashboard are stored in Redis. Both are server-side only.
- The participant-facing interview widget (`/interview/{widget_key}`) loads a public config endpoint that returns the agent's display settings (title, avatar, colors, modality) — no secrets. The interview itself runs over a WebSocket where audio/text flows through the backend to the AI provider. The browser never sees an API key.
- The dashboard shows keys as masked values (e.g. `sk-...7x2f`). Full keys are only sent *to* the server when an admin updates them via PUT.
- If you enable dashboard authentication (set `AUTH_USERNAME` and `AUTH_PASSWORD` in `.env`), only authenticated users can view or change keys. The interview widget routes are always public — that's by design, since participants need to access them without logging in.

Short version: participants interact with OASIS through a WebSocket. The backend makes the AI provider calls. Keys stay on the server.

</details>

<details>
<summary><strong>Can I pipe data from Qualtrics into the interview?</strong></summary>

Partially, with workarounds. OASIS doesn't have a native Qualtrics API integration, but the interview widget is a standard iframe that Qualtrics can embed, and you can pass a participant identifier via URL parameter. Qualtrics intentionally restricts access to in-progress response data from embedded content (for security and data integrity reasons), so piping live answers into an iframe is not straightforward. LimeSurvey is generally more flexible about exposing survey data to external embeds, but the specifics are still use-case dependent and require custom configuration.

**What works today:**

1. **Embed as iframe.** In Qualtrics, add a "Text/Graphic" question with custom HTML:
   ```html
   <iframe src="https://your-oasis-server.com/interview/WIDGET_KEY?pid=${e://Field/ResponseID}" width="100%" height="700" allow="microphone"></iframe>
   ```
   The `pid` parameter links the OASIS session to the Qualtrics response. Use Qualtrics piped text (`${e://Field/...}`) to pass the response ID or any embedded data field as the participant ID.

2. **One agent per condition.** If you have 3 experimental conditions, create 3 agents with different system prompts (each describing the condition context). In Qualtrics, use branch logic to show the iframe with the matching `WIDGET_KEY` for each condition. This is the cleanest approach when conditions are discrete.

3. **Encode condition in the participant ID.** Set participant ID mode to **Predefined** or **Input**, and use a structured ID like `P042_conditionA`. Mention in the system prompt that the participant ID encodes their condition and the agent should parse it. LLMs handle this reliably.

**What doesn't work (yet):**

- There's no `?condition=X&prior_answer=Y` URL parameter that gets injected into the system prompt automatically. The only first-class URL parameter is `pid`.
- OASIS can't call the Qualtrics API mid-interview to pull in earlier survey responses.
- There's no automatic redirect back to Qualtrics when the interview ends (see [Can the agent end the interview on its own?](#can-the-agent-end-the-interview-on-its-own)).

For most experimental designs, the "one agent per condition" approach is simplest and avoids fragile URL parameter parsing. If you need the LLM to reference specific prior answers, put that context in the system prompt or use the knowledge base to upload condition-specific documents.

</details>

<details>
<summary><strong>Can the agent end the interview on its own?</strong></summary>

Not automatically in the current version. Here's how session endings work:

- **Max duration:** If you set a max duration (e.g. 30 minutes), OASIS terminates the session when time runs out. The participant sees "Interview complete. Thank you for your participation. You may close this page now."
- **Structured interview guide:** When the agent finishes all topics, it delivers the configured closing message (e.g. "Thank you for your time"). But this is a *conversational* close — the WebSocket stays open and the participant can keep talking until they click **End Interview** or the max duration expires.
- **Participant clicks End Interview:** The button in the widget closes the session immediately.


Programmatic end-of-interview signaling and redirect URLs are on the roadmap.

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

One ask: if you cite OASIS, please link to the [main repository](https://github.com/oasis-surveys/oasis-platform) rather than a fork or modified copy. And if you've built something useful on top of it — a new provider integration, a pipeline improvement, a UI feature — consider contributing it back rather than maintaining a separate fork. The project is better when improvements land upstream where everyone benefits. We're happy to review PRs and help get things merged.

Questions? [max.lang@stx.ox.ac.uk](mailto:max.lang@stx.ox.ac.uk)

</details>

<details>
<summary><strong>What languages are supported?</strong></summary>

The language dropdown in the agent form includes twelve common languages (English, Spanish, French, German, Portuguese, Dutch, Italian, Chinese, Japanese, Korean, Arabic, Hindi). If you need a language that isn't in the list — like Finnish (`fi`) — select **Custom (provider code)** and type the provider-specific code directly.

**What the language setting does:** It tells the STT (speech-to-text) provider what language to expect in the audio stream. This improves transcription accuracy. For example, setting `fi` tells Whisper to expect Finnish speech rather than trying to auto-detect. The setting is also passed to some TTS providers. It does **not** control what language the LLM responds in — that's determined by your **system prompt**. If you want the agent to conduct interviews in Finnish, you need to do both: set the language to `fi` *and* write the system prompt in Finnish (or instruct the LLM to respond in Finnish).

For text-only interviews, the language setting has no effect — the LLM's response language is entirely controlled by the system prompt.

**Provider-specific codes:**

- **OpenAI Whisper / GPT-4o Transcribe**: ISO 639-1 codes (`en`, `fi`, `fr`, `de`, …). Finnish is `fi`. See [OpenAI language support](https://platform.openai.com/docs/guides/speech-to-text#supported-languages).
- **Deepgram**: BCP-47 style codes (`en-US`, `pt-BR`, `nl`). See [Deepgram language docs](https://developers.deepgram.com/docs/models-languages-overview).
- **Azure STT/TTS**: full locale codes (`en-US`, `fi-FI`, `zh-CN`). See [Azure language support](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/language-support).
- **OpenAI Realtime / Gemini Live (voice-to-voice)**: language is part of the system prompt context; the code is stored but may not map to a provider-level setting in all V2V pipelines.

The custom code field accepts up to 10 characters. If you're unsure which code your provider needs, check their documentation.

**One code for both STT and TTS:** OASIS uses a single language setting for the whole pipeline. In practice this is fine — the code is mainly used by STT (to know what language to expect in the audio), and most TTS providers auto-detect language from the text content without needing a code at all. If you mix providers that want different code formats (e.g. OpenAI STT expects `fi`, Deepgram expects `fi-FI`), use whatever your STT provider needs since that's where it actually matters.

You don't need to modify any UI labels or source code to use a new language. The language setting is a backend/pipeline parameter — the participant-facing interview widget has no language-specific UI text.

</details>

<details>
<summary><strong>Something is broken</strong></summary>

[Open an issue](https://github.com/oasis-surveys/oasis-platform/issues/new?template=bug_report.yml). OASIS launched in March 2026, rough edges are expected. We're active on issues.

</details>
