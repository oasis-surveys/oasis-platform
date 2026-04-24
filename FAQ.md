# FAQ

Things people ask. Updated when new ones come in.

## Contents

- [Can I run OASIS entirely with open-source models?](#can-i-run-oasis-entirely-with-open-source-models)
- [Can I run this on our institutional HPC / GPU cluster?](#can-i-run-this-on-our-institutional-hpc--gpu-cluster)
- [What about European cloud providers instead of on-prem?](#what-about-european-cloud-providers-instead-of-on-prem)
- [Why no Azure OpenAI Realtime voice-to-voice?](#why-no-azure-openai-realtime-voice-to-voice)
- [What's the difference between "modular" and "voice-to-voice"?](#whats-the-difference-between-modular-and-voice-to-voice)
- [Can I use NVIDIA PersonaPlex for self-hosted voice-to-voice?](#can-i-use-nvidia-personaplex-for-self-hosted-voice-to-voice)
- [Do I need an OpenAI API key?](#do-i-need-an-openai-api-key)
- [Where does my data go?](#where-does-my-data-go)
- [Can I use this for phone interviews?](#can-i-use-this-for-phone-interviews)
- [How many concurrent interviews can it handle?](#how-many-concurrent-interviews-can-it-handle)
- [What's the deal with the license?](#whats-the-deal-with-the-license)
- [Something is broken](#something-is-broken)

---

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
<summary><strong>Where does my data go?</strong></summary>

OASIS stores everything in your own PostgreSQL database. Transcripts, session metadata, participant IDs, all local.

The only data that leaves your infrastructure is what gets sent to external AI providers (audio/text going to the LLM, STT, or TTS API). If you use fully self-hosted models, nothing leaves your network. If you use cloud APIs, data goes to whichever provider you configured.

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
