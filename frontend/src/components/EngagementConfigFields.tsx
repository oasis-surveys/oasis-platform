import type { EngagementConfig, EngagementWeights } from "../lib/api";
import HelpTooltip from "./HelpTooltip";

interface EngagementConfigFieldsProps {
  config: EngagementConfig;
  onChange: (config: EngagementConfig) => void;
}

const WEIGHT_LABELS: Record<keyof EngagementWeights, string> = {
  length: "Answer length",
  latency: "Response speed",
  rate: "Speech rate",
  fillers: "Filler words",
  energy: "Audio energy",
};

function NumberField({
  label,
  value,
  min,
  max,
  step,
  tooltip,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  tooltip?: string;
  onChange: (v: number) => void;
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs font-medium text-gray-600 flex items-center gap-1.5">
        {label}
        {tooltip && <HelpTooltip text={tooltip} />}
      </span>
      <input
        type="number"
        className="input !py-1.5 !text-sm"
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={(e) => {
          const v = parseFloat(e.target.value);
          if (!Number.isNaN(v)) onChange(v);
        }}
      />
    </label>
  );
}

export default function EngagementConfigFields({
  config,
  onChange,
}: EngagementConfigFieldsProps) {
  const set = (patch: Partial<EngagementConfig>) =>
    onChange({ ...config, ...patch });
  const setWeight = (key: keyof EngagementWeights, v: number) =>
    onChange({ ...config, weights: { ...config.weights, [key]: v } });

  return (
    <div className="mt-4 rounded-lg border border-gray-100 bg-gray-50/60 p-4">
      <p className="text-xs font-semibold text-gray-700 mb-3">
        Engagement tuning
      </p>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        <NumberField
          label="Window (turns)"
          tooltip="How many consecutive turns are considered when detecting sustained disengagement or a positive streak."
          value={config.window_size}
          min={2}
          max={10}
          step={1}
          onChange={(v) => set({ window_size: Math.round(v) })}
        />
        <NumberField
          label="Low threshold"
          tooltip="A turn scoring below this (0–1) is labelled low engagement."
          value={config.low_threshold}
          min={0}
          max={1}
          step={0.01}
          onChange={(v) => set({ low_threshold: v })}
        />
        <NumberField
          label="High threshold"
          tooltip="A turn scoring at or above this (0–1) is labelled high engagement."
          value={config.high_threshold}
          min={0}
          max={1}
          step={0.01}
          onChange={(v) => set({ high_threshold: v })}
        />
        <NumberField
          label="Long latency (s)"
          tooltip="A turn whose response latency is at or above this many seconds gets a long_latency flag."
          value={Math.round((config.long_latency_ms / 1000) * 10) / 10}
          min={0.5}
          max={30}
          step={0.5}
          onChange={(v) => set({ long_latency_ms: Math.round(v * 1000) })}
        />
        <NumberField
          label="Short answer (words)"
          tooltip="A turn with fewer than this many words gets a very_short_answer flag."
          value={config.short_answer_words}
          min={1}
          max={20}
          step={1}
          onChange={(v) => set({ short_answer_words: Math.round(v) })}
        />
      </div>

      <details className="mt-3 group">
        <summary className="cursor-pointer text-xs font-medium text-gray-500 hover:text-gray-800 select-none">
          Advanced: score weights
        </summary>
        <p className="text-[11px] text-gray-400 mt-2">
          Relative weight of each signal in the turn score. Only the signals
          available for a turn are used; weights are renormalized automatically.
        </p>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mt-2">
          {(Object.keys(WEIGHT_LABELS) as (keyof EngagementWeights)[]).map(
            (key) => (
              <NumberField
                key={key}
                label={WEIGHT_LABELS[key]}
                value={config.weights[key]}
                min={0}
                max={1}
                step={0.05}
                onChange={(v) => setWeight(key, v)}
              />
            )
          )}
        </div>
      </details>
    </div>
  );
}
