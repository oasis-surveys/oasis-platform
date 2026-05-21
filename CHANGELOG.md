# Changelog

All notable changes to OASIS are tracked here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), with date-based
sections — versions are added retroactively when a release is cut.

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
