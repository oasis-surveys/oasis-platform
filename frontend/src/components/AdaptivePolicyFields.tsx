import {
  ADAPTIVE_ACTION_META,
  ADAPTIVE_TRIGGER_LABELS,
  type AdaptiveActionId,
  type AdaptivePolicy,
  type AdaptiveRule,
  type AdaptiveTrigger,
} from "../lib/api";
import HelpTooltip from "./HelpTooltip";

interface AdaptivePolicyFieldsProps {
  policy: AdaptivePolicy;
  onChange: (policy: AdaptivePolicy) => void;
  // Text agents can't change speaking pace; hide tts_speed actions.
  allowSpeed?: boolean;
}

const TRIGGERS = Object.keys(ADAPTIVE_TRIGGER_LABELS) as AdaptiveTrigger[];
const ACTIONS = Object.keys(ADAPTIVE_ACTION_META) as AdaptiveActionId[];

function newRule(): AdaptiveRule {
  return {
    on: "sustained_disengagement",
    action: "offer_break",
    custom_instruction:
      ADAPTIVE_ACTION_META.offer_break.defaultInstruction ?? null,
    cooldown_seconds: 60,
    params: {},
  };
}

export default function AdaptivePolicyFields({
  policy,
  onChange,
  allowSpeed = true,
}: AdaptivePolicyFieldsProps) {
  const actionOptions = ACTIONS.filter(
    (a) => allowSpeed || ADAPTIVE_ACTION_META[a].type !== "tts_speed"
  );

  const setMode = (mode: "shadow" | "live") => onChange({ ...policy, mode });

  const updateRule = (idx: number, patch: Partial<AdaptiveRule>) => {
    const rules = policy.rules.map((r, i) =>
      i === idx ? { ...r, ...patch } : r
    );
    onChange({ ...policy, rules });
  };

  const removeRule = (idx: number) =>
    onChange({ ...policy, rules: policy.rules.filter((_, i) => i !== idx) });

  const addRule = () => onChange({ ...policy, rules: [...policy.rules, newRule()] });

  return (
    <div className="mt-4 rounded-lg border border-gray-100 bg-gray-50/60 p-4">
      <p className="text-xs font-semibold text-gray-700 mb-3">
        Adaptive policy
      </p>

      {/* Mode selector */}
      <div className="flex flex-col gap-2">
        <span className="text-xs font-medium text-gray-600 flex items-center gap-1.5">
          Mode
          <HelpTooltip text="Shadow logs the actions the policy would take without applying them, so you can review behavior safely. Live applies the actions during the interview." />
        </span>
        <div className="inline-flex rounded-lg border border-gray-200 bg-white p-0.5 w-fit">
          {(["shadow", "live"] as const).map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => setMode(m)}
              className={`px-4 py-1.5 text-xs font-semibold rounded-md transition-colors ${
                policy.mode === m
                  ? "bg-gray-900 text-white"
                  : "text-gray-500 hover:text-gray-800"
              }`}
            >
              {m === "shadow" ? "Shadow (log only)" : "Live (apply)"}
            </button>
          ))}
        </div>
        {policy.mode === "live" && (
          <div className="mt-1 flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2">
            <svg
              className="h-4 w-4 shrink-0 text-amber-600 mt-0.5"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
              aria-hidden
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z"
              />
            </svg>
            <p className="text-xs text-amber-900/90">
              In live mode the agent changes its behavior for real participants.
              Sessions are flagged as adaptive, and every action is recorded.
            </p>
          </div>
        )}
      </div>

      {/* Rules */}
      <div className="mt-4 flex flex-col gap-3">
        {policy.rules.length === 0 && (
          <p className="text-[11px] text-gray-400">
            No rules yet. Add a rule to map an engagement trigger to an action.
          </p>
        )}
        {policy.rules.map((rule, idx) => {
          const actionType = ADAPTIVE_ACTION_META[rule.action]?.type;
          return (
            <div
              key={idx}
              className="rounded-lg border border-gray-200 bg-white p-3"
            >
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <label className="flex flex-col gap-1">
                  <span className="text-xs font-medium text-gray-600">
                    When
                  </span>
                  <select
                    className="input !py-1.5 !text-sm"
                    value={rule.on}
                    onChange={(e) =>
                      updateRule(idx, { on: e.target.value as AdaptiveTrigger })
                    }
                  >
                    {TRIGGERS.map((t) => (
                      <option key={t} value={t}>
                        {ADAPTIVE_TRIGGER_LABELS[t]}
                      </option>
                    ))}
                  </select>
                </label>

                <label className="flex flex-col gap-1">
                  <span className="text-xs font-medium text-gray-600">Do</span>
                  <select
                    className="input !py-1.5 !text-sm"
                    value={rule.action}
                    onChange={(e) => {
                      const action = e.target.value as AdaptiveActionId;
                      updateRule(idx, {
                        action,
                        params: {},
                        custom_instruction:
                          ADAPTIVE_ACTION_META[action].defaultInstruction ??
                          null,
                      });
                    }}
                  >
                    {actionOptions.map((a) => (
                      <option key={a} value={a}>
                        {ADAPTIVE_ACTION_META[a].label}
                        {ADAPTIVE_ACTION_META[a].type === "tts_speed"
                          ? " (pace)"
                          : ""}
                      </option>
                    ))}
                  </select>
                </label>
              </div>

              {actionType === "prompt" && (
                <label className="mt-3 flex flex-col gap-1">
                  <span className="text-xs font-medium text-gray-600 flex items-center gap-1.5">
                    Instruction sent to the agent
                    <HelpTooltip text="This exact text is injected as guidance before the agent's next turn when the rule fires. Edit it freely — it works like a prompt template. Clearing it restores the built-in default." />
                  </span>
                  <textarea
                    className="input !py-1.5 !text-sm"
                    rows={3}
                    placeholder="Leave blank to use the built-in instruction"
                    value={
                      rule.custom_instruction ??
                      ADAPTIVE_ACTION_META[rule.action]?.defaultInstruction ??
                      ""
                    }
                    onChange={(e) =>
                      updateRule(idx, {
                        custom_instruction: e.target.value || null,
                      })
                    }
                  />
                </label>
              )}

              {actionType === "tts_speed" && (
                <label className="mt-3 flex flex-col gap-1 w-40">
                  <span className="text-xs font-medium text-gray-600">
                    Speed (0.7–1.2)
                  </span>
                  <input
                    type="number"
                    className="input !py-1.5 !text-sm"
                    min={0.7}
                    max={1.2}
                    step={0.05}
                    value={rule.params.speed ?? (rule.action === "slow_down" ? 0.9 : 1.0)}
                    onChange={(e) => {
                      const v = parseFloat(e.target.value);
                      if (!Number.isNaN(v))
                        updateRule(idx, { params: { ...rule.params, speed: v } });
                    }}
                  />
                </label>
              )}

              <div className="mt-3 flex items-end justify-between gap-3">
                <label className="flex flex-col gap-1 w-40">
                  <span className="text-xs font-medium text-gray-600 flex items-center gap-1.5">
                    Cooldown (s)
                    <HelpTooltip text="Minimum seconds before this rule can fire again in the same session." />
                  </span>
                  <input
                    type="number"
                    className="input !py-1.5 !text-sm"
                    min={0}
                    max={3600}
                    step={5}
                    value={rule.cooldown_seconds}
                    onChange={(e) => {
                      const v = parseInt(e.target.value);
                      updateRule(idx, {
                        cooldown_seconds: Number.isNaN(v) ? 0 : v,
                      });
                    }}
                  />
                </label>
                <button
                  type="button"
                  onClick={() => removeRule(idx)}
                  className="text-xs font-medium text-red-600 hover:text-red-800 pb-2"
                >
                  Remove
                </button>
              </div>
            </div>
          );
        })}

        <button
          type="button"
          onClick={addRule}
          className="self-start text-xs font-semibold text-gray-700 hover:text-gray-900 rounded-md border border-dashed border-gray-300 px-3 py-1.5"
        >
          + Add rule
        </button>
      </div>
    </div>
  );
}
