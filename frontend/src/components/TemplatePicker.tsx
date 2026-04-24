import { useEffect, useState } from "react";
import { templates, agents, type AgentTemplate } from "../lib/api";

interface TemplatePickerProps {
  studyId: string;
  open: boolean;
  onClose: () => void;
  onCreated: (agentId: string) => void;
}

const MODALITY_LABEL: Record<AgentTemplate["modality"], string> = {
  voice: "Voice",
  text: "Text Chat",
};

const PIPELINE_LABEL: Record<AgentTemplate["pipeline_type"], string> = {
  modular: "STT → LLM → TTS",
  voice_to_voice: "Voice-to-Voice",
};

export default function TemplatePicker({
  studyId,
  open,
  onClose,
  onCreated,
}: TemplatePickerProps) {
  const [list, setList] = useState<AgentTemplate[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    setError(null);
    templates
      .list()
      .then(setList)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load templates"))
      .finally(() => setLoading(false));
  }, [open]);

  if (!open) return null;

  const handlePick = async (tmpl: AgentTemplate) => {
    if (creating) return;
    setCreating(tmpl.id);
    setError(null);
    try {
      const agent = await agents.createFromTemplate(studyId, tmpl.id);
      onCreated(agent.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create agent from template");
    } finally {
      setCreating(null);
    }
  };

  return (
    <div
      className="fixed inset-0 z-40 bg-black/40 flex items-start justify-center p-4 overflow-y-auto"
      onClick={onClose}
    >
      <div
        className="mt-16 w-full max-w-3xl rounded-3xl bg-white shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between p-6 border-b border-gray-100">
          <div>
            <h2 className="text-lg font-bold text-gray-900">Start from a template</h2>
            <p className="text-xs text-gray-500 mt-1">
              Pre-configured agents you can drop in with your OpenAI key. Land in
              draft so you can review the prompt before going live.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 p-1 rounded-md"
            aria-label="Close template picker"
          >
            <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="p-6 space-y-3">
          {error && (
            <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              {error}
            </div>
          )}

          {loading && (
            <div className="text-sm text-gray-400 flex items-center gap-2">
              <div className="h-4 w-4 rounded-full border-2 border-gray-300 border-t-gray-700 animate-spin" />
              Loading templates…
            </div>
          )}

          {list?.map((tmpl) => (
            <button
              type="button"
              key={tmpl.id}
              disabled={creating !== null}
              onClick={() => handlePick(tmpl)}
              className="w-full text-left rounded-2xl border border-gray-200 bg-white p-4 hover:border-gray-400 hover:bg-gray-50 transition-colors disabled:opacity-60"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <h3 className="text-sm font-semibold text-gray-900">{tmpl.name}</h3>
                    {tmpl.tags.map((t) => (
                      <span
                        key={t}
                        className="text-[10px] uppercase tracking-wider rounded-full bg-gray-100 text-gray-600 px-2 py-0.5 font-semibold"
                      >
                        {t}
                      </span>
                    ))}
                  </div>
                  <p className="text-xs text-gray-500 mt-1.5">{tmpl.description}</p>
                  <div className="flex items-center gap-3 mt-2 text-[11px] text-gray-400">
                    <span>{MODALITY_LABEL[tmpl.modality]}</span>
                    <span className="text-gray-300">·</span>
                    <span>{PIPELINE_LABEL[tmpl.pipeline_type]}</span>
                    <span className="text-gray-300">·</span>
                    <code className="font-mono">{tmpl.llm_model}</code>
                    {tmpl.interview_mode === "structured" && (
                      <>
                        <span className="text-gray-300">·</span>
                        <span>structured guide</span>
                      </>
                    )}
                  </div>
                </div>
                <span className="text-xs text-gray-500 whitespace-nowrap pt-0.5">
                  {creating === tmpl.id ? "Creating…" : "Use →"}
                </span>
              </div>
            </button>
          ))}

          {list && list.length === 0 && !loading && (
            <p className="text-sm text-gray-400">No templates available.</p>
          )}
        </div>
      </div>
    </div>
  );
}
