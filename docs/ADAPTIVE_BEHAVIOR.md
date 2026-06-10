# Adaptive behavior

This document describes adaptive behavior: how the engagement signals can be
used to adjust the agent during an interview, exactly what is sent to the model
when an action fires, how it is configured, and how every action is recorded
for disclosure.

Adaptive behavior builds on [engagement metrics](ENGAGEMENT_METRICS.md). It is
off by default, scoped per agent, and starts in a non-acting "shadow" mode.

## What happens when you enable it

Enabling **adaptive behavior** in the agent form does the following — nothing
more:

1. A starter policy with three editable rules appears in the form (see
   [Default policy](#default-policy)). You can change, remove, or add rules
   before saving. Nothing is active until you save the agent.
2. The mode is set to **Shadow**: in every session, the policy is evaluated
   after each participant turn and every action it *would* take is logged to
   the database — but the conversation itself is completely unchanged.
3. Only if you deliberately switch the mode to **Live** (a separate step with
   an in-form warning) do actions actually affect the interview.

Enabling or changing the policy affects new sessions only; running sessions
keep the policy they started with.

## How an action affects the conversation

Two kinds of action exist, and they are the only ways adaptive behavior ever
touches a session:

**Prompt actions** insert one guidance note into the model's conversation
context before its next turn. The participant never sees or hears this note;
it only steers the agent's next reply. Every injected note has this exact
shape:

```
[Interviewer guidance — this is an instruction for you, not something the
participant said. Follow it silently; never read it aloud, quote it, or
mention it.] <instruction text>
```

The `<instruction text>` is shown verbatim in the agent form for each rule —
what you see in the form is what gets injected. Edit it like a prompt
template, or clear it to restore the built-in default.

**Pace actions** change the agent's speaking pace (voice pipelines only). How
this is applied depends on the TTS provider — see
[Speaking pace and audio quality](#speaking-pace-and-audio-quality).

## Default policy

When you first enable adaptive behavior, the form is seeded with this starter
policy. It is plain data, not a hidden behavior — every part of it is visible
and editable in the form before you save:

| When (trigger) | Do (action) | Cooldown |
|----------------|-------------|----------|
| Sustained disengagement | Offer a break | 180 s |
| Very short answer | Encourage elaboration | 90 s |
| High filler / hedging | Soften the next question | 120 s |

## Actions and their exact default instructions

Prompt actions ship with a default instruction. The form shows it pre-filled
for each rule; the text below is exactly what is injected (after the guidance
prefix shown above) unless you edit it.

| Action | Default instruction sent to the agent |
|--------|----------------------------------------|
| `offer_break` | "The participant has shown signs of fatigue or disengagement over the last few turns. Gently offer a short break or to move to a lighter topic. Keep it brief and warm. Do not mention that this was detected automatically." |
| `soften_next_probe` | "Make your next question gentler and less probing. Lead with warmth and give the participant room to answer at their own pace." |
| `encourage_elaboration` | "The participant's recent answers have been brief. Warmly invite them to say more with a single open follow-up question." |
| `acknowledge_effort` | "Briefly acknowledge the participant's effort and engagement before continuing with the interview." |
| `privacy_check` | "Check in about the participant's comfort and privacy in one short, warm sentence before continuing." |
| `match_style` | "From now on, subtly mirror the participant's communication style: match their level of formality, their sentence length, and their energy. If they are brief and casual, be brief and casual; if they are detailed and reflective, give them room and depth. Keep the mirroring subtle — never imitate their exact words back at them, and never mention that you are adapting." |

Pace actions have a numeric speed instead of an instruction:

| Action | Type | Default |
|--------|------|---------|
| `slow_down` | pace | speed 0.9 |
| `reset_pace` | pace | speed 1.0 |

Speed values are clamped to the 0.7–1.2 range.

### Style matching ("assimilation")

The `match_style` action makes the agent mirror the participant's formality,
sentence length, and energy from the moment it fires. Attach it to a trigger
(for example `positive_engagement_streak`) to switch mirroring on
mid-interview based on engagement.

If you want the agent to mirror the participant *from the first turn,
unconditionally*, you do not need adaptive behavior at all — add the same
instruction to the agent's system prompt. Adaptive behavior is for changes
that should depend on measured engagement during the session.

## Speaking pace and audio quality

How a pace action is applied depends on the TTS provider, because providers
differ in *how* they change speed — and that difference is audible:

| Provider | Mechanism | Audio quality |
|----------|-----------|---------------|
| OpenAI (`gpt-4o-mini-tts` and other `gpt-4o-*` models) | Voice **instructions** ("Speak slowly and calmly, …") steer prosody at generation time | Natural — the model actually speaks slower, it is not post-processed |
| OpenAI (`tts-1`, `tts-1-hd`) | Numeric `speed` parameter (post-synthesis time-stretching) | Audible distortion away from 1.0 |
| ElevenLabs | Numeric `speed`, rendered natively by the voice model | Natural within 0.7–1.2 |
| Cartesia | Numeric `speed`, rendered natively | Natural within 0.7–1.2 |
| Self-hosted (OpenAI-compatible) | Numeric `speed`; behavior depends on your server | Varies |
| Azure, text chat | Not applied | The action is still recorded, with a note |

OASIS picks the mechanism automatically: agents using OpenAI `gpt-4o-*` TTS
get instruction-based pacing (no time-stretch artifacts); everything else gets
the numeric parameter. The audit row records which mechanism was used
(`detail.method` is `voice_instructions` or `speed`).

## Shadow and live modes

- **Shadow (default)** — the policy is evaluated and every intended action is
  recorded, but nothing is applied. The conversation is unchanged. Use this to
  review what the policy *would* do on real sessions before turning it on.
- **Live** — actions are applied during the interview. Prompt actions inject
  the guidance note; pace actions change speaking pace. Sessions where live
  adaptation can occur are flagged (`sessions.adaptive_active`), and every
  action is still recorded.

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

## Scope and limitations

- Available wherever engagement metrics are: the **modular voice pipeline**
  and **text chat**. Voice-to-voice pipelines are not supported.
- **Pace actions apply to modular voice only.** They are no-ops for text chat
  and unsupported providers; the action is still recorded, with a note.
- At most **one prompt action and one pace action fire per turn**. If several
  rules match, the first matching rule of each kind (by list order) wins.
- Each rule has an optional **cooldown** so the same rule does not fire on
  every qualifying turn.
- Adaptive behavior requires engagement tracking to be on for the agent.
- The policy is rule-based and readable. There is no model and no training
  data; you can always explain why an action fired.

## How to enable it

1. Open the agent form for a modular voice or text agent and turn on **Track
   engagement metrics**.
2. Turn on **Enable adaptive behavior**. The starter policy appears, in
   **Shadow** mode.
3. Review the rules: each shows its trigger, action, the exact instruction
   that will be injected (editable), and a cooldown. Adjust freely.
4. Optionally switch the mode to **Live** to apply actions.
5. Save the agent.

## How it works

For the modular voice pipeline, an `AdaptiveBehaviorProcessor` runs directly
after the engagement processor. It reads the turn's engagement signals,
evaluates the policy, and (in live mode) pushes an `LLMMessagesAppendFrame`
for prompt actions or a `TTSUpdateSettingsFrame` for pace actions before the
next agent turn. In text chat the same policy runs inline after each user
turn; prompt actions append the guidance note before the next model call.

## Where the data lives

Every action — applied or shadow — is written to the `adaptive_actions` table,
one row per action, with the triggering turn's sequence number, the trigger,
the action, the mode, and a `detail` object (whether it was applied, the
instruction or parameters, the pace mechanism, and any note). The agent's
policy is stored in `agents.adaptive_policy` (JSON) alongside
`agents.adaptive_enabled`. Whether a given session could be adapted live is
stored in `sessions.adaptive_active`.

Migrations add the table and columns:

```
alembic upgrade head
```

## Reading the data

### Dashboard

The session detail page's **Engagement metrics** card shows an **Adaptive
actions** section when a session has any. Each row lists the action, the
trigger, the turn, and whether it was applied (live) or only logged (shadow).
A badge shows whether the session ran in live or shadow mode.

### API

```
GET /studies/{study_id}/agents/{agent_id}/sessions/{session_id}/engagement
```

The response includes `adaptive_active` and an `adaptive_actions` list.

### Exports

- **CSV**: each transcript row gains an `adaptive_actions` column listing the
  actions triggered on that participant turn, tagged with mode and whether
  they were applied.
- **JSON**: each session gains an `adaptive` object with `active` and the
  full `actions` list.

## Consent and ethics

In live mode the agent changes its behavior in response to inferred
engagement. This is a more involved intervention than passive measurement.
Disclose it in your participant information and ethics or IRB review, keep the
recorded action log for transparency, and prefer shadow mode while validating
a policy.
