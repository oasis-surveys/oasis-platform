import { useState } from "react";

interface StoreAudioToggleProps {
  enabled: boolean;
  onChange: (enabled: boolean) => void;
}

export default function StoreAudioToggle({ enabled, onChange }: StoreAudioToggleProps) {
  const [showGdprModal, setShowGdprModal] = useState(false);

  const handleToggle = () => {
    if (enabled) {
      onChange(false);
      return;
    }
    setShowGdprModal(true);
  };

  const confirmEnable = () => {
    onChange(true);
    setShowGdprModal(false);
  };

  return (
    <>
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div className="min-w-0">
          <p className="text-sm font-medium text-gray-900">Store interview audio</p>
          <p className="text-xs text-gray-500 mt-1 max-w-xl">
            Save session audio for web voice interviews (session_user.wav and
            session_agent.wav). Off by default for this agent.
          </p>
        </div>

        <div className="flex items-center gap-3 shrink-0">
          <span
            className={`text-xs font-semibold uppercase tracking-wide w-7 text-right transition-colors ${
              enabled ? "text-gray-400" : "text-gray-900"
            }`}
          >
            Off
          </span>

          <button
            type="button"
            role="switch"
            aria-checked={enabled}
            aria-label="Store interview audio"
            onClick={handleToggle}
            className={`relative inline-flex h-8 w-14 shrink-0 items-center rounded-full transition-colors duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-gray-900 focus-visible:ring-offset-2 ${
              enabled ? "bg-gray-900" : "bg-gray-200"
            }`}
          >
            <span
              className={`inline-block h-6 w-6 rounded-full bg-white shadow-md transition-transform duration-200 ease-in-out ${
                enabled ? "translate-x-7" : "translate-x-1"
              }`}
            />
          </button>

          <span
            className={`text-xs font-semibold uppercase tracking-wide w-7 transition-colors ${
              enabled ? "text-gray-900" : "text-gray-400"
            }`}
          >
            On
          </span>
        </div>
      </div>

      {showGdprModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 p-4"
          role="presentation"
          onClick={() => setShowGdprModal(false)}
        >
          <div
            role="dialog"
            aria-labelledby="gdpr-audio-title"
            aria-modal="true"
            className="w-full max-w-md rounded-2xl bg-white shadow-2xl border border-amber-200"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="p-6 border-b border-amber-100 bg-amber-50 rounded-t-2xl">
              <div className="flex items-start gap-3">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-amber-100 text-amber-800">
                  <svg
                    className="h-5 w-5"
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
                </div>
                <div>
                  <h2 id="gdpr-audio-title" className="text-base font-bold text-gray-900">
                    GDPR and ethics approval required
                  </h2>
                  <p className="text-sm text-amber-900/90 mt-1">
                    Turning on audio storage has legal and ethical implications.
                  </p>
                </div>
              </div>
            </div>

            <div className="p-6 space-y-3 text-sm text-gray-700">
              <p>
                Storing raw voice recordings is <strong>personal data</strong> under the
                GDPR. You should only enable this if:
              </p>
              <ul className="list-disc pl-5 space-y-1.5 text-gray-600">
                <li>Your participant information sheet mentions audio recording and storage.</li>
                <li>You have a lawful basis (typically explicit consent) documented in your protocol.</li>
                <li>Your ethics or IRB review covers retention, access, and deletion of audio files.</li>
                <li>Your institution approves where files are stored (this server or your S3 bucket).</li>
              </ul>
              <p className="text-xs text-gray-500 pt-1">
                OASIS does not provide legal advice. If you are unsure, keep this setting off and
                use transcript-only capture.
              </p>
            </div>

            <div className="flex flex-col-reverse sm:flex-row sm:justify-end gap-2 p-6 pt-0">
              <button
                type="button"
                onClick={() => setShowGdprModal(false)}
                className="btn-secondary w-full sm:w-auto"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={confirmEnable}
                className="btn-primary w-full sm:w-auto"
              >
                I confirm, enable audio storage
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
