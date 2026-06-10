interface TrackEngagementToggleProps {
  enabled: boolean;
  onChange: (enabled: boolean) => void;
  disabled?: boolean;
  disabledReason?: string;
  description?: string;
}

const DEFAULT_DESCRIPTION =
  "Record per-turn engagement signals (response latency, answer length, speech rate, filler words) and a score for each participant turn. Observational only; it does not change the interview. Available for modular voice interviews. Off by default.";

export default function TrackEngagementToggle({
  enabled,
  onChange,
  disabled = false,
  disabledReason,
  description = DEFAULT_DESCRIPTION,
}: TrackEngagementToggleProps) {
  const isOn = enabled && !disabled;

  return (
    <div>
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div className="min-w-0">
          <p
            className={`text-sm font-medium ${
              disabled ? "text-gray-400" : "text-gray-900"
            }`}
          >
            Track engagement metrics
          </p>
          <p className="text-xs text-gray-500 mt-1 max-w-xl">{description}</p>
        </div>

        <div className="flex items-center gap-3 shrink-0">
          <span
            className={`text-xs font-semibold uppercase tracking-wide w-7 text-right transition-colors ${
              isOn ? "text-gray-400" : "text-gray-900"
            } ${disabled ? "opacity-40" : ""}`}
          >
            Off
          </span>

          <button
            type="button"
            role="switch"
            aria-checked={isOn}
            aria-label="Track engagement metrics"
            disabled={disabled}
            onClick={() => !disabled && onChange(!enabled)}
            className={`relative inline-flex h-8 w-14 shrink-0 items-center rounded-full transition-colors duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-gray-900 focus-visible:ring-offset-2 ${
              isOn ? "bg-gray-900" : "bg-gray-200"
            } ${disabled ? "cursor-not-allowed opacity-50" : ""}`}
          >
            <span
              className={`inline-block h-6 w-6 rounded-full bg-white shadow-md transition-transform duration-200 ease-in-out ${
                isOn ? "translate-x-7" : "translate-x-1"
              }`}
            />
          </button>

          <span
            className={`text-xs font-semibold uppercase tracking-wide w-7 transition-colors ${
              isOn ? "text-gray-900" : "text-gray-400"
            } ${disabled ? "opacity-40" : ""}`}
          >
            On
          </span>
        </div>
      </div>

      {disabled && disabledReason && (
        <div className="mt-3 flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2">
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
          <p className="text-xs text-amber-900/90">{disabledReason}</p>
        </div>
      )}
    </div>
  );
}
