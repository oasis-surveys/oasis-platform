# Changelog

All notable changes to OASIS are tracked here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), with date-based
sections — versions are added retroactively when a release is cut.

## 2026-06-10

### Fixed

- Structured interviews enforce one question per agent turn on the output
  path. The model sometimes crammed a probe, a leaked stage direction
  ("(Transition: ...)" read aloud), and the next main question into a single
  spoken turn, advancing through the whole guide in a couple of exchanges
  regardless of the protocol prompt. A new `StructuredOutputFilter` between
  the LLM and TTS re-emits the streamed response sentence by sentence,
  unwraps leaked transition labels, and cuts everything after the turn's
  first question — transcripts and the model's own context both match what
  the participant actually hears. The protocol prompt now also states the
  one-question limit is enforced and forbids reading transition labels.

## 2026-06-09

### Fixed

- Structured interviews no longer cut to the closing message while the
  participant is still asking about the final question. The guide processor's
  hard turn-counter was content-blind: the agent's answers to "what do you
  mean?" and its verbatim question repeats were charged against the follow-up
  budget, so a clarification exchange at the last question exhausted the
  budget and the close nudge fired — the agent then repeated the question and
  delivered the closing message in the same turn. The processor now buffers
  the participant's transcribed speech, skips counting bot turns that reply
  to clarification/repeat requests, and holds the advance/close nudge until
  the participant gives a substantive answer. Detection follows the agent's
  configured interview language, with pattern sets for all twelve languages
  offered in the agent form (English is always included as a baseline for
  code-switching participants).
  The closing instructions also explicitly forbid combining a question with
  the closing message in one turn.
- Deepgram STT failed to start (`ImportError: cannot import name 'LiveOptions'
  from 'deepgram'`): deepgram-sdk v4+ removed the top-level `LiveOptions`
  export. The pipeline now passes `DeepgramSTTSettings` as Pipecat 0.0.105
  expects. The Deepgram model list was also verified against the live
  `api.deepgram.com/v1/models` endpoint; Nova 3 is the default.
- Injected mid-conversation guidance (adaptive actions, structured-interview
  nudges, silence check-ins, text-chat knowledge-base context) is now sent as
  a clearly marked user-role note instead of a system message. OpenAI gpt-5.x
  rejects a system message that appears after an assistant message with a 400
  error ("Unexpected role 'system' after role 'assistant'"), which silenced
  the agent for the remainder of the session after the first adaptive action.
- Voice engagement turns are finalized at the aggregator's turn-stop boundary,
  fixing `response_latency_ms` always being recorded as empty: turns were
  previously finalized one turn late, by which time the bot-stopped timestamp
  had been refreshed and the latency delta was discarded as negative. Latency
  is now captured once when the participant starts speaking.
- Engagement and adaptive behavior now evaluate once per participant turn
  instead of once per STT fragment. Segmented STT services (OpenAI Whisper)
  emit one transcription per VAD segment, so a single spoken turn could
  produce several fragments that each scored as a "very short answer",
  over-firing adaptive actions mid-turn and stacking multiple injected
  instructions into one LLM call. Fragments are now aggregated and scored at
  the actual turn boundary, and the adaptive processor acts at most once per
  turn.
- Transcript entries are written to the database in a background task instead
  of on the audio pipeline's frame path, removing a per-fragment DB round trip
  from the turn latency. Sequence numbers are still assigned synchronously.
- Structured interviews no longer steamroll participant questions: the
  protocol prompt now instructs the model to briefly answer clarification
  questions (without consuming the follow-up budget) before continuing with
  the current probe, to ask exactly one question per turn and wait for the
  answer, and to count follow-ups by which probes were actually asked rather
  than by message count (agent turns can appear split in the context, which
  previously caused premature transitions). The advance/closing nudges also
  answer a pending participant question first.
- Model catalog refreshed and verified against the live provider APIs
  (June 2026): added Gemini 3.5 Flash; added Scaleway Qwen 3.5 397B,
  Qwen 3.6 35B, Mistral Medium 3.5 128B, and Gemma 4 26B; removed models the
  providers no longer serve (Scaleway DeepSeek-R1 Distill, Llama 3.1 8B,
  Mistral Nemo; OpenAI `gpt-4o-realtime-preview`). All listed OpenAI, Google,
  and Scaleway models were confirmed present on the providers' live model
  endpoints, with completion smoke tests for the new flagships.

### Changed

- Custom LiteLLM / OpenAI-compatible provider configuration is now clearly
  labeled: the dashboard Settings category is "Custom / Self-Hosted" with
  explicit env var names per field, the agent form's provider dropdowns and
  hints mention LiteLLM, and `.env.example` documents
  `OPENAI_COMPATIBLE_LLM_URL`/`_API_KEY` (LLM) and `SELF_HOSTED_STT_*` /
  `SELF_HOSTED_TTS_*` (STT/TTS) for LiteLLM proxies.

### Added

- Adaptive behavior (Phase 3a): act on engagement signals during an interview.
  Off by default and scoped per agent. A small per-agent policy maps engagement
  triggers (events or per-turn flags) to curated actions — prompt injections
  (offer a break, soften the next question, encourage elaboration, acknowledge
  effort, privacy check) and, for modular voice, speaking-pace changes. Defaults
  to a non-acting **shadow** mode that logs intended actions without applying
  them; switching to **live** is a deliberate choice. Every action (applied or
  shadow) is written to a new `adaptive_actions` table and surfaced on the
  session detail page, in the engagement API response, and in the JSON
  (`adaptive`) and CSV (`adaptive_actions`) exports. Sessions that can adapt live
  are flagged via `sessions.adaptive_active`. Available for modular voice and
  text chat (pace actions are no-ops for text); not available for voice-to-voice.
  See [docs/ADAPTIVE_BEHAVIOR.md](docs/ADAPTIVE_BEHAVIOR.md).
