import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { studies, type StudyListItem } from "../lib/api";
import HelpTooltip from "../components/HelpTooltip";

const STATUS_COLORS: Record<string, string> = {
  draft: "bg-gray-100 text-gray-600",
  active: "bg-oasis-50 text-oasis-600",
  paused: "bg-sand-300/50 text-sand-700",
  completed: "bg-blue-50 text-blue-700",
};

const STATUS_ICONS: Record<string, string> = {
  draft: "○",
  active: "●",
  paused: "◐",
  completed: "✓",
};

export default function StudyListPage() {
  const [list, setList] = useState<StudyListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    studies.list().then(setList).catch(console.error).finally(() => setLoading(false));
  };

  useEffect(load, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await studies.create({ title, description: description || undefined });
      setTitle("");
      setDescription("");
      setShowCreate(false);
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create study");
    }
  };

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 tracking-tight">Studies</h1>
          <p className="text-sm text-gray-500 mt-1 flex items-center gap-1.5">
            Manage your research studies and their conversational agents.
            <HelpTooltip text="A study is a research project. Each study can have multiple agents (AI interviewers) with different configurations. Studies help you organise and track your interview data." />
          </p>
        </div>
        <button
          data-tour="new-study"
          onClick={() => setShowCreate(!showCreate)}
          className="btn-primary"
        >
          {showCreate ? (
            <>
              <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
              Cancel
            </>
          ) : (
            <>
              <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
              </svg>
              New Study
            </>
          )}
        </button>
      </div>

      {/* Create Form */}
      {showCreate && (
        <form
          onSubmit={handleCreate}
          className="mb-8 card p-6 animate-slide-up"
        >
          <h2 className="text-lg font-semibold text-gray-900 mb-5">
            Create New Study
          </h2>
          {error && (
            <p className="mb-4 text-sm text-red-600 bg-red-50 rounded-xl px-4 py-2.5">
              {error}
            </p>
          )}
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1.5">
                Title
              </label>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                required
                className="input-styled"
                placeholder="e.g. User Experience Study 2026"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1.5">
                Description
              </label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={3}
                className="input-styled"
                placeholder="Brief description of the study objectives..."
              />
            </div>
            <button type="submit" className="btn-primary">
              <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
              </svg>
              Create Study
            </button>
          </div>
        </form>
      )}

      {/* Study List */}
      {loading ? (
        <div className="flex items-center gap-2 text-sm text-gray-400">
          <div className="h-4 w-4 rounded-full border-2 border-gray-300 border-t-gray-700 animate-spin" />
          Loading studies…
        </div>
      ) : list.length === 0 ? (
        <div className="card py-20 text-center">
          <div className="flex flex-col items-center gap-3">
            <div className="h-12 w-12 rounded-2xl bg-gray-100 flex items-center justify-center">
              <svg className="h-6 w-6 text-gray-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
              </svg>
            </div>
            <p className="text-gray-400 text-sm">
              No studies yet. Create one to get started.
            </p>
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          {list.map((study) => (
            <Link
              key={study.id}
              to={`/studies/${study.id}`}
              className="block card p-5 group"
            >
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="font-semibold text-gray-900 group-hover:text-gray-700 transition-colors">
                    {study.title}
                  </h3>
                  <p className="text-xs text-gray-400 mt-1.5">
                    Created {new Date(study.created_at).toLocaleDateString()}
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  <span
                    className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium capitalize ${
                      STATUS_COLORS[study.status] || ""
                    }`}
                  >
                    <span className="text-[10px]">{STATUS_ICONS[study.status] || ""}</span>
                    {study.status}
                  </span>
                  <svg className="h-4 w-4 text-gray-300 group-hover:text-gray-500 transition-colors" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                  </svg>
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
