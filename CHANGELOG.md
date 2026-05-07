# Changelog

All notable changes to OASIS are tracked here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), with date-based
sections — versions are added retroactively when a release is cut.

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
