/**
 * OASIS — Session list page.
 */

import { useEffect, useState, useCallback } from "react";
import { useParams, Link } from "react-router-dom";
import {
  agents,
  sessions,
  type Agent,
  type SessionItem,
  type SessionStats,
  type SessionListParams,
} from "../lib/api";
import HelpTooltip from "../components/HelpTooltip";
import CopyButton from "../components/CopyButton";
import { useToast } from "../components/Toast";

const STATUS_COLORS: Record<string, string> = {
  active: "bg-emerald-50 text-emerald-700",
  completed: "bg-blue-50 text-blue-700",
  timed_out: "bg-amber-50 text-amber-700",
  error: "bg-red-50 text-red-700",
};

const STATUS_LABELS: Record<string, string> = {
  active: "Live",
  completed: "Completed",
  timed_out: "Timed Out",
  error: "Error",
};

const ALL_STATUSES = ["active", "completed", "timed_out", "error"] as const;

export default function SessionListPage() {
  const { studyId, agentId } = useParams<{
    studyId: string;
    agentId: string;
  }>();
  const [agent, setAgent] = useState<Agent | null>(null);
  const [sessionList, setSessionList] = useState<SessionItem[]>([]);
  const [stats, setStats] = useState<SessionStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [toast, showToast] = useToast();

  // Filters
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [dateFrom, setDateFrom] = useState<string>("");
  const [dateTo, setDateTo] = useState<string>("");
  const [sortBy, setSortBy] = useState<string>("created_at");
  const [sortOrder, setSortOrder] = useState<string>("desc");

  const buildParams = useCallback((): SessionListParams => {
    const params: SessionListParams = {};
    if (statusFilter) params.status = statusFilter;
    if (dateFrom) params.date_from = new Date(dateFrom).toISOString();
    if (dateTo) params.date_to = new Date(dateTo).toISOString();
    if (sortBy) params.sort_by = sortBy;
    if (sortOrder) params.sort_order = sortOrder;
    return params;
  }, [statusFilter, dateFrom, dateTo, sortBy, sortOrder]);

  const fetchSessions = useCallback(async () => {
    if (!studyId || !agentId) return;
    try {
      const list = await sessions.list(studyId, agentId, buildParams());
      setSessionList(list);
    } catch (err) {
      console.error(err);
    }
  }, [studyId, agentId, buildParams]);

  useEffect(() => {
    if (!studyId || !agentId) return;
    setLoading(true);
    Promise.all([
      agents.get(studyId, agentId),
      sessions.stats(studyId, agentId),
      sessions.list(studyId, agentId, buildParams()),
    ])
      .then(([a, st, list]) => {
        setAgent(a);
        setStats(st);
        setSessionList(list);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [studyId, agentId]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!loading) fetchSessions();
  }, [statusFilter, dateFrom, dateTo, sortBy, sortOrder]); // eslint-disable-line react-hooks/exhaustive-deps

  // Auto-refresh every 10s
  useEffect(() => {
    const interval = setInterval(() => {
      fetchSessions();
      if (studyId && agentId) {
        sessions.stats(studyId, agentId).then(setStats).catch(() => {});
      }
    }, 10_000);
    return () => clearInterval(interval);
  }, [fetchSessions, studyId, agentId]);

  // Selection helpers
  const allIds = sessionList.map((s) => s.id);
  const allSelected = allIds.length > 0 && allIds.every((id) => selected.has(id));
  const someSelected = selected.size > 0;

  const toggleAll = () => {
    if (allSelected) {
      setSelected(new Set());
    } else {
      setSelected(new Set(allIds));
    }
  };

  const toggleOne = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-gray-400">
        <div className="h-4 w-4 rounded-full border-2 border-gray-300 border-t-gray-700 animate-spin" />
        Loading…
      </div>
    );
  }

  if (!agent) {
    return <p className="text-sm text-red-500">Agent not found.</p>;
  }

  const widgetUrl = `${window.location.origin}/interview/${agent.widget_key}`;
  const embedCode = `<iframe src="${widgetUrl}" width="100%" height="700" style="border:none;border-radius:16px;" allow="microphone" title="${agent.name} Interview"></iframe>`;
  const filterParams = buildParams();

  const selectedIds = [...selected].join(",");
  const exportAllCsvUrl = sessions.exportCsvUrl(studyId!, agentId!, filterParams);
  const exportAllJsonUrl = sessions.exportJsonUrl(studyId!, agentId!, filterParams);
  const exportSelCsvUrl = sessions.exportCsvUrl(studyId!, agentId!, {
    ...filterParams,
    session_ids: selectedIds,
  });
  const exportSelJsonUrl = sessions.exportJsonUrl(studyId!, agentId!, {
    ...filterParams,
    session_ids: selectedIds,
  });

  return (
    <div>
      {toast}

      {/* Breadcrumb */}
      <nav className="mb-6 text-sm text-gray-400 flex items-center gap-2">
        <Link to="/" className="hover:text-gray-600 transition-colors">Studies</Link>
        <ChevronRight />
        <Link to={`/studies/${studyId}`} className="hover:text-gray-600 transition-colors">Study</Link>
        <ChevronRight />
        <span className="text-gray-700 font-medium">{agent.name} — Sessions</span>
      </nav>

      {/* Agent header */}
      <div className="mb-6 card p-6">
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 tracking-tight mb-3">{agent.name}</h1>
            <div className="flex items-center gap-3">
              {/* Interview link with copy */}
              <div className="flex items-center gap-2 bg-gray-50 rounded-xl px-3 py-2 border border-gray-100">
                <svg className="h-3.5 w-3.5 text-gray-400 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M13.19 8.688a4.5 4.5 0 011.242 7.244l-4.5 4.5a4.5 4.5 0 01-6.364-6.364l1.757-1.757m9.86-1.125a4.5 4.5 0 00-7.244-1.242l-4.5 4.5a4.5 4.5 0 006.364 6.364l1.757-1.757" />
                </svg>
                <code className="text-[11px] font-mono text-gray-600 select-all max-w-[260px] truncate">
                  {widgetUrl}
                </code>
                <CopyButton
                  text={widgetUrl}
                  onCopied={showToast}
                  toastMessage="Interview link copied!"
                />
              </div>

              {/* Embed code copy */}
              <button
                type="button"
                onClick={() => {
                  navigator.clipboard.writeText(embedCode);
                  showToast("Embed code copied!");
                }}
                className="btn-secondary !py-2 !px-3 !text-xs"
              >
                <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M17.25 6.75L22.5 12l-5.25 5.25m-10.5 0L1.5 12l5.25-5.25m7.5-3l-4.5 16.5" />
                </svg>
                Embed
                <HelpTooltip text="Copy an HTML iframe snippet to embed this interview widget in Qualtrics, SurveyMonkey, or any webpage." className="ml-0.5" />
              </button>
            </div>
          </div>
          <Link
            to={`/studies/${studyId}/agents/${agentId}`}
            className="btn-secondary !py-1.5 !px-3 !text-xs"
          >
            Edit Agent
          </Link>
        </div>
      </div>

      {/* ── Stats Cards ── */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
          <StatCard label="Total Sessions" value={stats.total_sessions} />
          <StatCard
            label="Completed"
            value={stats.completed_sessions}
            sub={`${stats.completion_rate}% rate`}
            color="text-blue-600"
          />
          <StatCard
            label="Avg Duration"
            value={
              stats.avg_duration_seconds != null
                ? formatDuration(stats.avg_duration_seconds)
                : "—"
            }
          />
          <StatCard label="Total Utterances" value={stats.total_utterances} />
          {stats.active_sessions > 0 && (
            <StatCard
              label="Active Now"
              value={stats.active_sessions}
              color="text-emerald-600"
              pulse
            />
          )}
          {stats.error_sessions > 0 && (
            <StatCard label="Errors" value={stats.error_sessions} color="text-red-600" />
          )}
          {stats.timed_out_sessions > 0 && (
            <StatCard
              label="Timed Out"
              value={stats.timed_out_sessions}
              color="text-amber-600"
            />
          )}
        </div>
      )}

      {/* ── Filters & Export ── */}
      <div className="mb-4 card p-4">
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="block text-[10px] font-semibold text-gray-400 uppercase tracking-wider mb-1">Status</label>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="select-styled !py-1.5 text-xs"
            >
              <option value="">All statuses</option>
              {ALL_STATUSES.map((s) => (
                <option key={s} value={s}>{STATUS_LABELS[s]}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-[10px] font-semibold text-gray-400 uppercase tracking-wider mb-1">From</label>
            <input
              type="date"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              className="input-styled !py-1.5 text-xs"
            />
          </div>

          <div>
            <label className="block text-[10px] font-semibold text-gray-400 uppercase tracking-wider mb-1">To</label>
            <input
              type="date"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              className="input-styled !py-1.5 text-xs"
            />
          </div>

          <div>
            <label className="block text-[10px] font-semibold text-gray-400 uppercase tracking-wider mb-1">Sort by</label>
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value)}
              className="select-styled !py-1.5 text-xs"
            >
              <option value="created_at">Date</option>
              <option value="duration_seconds">Duration</option>
              <option value="status">Status</option>
            </select>
          </div>

          <div>
            <label className="block text-[10px] font-semibold text-gray-400 uppercase tracking-wider mb-1">Order</label>
            <select
              value={sortOrder}
              onChange={(e) => setSortOrder(e.target.value)}
              className="select-styled !py-1.5 text-xs"
            >
              <option value="desc">Newest first</option>
              <option value="asc">Oldest first</option>
            </select>
          </div>

          {(statusFilter || dateFrom || dateTo) && (
            <button
              onClick={() => { setStatusFilter(""); setDateFrom(""); setDateTo(""); }}
              className="text-xs text-gray-400 hover:text-gray-600 transition-colors self-end pb-2"
            >
              Clear filters
            </button>
          )}

          <div className="flex-1" />

          {/* Export dropdown */}
          <div className="flex items-center gap-2">
            {someSelected && (
              <span className="text-xs text-gray-500">
                {selected.size} selected
              </span>
            )}
            <ExportMenu
              allCsvUrl={exportAllCsvUrl}
              allJsonUrl={exportAllJsonUrl}
              selCsvUrl={exportSelCsvUrl}
              selJsonUrl={exportSelJsonUrl}
              hasSelection={someSelected}
              totalCount={sessionList.length}
            />
          </div>
        </div>
      </div>

      {/* ── Session Table ── */}
      {sessionList.length === 0 ? (
        <div className="card py-16 text-center">
          <div className="flex flex-col items-center gap-3">
            <div className="h-12 w-12 rounded-2xl bg-gray-100 flex items-center justify-center">
              <svg className="h-6 w-6 text-gray-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M20.25 8.511c.884.284 1.5 1.128 1.5 2.097v4.286c0 1.136-.847 2.1-1.98 2.193-.34.027-.68.052-1.02.072v3.091l-3-3c-1.354 0-2.694-.055-4.02-.163a2.115 2.115 0 01-.825-.242m9.345-8.334a2.126 2.126 0 00-.476-.095 48.64 48.64 0 00-8.048 0c-1.131.094-1.976 1.057-1.976 2.192v4.286c0 .837.46 1.58 1.155 1.951m9.345-8.334V6.637c0-1.621-1.152-3.026-2.76-3.235A48.455 48.455 0 0011.25 3c-2.115 0-4.198.137-6.24.402-1.608.209-2.76 1.614-2.76 3.235v6.226c0 1.621 1.152 3.026 2.76 3.235.577.075 1.157.14 1.74.194V21l4.155-4.155" />
              </svg>
            </div>
            <p className="text-gray-400 text-sm">
              {statusFilter || dateFrom || dateTo
                ? "No sessions match the current filters."
                : "No sessions yet. Share the interview link with participants."}
            </p>
          </div>
        </div>
      ) : (
        <div className="card overflow-hidden">
          {/* Table header */}
          <div className="border-b border-gray-100 px-4 py-3 flex items-center gap-4 bg-gray-50/80">
            <input
              type="checkbox"
              checked={allSelected}
              onChange={toggleAll}
              className="h-4 w-4 rounded border-gray-300 text-gray-900 focus:ring-0 cursor-pointer"
            />
            <span className="text-[10px] font-semibold uppercase tracking-wider text-gray-400 flex-1">
              Session
            </span>
            <span className="text-[10px] font-semibold uppercase tracking-wider text-gray-400 w-32 text-right">
              Duration
            </span>
            <span className="text-[10px] font-semibold uppercase tracking-wider text-gray-400 w-28 text-right">
              Status
            </span>
          </div>

          {/* Table rows */}
          <div className="divide-y divide-gray-100">
            {sessionList.map((s) => (
              <div
                key={s.id}
                className={`flex items-center gap-4 px-4 py-3.5 transition-colors ${
                  selected.has(s.id) ? "bg-gray-50" : "hover:bg-gray-50/50"
                }`}
              >
                <input
                  type="checkbox"
                  checked={selected.has(s.id)}
                  onChange={() => toggleOne(s.id)}
                  onClick={(e) => e.stopPropagation()}
                  className="h-4 w-4 rounded border-gray-300 text-gray-900 focus:ring-0 cursor-pointer flex-shrink-0"
                />

                <Link
                  to={`/studies/${studyId}/agents/${agentId}/sessions/${s.id}`}
                  className="flex-1 flex items-center gap-3 min-w-0"
                >
                  {s.status === "active" && (
                    <span className="relative flex h-2.5 w-2.5 flex-shrink-0">
                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                      <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500"></span>
                    </span>
                  )}
                  <div className="min-w-0">
                    <p className="font-medium text-gray-900 text-sm font-mono truncate">
                      {s.id.slice(0, 12)}…
                    </p>
                    <p className="text-xs text-gray-400 mt-0.5">
                      {new Date(s.created_at).toLocaleString()}
                      {s.participant_id && (
                        <span className="ml-2 text-gray-300">· {s.participant_id}</span>
                      )}
                    </p>
                  </div>
                </Link>

                <Link
                  to={`/studies/${studyId}/agents/${agentId}/sessions/${s.id}`}
                  className="w-32 text-right text-sm text-gray-500"
                >
                  {s.duration_seconds != null
                    ? formatDuration(s.duration_seconds)
                    : s.status === "active"
                    ? "In progress…"
                    : "—"}
                </Link>

                <Link
                  to={`/studies/${studyId}/agents/${agentId}/sessions/${s.id}`}
                  className="w-28 flex justify-end"
                >
                  <span
                    className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${
                      STATUS_COLORS[s.status] || "bg-gray-100 text-gray-600"
                    }`}
                  >
                    {s.status === "active" && (
                      <span className="relative flex h-1.5 w-1.5">
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                        <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-emerald-500"></span>
                      </span>
                    )}
                    {STATUS_LABELS[s.status] || s.status}
                  </span>
                </Link>
              </div>
            ))}
          </div>

          {/* Table footer */}
          <div className="border-t border-gray-100 px-4 py-2.5 bg-gray-50/80 flex items-center justify-between">
            <span className="text-xs text-gray-400">
              {sessionList.length} session{sessionList.length !== 1 ? "s" : ""}
              {someSelected && ` · ${selected.size} selected`}
            </span>
            {someSelected && (
              <button
                onClick={() => setSelected(new Set())}
                className="text-xs text-gray-400 hover:text-gray-600 transition-colors"
              >
                Clear selection
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Export Menu ───────────────────────────────────────────────

function ExportMenu({
  allCsvUrl,
  allJsonUrl,
  selCsvUrl,
  selJsonUrl,
  hasSelection,
  totalCount,
}: {
  allCsvUrl: string;
  allJsonUrl: string;
  selCsvUrl: string;
  selJsonUrl: string;
  hasSelection: boolean;
  totalCount: number;
}) {
  const [open, setOpen] = useState(false);

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        className="btn-secondary !py-1.5 !px-3 !text-xs"
      >
        <DownloadIcon />
        Export
        <svg className="h-3 w-3 text-gray-400" viewBox="0 0 20 20" fill="currentColor">
          <path fillRule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clipRule="evenodd" />
        </svg>
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div className="absolute right-0 top-full mt-1.5 z-20 w-56 rounded-2xl border border-gray-200 bg-white shadow-xl py-1.5 text-sm animate-scale-in">
            <div className="px-3.5 py-1.5 text-[10px] font-semibold text-gray-400 uppercase tracking-wider">
              Download All ({totalCount})
            </div>
            <a
              href={allCsvUrl}
              download
              onClick={() => setOpen(false)}
              className="flex items-center gap-2 px-3.5 py-2 hover:bg-gray-50 text-gray-700 transition-colors"
            >
              <DownloadIcon /> All sessions — CSV
            </a>
            <a
              href={allJsonUrl}
              download
              onClick={() => setOpen(false)}
              className="flex items-center gap-2 px-3.5 py-2 hover:bg-gray-50 text-gray-700 transition-colors"
            >
              <DownloadIcon /> All sessions — JSON
            </a>

            {hasSelection && (
              <>
                <div className="my-1 border-t border-gray-100" />
                <div className="px-3.5 py-1.5 text-[10px] font-semibold text-gray-400 uppercase tracking-wider">
                  Download Selected
                </div>
                <a
                  href={selCsvUrl}
                  download
                  onClick={() => setOpen(false)}
                  className="flex items-center gap-2 px-3.5 py-2 hover:bg-gray-50 text-gray-700 transition-colors"
                >
                  <DownloadIcon /> Selected — CSV
                </a>
                <a
                  href={selJsonUrl}
                  download
                  onClick={() => setOpen(false)}
                  className="flex items-center gap-2 px-3.5 py-2 hover:bg-gray-50 text-gray-700 transition-colors"
                >
                  <DownloadIcon /> Selected — JSON
                </a>
              </>
            )}
          </div>
        </>
      )}
    </div>
  );
}

// ── Helper Components ─────────────────────────────────────────

function ChevronRight() {
  return (
    <svg className="h-3.5 w-3.5 text-gray-300" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
    </svg>
  );
}

function StatCard({
  label,
  value,
  sub,
  color,
  pulse,
}: {
  label: string;
  value: string | number;
  sub?: string;
  color?: string;
  pulse?: boolean;
}) {
  return (
    <div className="card p-4 !hover:shadow-sm">
      <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider">{label}</p>
      <p
        className={`text-2xl font-bold mt-1 ${color || "text-gray-900"} ${
          pulse ? "animate-pulse" : ""
        }`}
      >
        {value}
      </p>
      {sub && <p className="text-xs text-gray-400 mt-0.5">{sub}</p>}
    </div>
  );
}

function DownloadIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      className="h-3.5 w-3.5"
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={2}
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
      />
    </svg>
  );
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const mins = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  return `${mins}m ${secs}s`;
}
