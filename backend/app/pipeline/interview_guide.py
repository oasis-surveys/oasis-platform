"""
Structured Interview Guide — System-prompt-based approach.

Instead of a complex stateful processor, we construct a detailed system
prompt that tells the LLM exactly how to conduct the structured interview.

Modern LLMs (GPT-4o, GPT-5, Gemini 2.x) follow structured protocols
remarkably well.  We layer a lightweight turn-counter on top that nudges
the model if it lingers too long on one question.

Architecture
------------
1.  `build_structured_prompt()`  – creates the full system prompt from
    the researcher's guide + their base prompt.
2.  `InterviewGuideProcessor`   – a Pipecat FrameProcessor that sits in
    the pipeline and monitors agent/user turns.  After *max_follow_ups*
    exchanges on a question it injects an LLM system message to advance.
"""

from __future__ import annotations

import json
from typing import Optional

from loguru import logger


# ── Prompt builder ──────────────────────────────────────────────────────────

def build_structured_prompt(
    base_prompt: str,
    guide: dict,
) -> str:
    """
    Build a comprehensive system prompt that encodes the interview guide.

    Parameters
    ----------
    base_prompt : str
        The researcher's base system prompt (personality, context, etc.).
    guide : dict
        The interview_guide JSON from the Agent model.
        Expected shape:
        {
          "questions": [
            {
              "text": "...",
              "probes": ["...", "..."],
              "max_follow_ups": 3,
              "transition": "..."        # optional
            },
            ...
          ],
          "closing_message": "..."        # optional
        }

    Returns
    -------
    str
        Full system prompt with the interview protocol embedded.
    """
    questions = guide.get("questions", [])
    closing = guide.get(
        "closing_message",
        "Thank you for your time. This concludes our interview.",
    )

    if not questions:
        return base_prompt

    # Build the question guide section
    guide_lines = []
    for i, q in enumerate(questions, 1):
        text = q.get("text", "")
        probes = q.get("probes", [])
        max_fu = q.get("max_follow_ups", 3)
        transition = q.get("transition", "")

        guide_lines.append(f"### Question {i}")
        guide_lines.append(f"**Ask:** {text}")
        if probes:
            guide_lines.append("**Example probes to deepen the response:**")
            for p in probes:
                guide_lines.append(f"  - {p}")
        guide_lines.append(
            f"**Follow-ups:** Ask up to {max_fu} follow-up questions to "
            f"explore this topic thoroughly. If the participant has already "
            f"given a comprehensive answer, you may move on sooner."
        )
        if transition:
            guide_lines.append(f"**Transition:** {transition}")
        guide_lines.append("")

    question_guide = "\n".join(guide_lines)

    structured_section = f"""

---

## STRUCTURED INTERVIEW PROTOCOL

You are conducting a **structured interview**. Follow this question guide
in the exact order below.  For each question:

1.  Ask the main question naturally (do not read it verbatim — paraphrase
    to match the conversational flow).
2.  Listen to the participant's response carefully.
3.  Ask follow-up probes to get deeper, richer answers.  Use the example
    probes as inspiration but adapt them based on what the participant
    actually says.
4.  When you have explored the topic sufficiently (or reached the maximum
    follow-ups), transition naturally to the next question.
5.  Do **not** skip questions.  Do **not** change the order.
6.  After the final question, deliver the closing message and end the
    interview gracefully.

{question_guide}

### Closing
When all questions are complete, say: "{closing}"

---

**Important rules:**
- Stay on topic.  If the participant goes off on a tangent, gently steer
  them back to the current question.
- Be warm, empathetic, and professional at all times.
- Never reveal that you are following a script or question guide.
- Adapt your probing based on the participant's actual answers — do not
  ask probes that are redundant given what they already said.
- If a participant's answer already covers the next question, acknowledge
  it and still ask the question to give them a chance to add more.
"""

    return base_prompt.rstrip() + structured_section
