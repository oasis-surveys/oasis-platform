import { useEffect, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import {
  studies,
  agents,
  type Study,
  type AgentListItem,
  type StudyAnalytics,
} from "../lib/api";
import HelpTooltip from "../components/HelpTooltip";
import CopyButton from "../components/CopyButton";
import { useToast } from "../components/Toast";

const STATUS_COLORS: Record<string, string> = {
  draft: "bg-gray-100 text-gray-600",
  active: "bg-emerald-50 text-emerald-700",
  paused: "bg-amber-50 text-amber-700",
  completed: "bg-blue-50 text-blue-700",
};

export default function StudyDetailPage() {
  const { studyId } = useParams<{ studyId: string }>();
  const navigate = useNavigate();
  const [study, setStudy] = useState<Study | null>(null);
  const [agentList, setAgentList] = useState<AgentListItem[]>([]);
  const [analytics, setAnalytics] = useState<StudyAnalytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [toast, showToast] = useToast();

  useEffect(() => {
    if (!studyId) return;
    Promise.all([
      studies.get(studyId),
      agents.list(studyId),
      studies.analytics(studyId).catch(() => null),
    ])
      .then(([s, a, an]) => {
        setStudy(s);
        setAgentList(a);
        setAnalytics(an);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [studyId]);

  const handleDelete = async () => {
    if (!studyId || !confirm("Delete this study and all its agents?")) return;
    await studies.delete(studyId);
    navigate("/");
  };

  const handleStatusChange = async (newStatus: Study["status"]) => {
    if (!studyId) return;
    const updated = await studies.update(studyId, { status: newStatus });
    setStudy(updated);
  };

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-gray-400">
        <div className="h-4 w-4 rounded-full border-2 border-gray-300 border-t-gray-700 animate-spin" />
        Loading…
      </div>
    );
  }

  if (!study) {
    return <p className="text-sm text-red-500">Study not found.</p>;
  }

  return (
    <div>
      {toast}

      {/* Breadcrumb */}
      <nav className="mb-6 text-sm text-gray-400 flex items-center gap-2">
        <Link to="/" className="hover:text-gray-600 transition-colors">Studies</Link>
        <svg className="h-3.5 w-3.5 text-gray-300" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
        </svg>
        <span className="text-gray-700 font-medium">{study.title}</span>
      </nav>

      {/* Study Header */}
      <div className="mb-6 card p-6">
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 tracking-tight">{study.title}</h1>
            {study.description && (
              <p className="text-sm text-gray-500 mt-2 max-w-lg">{study.description}</p>
            )}
            <p className="text-xs text-gray-400 mt-2">
              Created {new Date(study.created_at).toLocaleDateString()}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <select
              value={study.status}
              onChange={(e) =>
                handleStatusChange(e.target.value as Study["status"])
              }
              className="select-styled !py-1.5 text-xs"
            >
              <option value="draft">Draft</option>
              <option value="active">Active</option>
              <option value="paused">Paused</option>
              <option value="completed">Completed</option>
            </select>
            <button onClick={handleDelete} className="btn-danger !py-1.5 !px-3 !text-xs">
              Delete
            </button>
          </div>
        </div>
      </div>

      {/* ── Study Analytics ───────────────────────────────────── */}
      {analytics && analytics.total_sessions > 0 && (
        <div className="mb-6">
          <h2 className="text-sm font-semibold text-gray-900 mb-3 flex items-center gap-1.5">
            Study Overview
            <HelpTooltip text="Aggregate statistics across all agents in this study. Updated in real-time as new sessions are recorded." />
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <StatCard label="Total Sessions" value={analytics.total_sessions} />
            <StatCard
              label="Completed"
              value={analytics.completed_sessions}
              sub={`${analytics.completion_rate}% rate`}
              color="text-blue-600"
            />
            <StatCard
              label="Avg Duration"
              value={
                analytics.avg_duration_seconds != null
                  ? formatDuration(analytics.avg_duration_seconds)
                  : "—"
              }
            />
            <StatCard
              label="Total Utterances"
              value={analytics.total_utterances}
            />
          </div>
        </div>
      )}

      {/* Agents Section */}
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-sm font-semibold text-gray-900 flex items-center gap-1.5">
          Agents
          <HelpTooltip text="Agents are AI interviewers. Each agent has its own prompt, model configuration, and shareable interview link." />
        </h2>
        <Link
          to={`/studies/${studyId}/agents/new`}
          className="btn-primary !py-2 !px-4 !text-xs"
        >
          <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
          </svg>
          New Agent
        </Link>
      </div>

      {agentList.length === 0 ? (
        <div className="card py-16 text-center">
          <div className="flex flex-col items-center gap-3">
            <div className="h-12 w-12 rounded-2xl bg-gray-100 flex items-center justify-center">
              <svg className="h-6 w-6 text-gray-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z" />
              </svg>
            </div>
            <p className="text-gray-400 text-sm">
              No agents yet. Create one to start conducting interviews.
            </p>
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          {agentList.map((agent) => {
            const agentAnalytics = analytics?.agents.find(
              (a) => a.agent_id === agent.id
            );
            const widgetUrl = `${window.location.origin}/interview/${agent.widget_key}`;
            const embedCode = `<iframe src="${widgetUrl}" width="100%" height="700" style="border:none;border-radius:16px;" allow="microphone" title="${agent.name} Interview"></iframe>`;

            return (
              <div
                key={agent.id}
                className="card overflow-hidden"
              >
                {/* Main card body */}
                <Link
                  to={`/studies/${studyId}/agents/${agent.id}`}
                  className="block p-5 hover:bg-gray-50/50 transition-colors"
                >
                  <div className="flex items-center justify-between">
                    <div>
                      <h3 className="font-semibold text-gray-900">
                        {agent.name}
                      </h3>
                      <div className="flex items-center gap-3 mt-2 text-xs text-gray-400">
                        <span className="inline-flex items-center gap-1">
                          <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M9.75 3.104v5.714a2.25 2.25 0 01-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 014.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15.3M14.25 3.104c.251.023.501.05.75.082M19.8 15.3l-1.57.393A9.065 9.065 0 0112 15a9.065 9.065 0 00-6.23.693L5 14.5m14.8.8l1.402 1.402c1.232 1.232.65 3.318-1.067 3.611A48.309 48.309 0 0112 21c-2.773 0-5.491-.235-8.135-.687-1.718-.293-2.3-2.379-1.067-3.61L5 14.5" />
                          </svg>
                          {agent.llm_model}
                        </span>
                        <span className="text-gray-300">·</span>
                        <span className="capitalize">
                          {agent.pipeline_type.replace("_", " ")}
                        </span>
                        <span className="text-gray-300">·</span>
                        <span>{agent.language.toUpperCase()}</span>
                        {agentAnalytics && agentAnalytics.total_sessions > 0 && (
                          <>
                            <span className="text-gray-300">·</span>
                            <span className="text-gray-500 font-medium">
                              {agentAnalytics.total_sessions} session
                              {agentAnalytics.total_sessions !== 1 ? "s" : ""}
                            </span>
                          </>
                        )}
                      </div>
                    </div>
                    <span
                      className={`rounded-full px-3 py-1 text-xs font-medium capitalize ${
                        STATUS_COLORS[agent.status] || ""
                      }`}
                    >
                      {agent.status}
                    </span>
                  </div>
                </Link>

                {/* Action bar */}
                <div className="border-t border-gray-100 bg-gray-50/50 px-5 py-2.5 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <code className="rounded-lg bg-white border border-gray-200 px-2.5 py-1 text-[11px] text-gray-500 font-mono">
                      {agent.widget_key}
                    </code>
                    <CopyButton
                      text={widgetUrl}
                      onCopied={showToast}
                      toastMessage="Interview link copied!"
                    />
                    <CopyButton
                      text={embedCode}
                      onCopied={showToast}
                      toastMessage="Embed code copied!"
                      label="Embed"
                      className="!w-auto !px-2"
                    />
                  </div>
                  <Link
                    to={`/studies/${studyId}/agents/${agent.id}/sessions`}
                    onClick={(e) => e.stopPropagation()}
                    className="inline-flex items-center gap-1.5 rounded-xl bg-gray-900 px-4 py-1.5 text-xs font-semibold text-white hover:bg-gray-800 transition-all active:scale-[0.98] shadow-sm"
                  >
                    <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 12h16.5m-16.5 3.75h16.5M3.75 19.5h16.5M5.625 4.5h12.75a1.875 1.875 0 010 3.75H5.625a1.875 1.875 0 010-3.75z" />
                    </svg>
                    Sessions
                    {agentAnalytics && agentAnalytics.active_sessions > 0 && (
                      <span className="ml-1 inline-flex items-center justify-center h-4 w-4 rounded-full bg-emerald-500 text-[10px] font-bold text-white">
                        {agentAnalytics.active_sessions}
                      </span>
                    )}
                  </Link>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── Helper Components ────────────────────────────────────────

function StatCard({
  label,
  value,
  sub,
  color,
}: {
  label: string;
  value: string | number;
  sub?: string;
  color?: string;
}) {
  return (
    <div className="card p-4 !hover:shadow-sm">
      <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider">
        {label}
      </p>
      <p className={`text-2xl font-bold mt-1 ${color || "text-gray-900"}`}>
        {value}
      </p>
      {sub && <p className="text-xs text-gray-400 mt-0.5">{sub}</p>}
    </div>
  );
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const mins = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  return `${mins}m ${secs}s`;
}
