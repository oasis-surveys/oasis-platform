# Engagement metrics

This document describes the engagement metrics feature: what it measures, how
it is computed, where the data is stored, and how to read it. It is
observational only. Nothing here changes how the agent behaves during an
interview.

To act on these signals (offer a break, soften a question, adjust pace), see
[adaptive behavior](ADAPTIVE_BEHAVIOR.md), which is built on top of this feature
and is off by default.

## What it is

When engagement tracking is enabled for an agent, OASIS computes a small set of
signals for each participant turn and assigns the turn a score between 0 and 1
with a coarse label (low, medium, or high). The numbers are meant to help
researchers spot turns where a participant was hesitant, terse, or disengaged,
and to provide an exportable record alongside the transcript. Both modular voice
interviews and text chat interviews are supported; voice has the full signal
set, text a lexical and timing subset (see below).

The score is produced by a rule-based scorer with readable, per-agent
thresholds, so you can always explain why a turn scored the way it did. There is
no model and no training data.

## Scope and limitations

- Available for the **modular voice pipeline** (STT, LLM, TTS) and for **text
  chat** agents. The voice-to-voice pipelines (OpenAI Realtime, Gemini Live) do
  not expose the participant audio and turn timing the same way, so metrics are
  not computed for them. The toggle has no effect on those agents.
- The metrics are heuristics. They are useful as a relative signal within a
  session, not as an absolute measure of a person's state. Treat them
  accordingly in any analysis.

## How to enable it

1. Open the agent form for a modular voice or text agent.
2. Under **Interview Settings**, turn on **Track engagement metrics**.
3. Save the agent.

It is off by default. Enabling it for an existing agent affects new sessions
only.

## Text interviews

Text chat exposes only lexical and timing signals, so a turn records:

- `response_latency_ms` — time from the agent's message being sent to the
  participant's message arriving. This is **reading + thinking + typing** time,
  not spoken response time, so it runs much longer than voice latency. The text
  profile uses wider thresholds accordingly, and scores are not directly
  comparable across modalities.
- `word_count` and `char_count`.
- `filler_count` — for text this counts lexical **hedging** ("maybe", "i think",
  "i'm not sure"), the typed analogue of spoken fillers.

`voiced_ms`, `speech_rate_wpm`, and `rms_energy` are not available for text and
stay null. The score uses whatever components are present (length, latency,
hedging), and the same events apply.

## What gets measured

Per participant turn:

| Feature | Meaning |
|---------|---------|
| `response_latency_ms` | Time from the agent finishing speaking to the participant starting to speak. |
| `voiced_ms` | Length of the participant's turn from start to stop of speech. |
| `word_count` | Words in the transcribed turn. |
| `char_count` | Characters in the transcribed turn. |
| `speech_rate_wpm` | Words divided by voiced minutes. |
| `filler_count` | Count of filler words ("um", "uh", "like", and so on), per language. |
| `rms_energy` | Mean normalized amplitude of the participant audio for the turn (0 to 1). |
| `score` | Rule-based engagement score from 0 to 1. |
| `label` | `low` (below 0.34), `medium`, or `high` (0.67 and above). |

Latency is measured from the upstream `BotStoppedSpeakingFrame` to the next
`UserStartedSpeakingFrame`. Audio energy is computed on the participant audio
buffer captured between the start and stop of the turn, using the standard
library only, so there is no extra dependency and no meaningful added latency
on the pipeline.

## How the score is computed

The score is a weighted average of the components that are available for a turn.
If a component is missing (for example, no latency on the first turn), the
remaining weights are renormalized so the score still falls between 0 and 1.

| Component | Weight | Full credit when |
|-----------|--------|------------------|
| length | 0.35 | 25 or more words |
| latency | 0.25 | 300 ms or faster, scaling to 0 at 4000 ms |
| rate | 0.15 | 90 to 170 wpm |
| fillers | 0.15 | no filler words, scaling to 0 at 15% of words |
| energy | 0.10 | normalized amplitude of 0.12 or higher |

Each turn can also carry flags: `long_latency` (at or above the configured
seconds), `very_short_answer` (fewer than the configured word count), and
`high_filler` (15% or more filler words).

## Events

On top of per-turn scoring, a rolling window over recent turns produces discrete
events:

| Event | Fires when |
|-------|------------|
| `sustained_disengagement` | The last `window_size` turns are all labelled low. |
| `positive_engagement_streak` | The last `window_size` turns are all labelled high. |
| `recovery_after_dip` | A high turn follows at least one recent low turn. |

Each event fires once when its condition first becomes true and re-arms only
after the condition clears, so a sustained state does not produce one row per
turn. Events are stored in the `engagement_events` table, one row per event,
with the triggering turn's sequence number.

## Configuration

Thresholds and weights are tunable per agent. With tracking on, the agent form
shows an **Engagement tuning** panel:

- Window (turns) for event detection.
- Low and high score thresholds for the turn label.
- Long-latency flag (seconds) and short-answer flag (words).
- Advanced: the relative weight of each score component.

These are stored in the agent's `engagement_config` (JSON). Any field left unset
falls back to the built-in defaults in `backend/app/engagement/scorer.py`, so an
agent only persists the values it changes.

## Where the data lives

Per-turn metrics are written to the `engagement_turns` table, one row per
participant turn, linked to the session and to the matching transcript sequence
number. Events are written to the `engagement_events` table. The transcript
itself is unchanged.

Migrations add these tables and the `agents.track_engagement` and
`agents.engagement_config` columns:

```
alembic upgrade head
```

## Reading the data

### Dashboard

The session detail page shows an **Engagement metrics** card when a session has
recorded turns. It lists a session summary (average score, average latency,
average words, count of low-engagement turns), any events, and a per-turn
breakdown.

### API

```
GET /studies/{study_id}/agents/{agent_id}/sessions/{session_id}/engagement
```

Returns the session summary, the per-turn rows, and the events.

### Exports

- **CSV**: each transcript row gains `engagement_score`, `engagement_label`,
  `response_latency_ms`, `word_count`, `speech_rate_wpm`, `filler_count`, and
  `engagement_events`. These are populated on participant rows that have
  metrics; the `engagement_events` cell lists any events the turn triggered.
- **JSON**: each session gains an `engagement` object with the summary, the
  per-turn list, and the events.

## Consent and ethics

Engagement metrics are derived from the participant's speech timing, transcript,
and audio amplitude. They do not store new audio (audio storage is a separate,
independent setting). Even so, behavioural measurement can be sensitive. Cover
it in your participant information and ethics or IRB review if your study relies
on it, and disclose it in your methods where relevant.