- Engagement metrics for text chat interviews (observational): response latency
  (reading + typing time), answer length, and lexical hedging, scored with a
  text-specific threshold profile. Enabled per agent with the same **Track
  engagement metrics** toggle, which now appears for text agents. Audio-based
  signals (speech rate, energy) are not available for text and stay null. See
  [docs/ENGAGEMENT_METRICS.md](docs/ENGAGEMENT_METRICS.md).
- Engagement events (Phase 2, observational): rolling-window detection of
  `sustained_disengagement`, `positive_engagement_streak`, and
  `recovery_after_dip`, stored in a new `engagement_events` table. Each event
  fires once when its condition is met and re-arms after it clears. Thresholds
  and component weights are now tunable per agent via **Engagement tuning** in
  the agent form (`engagement_config`). Events appear on the session detail
  page, in the engagement API response, in the JSON export, and as an
  `engagement_events` column in the CSV export. Still observe-only and modular
  voice only. See [docs/ENGAGEMENT_METRICS.md](docs/ENGAGEMENT_METRICS.md).
- Engagement metrics for modular voice interviews (Phase 1, observational).
  Off by default; enable per agent with **Track engagement metrics**. Each
  participant turn records response latency, answer length, speech rate, filler
  count, and audio energy, plus a 0–1 rule-based score and label
  (low/medium/high). Metrics are stored per session, shown on the session detail
  page, and included in the CSV and JSON exports. This does not change the
  interview. See [docs/ENGAGEMENT_METRICS.md](docs/ENGAGEMENT_METRICS.md).

## 2026-05-21

### Added

- Session audio recording for web voice interviews (modular and voice-to-voice).
  Off by default; enable per agent with **Store interview audio**. Each session
  writes `session_user.wav`, `session_agent.wav`, and `manifest.json` under a
  study/agent/participant/session path. Storage is local (`AUDIO_STORAGE_*`) or
  S3-compatible (`AUDIO_S3_*`), configurable in Settings or `.env`. See
  [docs/AUDIO_RECORDING.md](docs/AUDIO_RECORDING.md).

## 2026-05-19

### Fixed

- Dashboard and participant UI polish: clearer API validation messages, load
  failure states on agent/session/settings pages (no silent empty forms or
  overwrite-on-save), export success and error toasts instead of `alert`,
  session list refresh errors and local-timezone date filters, and honest
  copy on admin session terminate.
- Voice interviews show a clear error when the microphone is blocked or
  unavailable instead of staying on an active call with no audio.
- Live session monitor drops the LIVE badge when the WebSocket disconnects;
  terminate stays available while the session is still active in the database.
- Agent form validation for empty custom models, structured mode with no
  questions, invalid widget hex colours, and non-numeric duration fields;
  predefined participant links prompt you to save the agent first.

### Changed

- Logout with authentication disabled returns to the home page instead of
  the login screen. Ending an interview early shows different copy from a
  normal completion. Chat send has an accessible label; interview type
  toggles expose radio semantics.

## 2026-05-15

### Fixed

- Text chat sessions no longer die when iOS Safari backgrounds the tab
  ([#13](https://github.com/oasis-surveys/oasis-platform/issues/13)).
  The WebSocket had zero traffic between messages, so iOS killed it as idle
  after ~60s. Fix adds a lightweight keepalive ping every 20s from the backend
  plus a Caddy-level keepalive on the proxy. The ping stops when the session
  ends. Voice sessions were never affected because continuous audio frames
  already act as a natural heartbeat. Tested via USB to macOS using Safari
  Web Inspector to confirm pings flow and the socket survives app switches.
  This is not a reconnect/resume implementation, just a keepalive to prevent
  the disconnect from happening in the first place. A full reconnect flow
  could be added later but has privacy implications for research contexts
  since resuming a session likely requires tying it to an IP or persistent
  connection identifier, which may conflict with anonymous/pseudonymous
  participant setups.

### Changed

- Gemini 3.1 Flash Lite model ID updated from preview to GA
  (`gemini-3.1-flash-lite-preview` to `gemini-3.1-flash-lite`). Google is
  discontinuing the preview endpoint on May 25, 2026.

## 2026-05-07

### Added

- `gpt-realtime-2` in the voice-to-voice model dropdown ([OpenAI announcement](https://developers.openai.com/api/docs/models/gpt-realtime-2)).
  Picks up the new model with no backend changes since the V2V path passes
  the model name straight through to OpenAI's Realtime WebSocket. The new
  `reasoning_effort` parameter that gpt-realtime-2 supports is not exposed
  yet because pipecat's `SessionProperties` doesn't have the field; the
  model runs at OpenAI's default effort until pipecat adds it. Tracked
  with a TODO in `runner.py`.

## 2026-05-06

### Fixed

- Text chat now routes `custom/<model>` agents through the configured
  OpenAI-compatible endpoint (`OPENAI_COMPATIBLE_LLM_URL`) instead of falling
  through to OpenAI with the wrong base URL. Voice already handled this; text
  was missing the branch. Reported by [@robertgartman](https://github.com/robertgartman)
  in [#7](https://github.com/oasis-surveys/oasis-platform/issues/7), running
  OpenRouter via the custom-LLM setting.

## 2026-04-28

### Added

- Custom language code option in the agent form. Pick **Custom (provider code)**
  to enter any provider-specific code (e.g. `fi`, `pt-BR`, `cmn-Hans-CN`)
  instead of being limited to the twelve preset languages.

## 1.0.0 — 2026-03

Initial public release.

[1.0.0]: https://github.com/oasis-surveys/oasis-platform/releases/tag/v1.0.0
