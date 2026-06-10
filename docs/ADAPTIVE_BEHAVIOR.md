# Adaptive behavior

This document describes adaptive behavior: how the engagement signals can be
used to adjust the agent during an interview, what actions are available, how it
is configured, and how every action is recorded for disclosure.

Adaptive behavior builds on [engagement metrics](ENGAGEMENT_METRICS.md). It is
off by default, scoped per agent, and starts in a non-acting "shadow" mode.

## What it is

When adaptive behavior is enabled, OASIS evaluates a small per-agent policy after
each participant turn. The policy maps engagement triggers (rolling-window events
or per-turn flags) to a curated set of actions. Two kinds of action are
supported:

- **Prompt actions** inject a short system instruction before the agent's next
  turn (for example, offer a break, soften the next question, encourage
  elaboration).
- **Pace actions** change the agent's speaking speed for the modular voice
  pipeline (slow down, reset pace).

The policy is rule-based and readable. There is no model and no training data;
you can always explain why an action fired.

## Shadow and live modes

Adaptive behavior has two modes, chosen per agent:

- **Shadow (default)** — the policy is evaluated and every intended action is
  recorded, but nothing is applied. The conversation is unchanged. Use this to
  review what the policy *would* do on real sessions before turning it on.
- **Live** — actions are applied during the interview. Prompt actions inject an
  instruction; pace actions change speaking speed. Sessions where live
  adaptation can occur are flagged (`sessions.adaptive_active`), and every action
  is still recorded.

Switching from shadow to live is a deliberate choice in the agent form, with an
in-form warning.

## Scope and limitations

- Available wherever engagement metrics are: the **modular voice pipeline** and
  **text chat**. Voice-to-voice pipelines are not supported.
- **Pace actions apply to modular voice only.** They are no-ops for text chat,
  and for TTS providers that do not accept a runtime speed setting (currently
  applied for ElevenLabs, OpenAI, and Cartesia). When a pace action cannot be
  applied it is still recorded, with a note.
- At most **one prompt action and one pace action fire per turn**. If several
  rules match, the first matching rule of each kind (by list order) wins.
- Each rule has an optional **cooldown** so the same rule does not fire on every
  qualifying turn.
- Adaptive behavior requires engagement tracking to be on for the agent.

## Triggers

A rule fires on one trigger. Triggers are the engagement events and per-turn
flags already produced by the engagement feature:

| Trigger | Source |
|---------|--------|
| `sustained_disengagement` | Event: the last `window_size` turns are all low. |
| `positive_engagement_streak` | Event: the last `window_size` turns are all high. |
| `recovery_after_dip` | Event: a high turn follows a recent low turn. |
| `long_latency` | Per-turn flag: response latency at or above the configured threshold. |
| `very_short_answer` | Per-turn flag: fewer than the configured word count. |
| `high_filler` | Per-turn flag: 15% or more filler / hedging. |

## Actions

Actions are curated and built-in. Prompt actions ship with a default
instruction; a rule may override it with its own `custom_instruction`.

| Action | Type | Default behavior |
|--------|------|------------------|
| `offer_break` | prompt | Gently offer a short break or a lighter topic. |
| `soften_next_probe` | prompt | Make the next question gentler and less probing. |
| `encourage_elaboration` | prompt | Warmly invite the participant to say more. |
| `acknowledge_effort` | prompt | Briefly acknowledge engagement before continuing. |
| `privacy_check` | prompt | Check in on comfort and privacy in one sentence. |
| `slow_down` | pace | Lower speaking speed (default 0.9). |
| `reset_pace` | pace | Return speaking speed to normal (default 1.0). |

Pace speed is clamped to the 0.7–1.2 range.

## How to enable it

1. Open the agent form for a modular voice or text agent and turn on **Track
   engagement metrics**.
2. Turn on **Enable adaptive behavior**. It starts in **Shadow** mode.
3. Add one or more rules: pick a trigger ("When"), an action ("Do"), an optional
   custom instruction, and a cooldown.
4. Optionally switch the mode to **Live** to apply actions.
5. Save the agent.

It is off by default. Enabling or changing it affects new sessions only.

## How it works

For the modular voice pipeline, an `AdaptiveBehaviorProcessor` runs directly
after the engagement processor. It reads the turn's engagement signals, evaluates
the policy, and (in live mode) pushes an `LLMMessagesAppendFrame` for prompt
actions or a `TTSUpdateSettingsFrame` for pace actions before the next agent
turn. In text chat the same policy runs inline after each user turn; prompt
actions append a system message before the next model call.

## Where the data lives

Every action — applied or shadow — is written to the `adaptive_actions` table,
one row per action, with the triggering turn's sequence number, the trigger, the
action, the mode, and a `detail` object (whether it was applied, the instruction
or parameters, and any note). The agent's policy is stored in
`agents.adaptive_policy` (JSON) alongside `agents.adaptive_enabled`. Whether a
given session could be adapted live is stored in `sessions.adaptive_active`.

Migrations add the table and columns:

```
alembic upgrade head
```

## Reading the data

### Dashboard

The session detail page's **Engagement metrics** card shows an **Adaptive
actions** section when a session has any. Each row lists the action, the
trigger, the turn, and whether it was applied (live) or only logged (shadow). A
badge shows whether the session ran in live or shadow mode.

### API

```
GET /studies/{study_id}/agents/{agent_id}/sessions/{session_id}/engagement
```

The response includes `adaptive_active` and an `adaptive_actions` list.

### Exports

- **CSV**: each transcript row gains an `adaptive_actions` column listing the
  actions triggered on that participant turn, tagged with mode and whether they
  were applied.
- **JSON**: each session gains an `adaptive` object with `active` and the full
  `actions` list.

## Consent and ethics

In live mode the agent changes its behavior in response to inferred engagement.
This is a more involved intervention than passive measurement. Disclose it in
your participant information and ethics or IRB review, keep the recorded action
log for transparency, and prefer shadow mode while validating a policy.
