/**
 * OASIS — Session transcript viewer with live streaming.
 */

import { useEffect, useRef, useState } from "react";
import { useParams, Link } from "react-router-dom";
import {
  sessions,
  getAuthToken,
  type SessionDetail,
  type SessionAudioManifest,
  type EngagementSummary,
  ADAPTIVE_ACTION_META,
  ADAPTIVE_TRIGGER_LABELS,
} from "../lib/api";
import HelpTooltip from "../components/HelpTooltip";
import { useToast } from "../components/Toast";

const ROLE_STYLES: Record<string, string> = {
  user: "bg-gray-900 text-white rounded-br-md",
  agent: "bg-gray-100 text-gray-800 rounded-bl-md",
  system: "bg-amber-50 text-amber-800 rounded-bl-md italic",
};

const ROLE_LABELS: Record<string, string> = {
  user: "Participant",
  agent: "Agent",
  system: "System",
};

const ENGAGEMENT_EVENT_LABELS: Record<string, string> = {
  sustained_disengagement: "Sustained disengagement",
  positive_engagement_streak: "Positive engagement streak",
  recovery_after_dip: "Recovery after a dip",
};

const WS_MONITOR_URL = `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}/ws/monitor`;

/**
 * Simple markdown-to-HTML renderer for transcript display.
 * Handles **bold**, *italic*, `code`, lists, and line breaks.
 */
function renderMarkdown(text: string): string {
  let html = text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

  html = html.replace(/```([\s\S]*?)```/g, '<pre class="bg-black/5 rounded-lg p-2 my-1 text-xs font-mono overflow-x-auto whitespace-pre-wrap">$1</pre>');
  html = html.replace(/`([^`]+)`/g, '<code class="bg-black/10 rounded px-1 py-0.5 text-xs font-mono">$1</code>');
  html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/(?<!\w)\*(.+?)\*(?!\w)/g, "<em>$1</em>");
  html = html.replace(
    /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener noreferrer" class="underline hover:opacity-80">$1</a>'
  );

  const lines = html.split("\n");
  const result: string[] = [];
  let inUl = false;
  let inOl = false;

  for (const line of lines) {
    const ulMatch = line.match(/^\s*[-•]\s+(.+)/);
    const olMatch = line.match(/^\s*\d+[.)]\s+(.+)/);

    if (ulMatch) {
      if (!inUl) { result.push('<ul class="list-disc list-inside my-1 space-y-0.5">'); inUl = true; }
      if (inOl) { result.push("</ol>"); inOl = false; }
      result.push(`<li>${ulMatch[1]}</li>`);
    } else if (olMatch) {
      if (!inOl) { result.push('<ol class="list-decimal list-inside my-1 space-y-0.5">'); inOl = true; }
      if (inUl) { result.push("</ul>"); inUl = false; }
      result.push(`<li>${olMatch[1]}</li>`);
    } else {
      if (inUl) { result.push("</ul>"); inUl = false; }
      if (inOl) { result.push("</ol>"); inOl = false; }
      result.push(line);
    }
  }
  if (inUl) result.push("</ul>");
  if (inOl) result.push("</ol>");

  html = result.join("\n").replace(/\n/g, "<br>");
  html = html.replace(/<br><(ul|ol)/g, "<$1");
  html = html.replace(/<\/(ul|ol)><br>/g, "</$1>");

  return html;
}

interface LiveEntry {
  role: "user" | "agent" | "system";
  content: string;
  sequence: number;
  spoken_at?: string;
}

export default function SessionDetailPage() {
  const { studyId, agentId, sessionId } = useParams<{
    studyId: string;
    agentId: string;
    sessionId: string;
  }>();
  const [session, setSession] = useState<SessionDetail | null>(null);
  const [liveEntries, setLiveEntries] = useState<LiveEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [toast, showToast] = useToast();
  const [isLive, setIsLive] = useState(false);
  const [liveStatus, setLiveStatus] = useState<string>("connecting");
  const [terminating, setTerminating] = useState(false);
  const [audioManifest, setAudioManifest] = useState<SessionAudioManifest | null>(null);
  const [engagement, setEngagement] = useState<EngagementSummary | null>(null);
  const ws = useRef<WebSocket | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [liveEntries, session?.entries]);

  useEffect(() => {
    if (!studyId || !agentId || !sessionId) return;
    setLoadError(null);
    sessions
      .get(studyId, agentId, sessionId)
      .then((s) => {
        setSession(s);
        if (s.status === "active") setIsLive(true);
      })
      .catch((err) => {
        setLoadError(
          err instanceof Error ? err.message : "Could not load session. Check your connection and try again."
        );
      })
      .finally(() => setLoading(false));
  }, [studyId, agentId, sessionId]);

  useEffect(() => {
    if (!studyId || !agentId || !sessionId || !session?.audio_recording_enabled) {
      setAudioManifest(null);
      return;
    }
    if (session.status === "active") return;
    sessions
      .getAudioManifest(studyId, agentId, sessionId)
      .then(setAudioManifest)
      .catch(() => setAudioManifest(null));
  }, [studyId, agentId, sessionId, session?.audio_recording_enabled, session?.status]);

  useEffect(() => {
    if (!studyId || !agentId || !sessionId || !session) {
      setEngagement(null);
      return;
    }
    sessions
      .getEngagement(studyId, agentId, sessionId)
      .then((e) => setEngagement(e.turn_count > 0 ? e : null))
      .catch(() => setEngagement(null));
  }, [studyId, agentId, sessionId, session?.status]);

  useEffect(() => {
    if (!isLive || !sessionId) return;

    // Attach JWT as a query param when present — the monitor endpoint reads
    // ?token=… and rejects with close code 4401 when AUTH_ENABLED=true.
    const token = getAuthToken();
    const url = token
      ? `${WS_MONITOR_URL}/${sessionId}?token=${encodeURIComponent(token)}`
      : `${WS_MONITOR_URL}/${sessionId}`;
    const socket = new WebSocket(url);
    ws.current = socket;

    socket.onopen = () => setLiveStatus("connected");

    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        if (data.type === "transcript") {
          setLiveEntries((prev) => {
            if (prev.some((e) => e.sequence === data.sequence)) return prev;
            return [
              ...prev,
              {
                role: data.role,
                content: data.content,
                sequence: data.sequence,
                spoken_at: data.spoken_at,
              },
            ];
          });
        } else if (data.type === "session_ended") {
          setIsLive(false);
          setLiveStatus("ended");
          if (studyId && agentId && sessionId) {
            sessions.get(studyId, agentId, sessionId).then(setSession);
          }
        }
      } catch (e) {
        console.error("Failed to parse monitor message:", e);
      }
    };

    socket.onclose = () => {
      setLiveStatus((s) => (s === "ended" ? s : "disconnected"));
      setIsLive(false);
    };
    socket.onerror = () => {
      setLiveStatus("error");
      setIsLive(false);
    };

    return () => {
      socket.close();
      ws.current = null;
    };
  }, [isLive, sessionId, studyId, agentId]);

  const handleTerminate = async () => {
    if (!studyId || !agentId || !sessionId) return;
    if (
      !confirm(
        "Mark this session as ended in the dashboard? The participant may stay connected until they leave or close the page."
      )
    ) {
      return;
    }
    setTerminating(true);
    try {
      await sessions.terminate(studyId, agentId, sessionId);
      setTimeout(() => {
        sessions.get(studyId, agentId, sessionId).then((s) => {
          setSession(s);
          if (s.status !== "active") setIsLive(false);
        });
      }, 1500);
    } catch (err) {
      showToast(
        err instanceof Error ? err.message : "Failed to terminate session",
        "warning"
      );
    } finally {
      setTerminating(false);
    }
  };

  const showLiveBadge =
    isLive && (liveStatus === "connected" || liveStatus === "connecting");

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-gray-400">
        <div className="h-4 w-4 rounded-full border-2 border-gray-300 border-t-gray-700 animate-spin" />
        Loading…
      </div>
    );
  }

  if (loadError || !session) {
    return <p className="text-sm text-red-500">{loadError || "Session not found."}</p>;
  }

  const existingSequences = new Set(session.entries.map((e) => e.sequence));
  const newLiveEntries = liveEntries.filter((e) => !existingSequences.has(e.sequence));

  const allEntries = [
    ...session.entries.map((e) => ({
      role: e.role,
      content: e.content,
      sequence: e.sequence,
      spoken_at: e.spoken_at,
    })),
    ...newLiveEntries,
  ].sort((a, b) => a.sequence - b.sequence);

  const handleDownload = async (format: "csv" | "json") => {
    try {
      if (format === "csv") {
        await sessions.downloadCsv(studyId!, agentId!, { session_ids: sessionId! });
      } else {
        await sessions.downloadJson(studyId!, agentId!, { session_ids: sessionId! });
      }
      showToast(`Exported ${format.toUpperCase()} successfully`, "success");
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Export failed", "warning");
    }
  };

  return (
    <div>
      {toast}
      {/* Breadcrumb */}
      <nav className="mb-6 text-sm text-gray-400 flex items-center gap-2">
        <Link to="/" className="hover:text-gray-600 transition-colors">Studies</Link>
        <ChevronRight />
        <Link to={`/studies/${studyId}`} className="hover:text-gray-600 transition-colors">Study</Link>
        <ChevronRight />
        <Link
          to={`/studies/${studyId}/agents/${agentId}/sessions`}
          className="hover:text-gray-600 transition-colors"
        >
          Sessions
        </Link>
        <ChevronRight />
        <span className="text-gray-700 font-medium">Transcript</span>
      </nav>

      {/* Session metadata */}
      <div className="mb-6 card p-6">
        <div className="flex items-start justify-between mb-5">
          <div>
            <h1 className="text-xl font-bold text-gray-900 tracking-tight flex items-center gap-2">
              Session Transcript
              <HelpTooltip text="This is a diarised transcript — participant and agent utterances are separated and timestamped automatically." />
            </h1>
            <p className="text-xs font-mono text-gray-400 mt-1">{session.id}</p>
          </div>
          <div className="flex items-center gap-2">
            {showLiveBadge && (
              <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700">
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                </span>
                LIVE
              </span>
            )}
            {session.status === "active" && (
              <button
                onClick={handleTerminate}
                disabled={terminating}
                className="btn-danger !py-1.5 !px-3 !text-xs"
              >
                <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
                {terminating ? "Terminating…" : "Terminate"}
              </button>
            )}
            <button
              type="button"
              onClick={() => handleDownload("csv")}
              className="btn-secondary !py-1.5 !px-3 !text-xs"
            >
              <DownloadIcon /> CSV
            </button>
            <button
              type="button"
              onClick={() => handleDownload("json")}
              className="btn-secondary !py-1.5 !px-3 !text-xs"
            >
              <DownloadIcon /> JSON
            </button>
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-5 gap-4 text-sm">
          <div>
            <span className="text-gray-400 block text-[10px] font-semibold uppercase tracking-wider">Status</span>
            <span className="capitalize font-medium text-gray-900">
              {isLive ? "active" : session.status.replace("_", " ")}
            </span>
          </div>
          <div>
            <span className="text-gray-400 block text-[10px] font-semibold uppercase tracking-wider">Participant</span>
            <span className="font-mono font-medium text-gray-900 text-xs break-all">
              {session.participant_id || "—"}
            </span>
          </div>
          <div>
            <span className="text-gray-400 block text-[10px] font-semibold uppercase tracking-wider">Duration</span>
            <span className="font-medium text-gray-900">
              {session.duration_seconds != null
                ? formatDuration(session.duration_seconds)
                : isLive
                ? "In progress…"
                : "—"}
            </span>
          </div>
          <div>
            <span className="text-gray-400 block text-[10px] font-semibold uppercase tracking-wider">Started</span>
            <span className="font-medium text-gray-900">{new Date(session.created_at).toLocaleString()}</span>
          </div>
          <div>
            <span className="text-gray-400 block text-[10px] font-semibold uppercase tracking-wider">Utterances</span>
            <span className="font-medium text-gray-900">{allEntries.length}</span>
          </div>
        </div>

        {session.audio_recording_enabled && (
          <div className="mt-5 pt-5 border-t border-gray-100">
            <h2 className="text-sm font-semibold text-gray-900 mb-2 flex items-center gap-2">
              Interview audio
              <HelpTooltip text="Full-session WAV files: session_user.wav (participant) and session_agent.wav (agent). Written when the interview ends." />
            </h2>
            {session.status === "active" ? (
              <p className="text-xs text-gray-500">Audio files are written when the session ends.</p>
            ) : session.audio_recording_status === "none" ? (
              <p className="text-xs text-gray-500">No recording status yet.</p>
            ) : audioManifest && audioManifest.turns.length > 0 ? (
              <ul className="space-y-2">
                {audioManifest.turns.map((turn) => (
                  <li
                    key={`${turn.sequence}-${turn.role}`}
                    className="flex items-center justify-between gap-3 text-sm"
                  >
                    <span className="text-gray-700">
                      {turn.role === "user" ? "Participant" : "Agent"}
                      {turn.duration_ms != null && (
                        <span className="text-gray-400 ml-2">
                          {(turn.duration_ms / 1000).toFixed(1)}s
                        </span>
                      )}
                    </span>
                    <button
                      type="button"
                      className="btn-secondary !py-1 !px-2 !text-xs"
                      onClick={() =>
                        studyId &&
                        agentId &&
                        sessionId &&
                        sessions
                          .downloadAudioTurn(studyId, agentId, sessionId, turn.filename)
                          .then(() => showToast(`Downloaded ${turn.filename}`, "success"))
                          .catch((err) =>
                            showToast(
                              err instanceof Error ? err.message : "Download failed",
                              "warning"
                            )
                          )
                      }
                    >
                      <DownloadIcon /> {turn.filename}
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-xs text-amber-700">
                Recording status: {session.audio_recording_status}. No turn files found.
              </p>
            )}
          </div>
        )}
      </div>

      {/* ── Engagement metrics ── */}
      {engagement && (
        <div className="card overflow-hidden">
          <div className="px-5 py-3.5 border-b border-gray-100 flex items-center justify-between bg-gray-50/50">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-gray-400 flex items-center gap-2">
              Engagement metrics
              <HelpTooltip text="Observational signals computed per participant turn (response latency, answer length, speech rate, filler words) and a 0–1 rule-based score. This does not change the interview and is included in CSV/JSON exports." />
            </span>
            {engagement.label && <EngagementBadge label={engagement.label} />}
          </div>

          <div className="px-5 py-5">
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4 text-sm">
              <div>
                <span className="text-gray-400 block text-[10px] font-semibold uppercase tracking-wider">Avg score</span>
                <span className="font-medium text-gray-900">
                  {engagement.average_score != null ? engagement.average_score.toFixed(2) : "—"}
                </span>
              </div>
              <div>
                <span className="text-gray-400 block text-[10px] font-semibold uppercase tracking-wider">Turns scored</span>
                <span className="font-medium text-gray-900">{engagement.turn_count}</span>
              </div>
              <div>
                <span className="text-gray-400 block text-[10px] font-semibold uppercase tracking-wider">Avg latency</span>
                <span className="font-medium text-gray-900">
                  {engagement.average_latency_ms != null
                    ? `${(engagement.average_latency_ms / 1000).toFixed(1)}s`
                    : "—"}
                </span>
              </div>
              <div>
                <span className="text-gray-400 block text-[10px] font-semibold uppercase tracking-wider">Avg words</span>
                <span className="font-medium text-gray-900">
                  {engagement.average_words != null ? engagement.average_words.toFixed(1) : "—"}
                </span>
              </div>
              <div>
                <span className="text-gray-400 block text-[10px] font-semibold uppercase tracking-wider">Low turns</span>
                <span className="font-medium text-gray-900">{engagement.low_engagement_turns}</span>
              </div>
            </div>

            {engagement.events.length > 0 && (
              <div className="mt-4 border-t border-gray-50 pt-3">
                <span className="text-[10px] font-semibold uppercase tracking-wider text-gray-400">
                  Events
                </span>
                <ul className="mt-2 space-y-1.5">
                  {engagement.events.map((ev, i) => (
                    <li
                      key={`${ev.event_type}-${ev.transcript_sequence}-${i}`}
                      className="flex items-center gap-2 text-xs text-gray-700"
                    >
                      <span
                        className={`inline-block h-1.5 w-1.5 rounded-full ${
                          ev.event_type === "positive_engagement_streak"
                            ? "bg-emerald-500"
                            : ev.event_type === "recovery_after_dip"
                            ? "bg-sky-500"
                            : "bg-rose-500"
                        }`}
                      />
                      <span>{ENGAGEMENT_EVENT_LABELS[ev.event_type] || ev.event_type}</span>
                      {ev.transcript_sequence != null && (
                        <span className="text-gray-400">· turn #{ev.transcript_sequence}</span>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {engagement.adaptive_actions.length > 0 && (
              <div className="mt-4 border-t border-gray-50 pt-3">
                <div className="flex items-center gap-2">
                  <span className="text-[10px] font-semibold uppercase tracking-wider text-gray-400">
                    Adaptive actions
                  </span>
                  <span
                    className={`text-[10px] font-semibold uppercase tracking-wide rounded-full px-2 py-0.5 ${
                      engagement.adaptive_active
                        ? "bg-emerald-50 text-emerald-700"
                        : "bg-gray-100 text-gray-500"
                    }`}
                  >
                    {engagement.adaptive_active ? "Live" : "Shadow"}
                  </span>
                </div>
                <ul className="mt-2 space-y-1.5">
                  {engagement.adaptive_actions.map((a, i) => {
                    const applied = (a.detail || {})["applied"] === true;
                    return (
                      <li
                        key={`${a.action}-${a.transcript_sequence}-${i}`}
                        className="flex flex-wrap items-center gap-2 text-xs text-gray-700"
                      >
                        <span
                          className={`inline-block h-1.5 w-1.5 rounded-full ${
                            applied ? "bg-emerald-500" : "bg-gray-300"
                          }`}
                        />
                        <span className="font-medium">
                          {ADAPTIVE_ACTION_META[
                            a.action as keyof typeof ADAPTIVE_ACTION_META
                          ]?.label || a.action}
                        </span>
                        <span className="text-gray-400">
                          ·{" "}
                          {ADAPTIVE_TRIGGER_LABELS[
                            a.trigger as keyof typeof ADAPTIVE_TRIGGER_LABELS
                          ] || a.trigger}
                        </span>
                        {a.transcript_sequence != null && (
                          <span className="text-gray-400">
                            · turn #{a.transcript_sequence}
                          </span>
                        )}
                        <span
                          className={`text-[10px] uppercase tracking-wide ${
                            applied ? "text-emerald-600" : "text-gray-400"
                          }`}
                        >
                          {a.mode === "live" && applied
                            ? "applied"
                            : "logged"}
                        </span>
                      </li>
                    );
                  })}
                </ul>
              </div>
            )}

            <details className="mt-4 group">
              <summary className="cursor-pointer text-xs font-medium text-gray-500 hover:text-gray-800 select-none">
                Per-turn breakdown
              </summary>
              <div className="mt-3 overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-left text-gray-400 border-b border-gray-100">
                      <th className="py-1.5 pr-3 font-semibold">Turn</th>
                      <th className="py-1.5 pr-3 font-semibold">Score</th>
                      <th className="py-1.5 pr-3 font-semibold">Latency</th>
                      <th className="py-1.5 pr-3 font-semibold">Words</th>
                      <th className="py-1.5 pr-3 font-semibold">Rate (wpm)</th>
                      <th className="py-1.5 pr-3 font-semibold">Fillers</th>
                      <th className="py-1.5 pr-3 font-semibold">Flags</th>
                    </tr>
                  </thead>
                  <tbody>
                    {engagement.turns.map((t) => (
                      <tr key={t.transcript_sequence} className="border-b border-gray-50">
                        <td className="py-1.5 pr-3 text-gray-500">#{t.transcript_sequence}</td>
                        <td className="py-1.5 pr-3">
                          <span className="inline-flex items-center gap-2">
                            {t.label && <EngagementBadge label={t.label} small />}
                            <span className="text-gray-700">
                              {t.score != null ? t.score.toFixed(2) : "—"}
                            </span>
                          </span>
                        </td>
                        <td className="py-1.5 pr-3 text-gray-700">
                          {t.response_latency_ms != null
                            ? `${(t.response_latency_ms / 1000).toFixed(1)}s`
                            : "—"}
                        </td>
                        <td className="py-1.5 pr-3 text-gray-700">{t.word_count ?? "—"}</td>
                        <td className="py-1.5 pr-3 text-gray-700">
                          {t.speech_rate_wpm != null ? Math.round(t.speech_rate_wpm) : "—"}
                        </td>
                        <td className="py-1.5 pr-3 text-gray-700">{t.filler_count ?? "—"}</td>
                        <td className="py-1.5 pr-3 text-gray-400">
                          {t.flags.length > 0 ? t.flags.join(", ") : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          </div>
        </div>
      )}

      {/* ── Transcript ── */}
      <div className="card overflow-hidden">
        <div className="px-5 py-3.5 border-b border-gray-100 flex items-center justify-between bg-gray-50/50">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-gray-400">
            Diarized Transcript
          </span>
          {isLive && (
            <span className="text-xs text-gray-400 flex items-center gap-1.5">
              {liveStatus === "connected" && (
                <>
                  <span className="relative flex h-1.5 w-1.5">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-emerald-500"></span>
                  </span>
                  Streaming live…
                </>
              )}
              {liveStatus === "connecting" && "Connecting…"}
              {liveStatus === "ended" && "Session ended"}
              {liveStatus === "disconnected" && "Disconnected — refresh the page to reconnect"}
              {liveStatus === "error" && "Monitor connection error — refresh to retry"}
            </span>
          )}
        </div>

        <div className="px-5 py-5 space-y-3 max-h-[60vh] overflow-y-auto">
          {allEntries.length === 0 && (
            <p className="text-gray-300 text-sm text-center py-12">
              {isLive ? "Waiting for first utterance…" : "No transcript entries recorded."}
            </p>
          )}
          {allEntries.map((entry, idx) => (
            <div
              key={`${entry.sequence}-${idx}`}
              className={`flex ${entry.role === "user" ? "justify-end" : "justify-start"} animate-fade-in`}
            >
              <div className="flex flex-col gap-0.5 max-w-[80%]">
                <span
                  className={`text-[10px] font-semibold uppercase tracking-wider ${
                    entry.role === "user"
                      ? "text-right text-gray-400"
                      : "text-left text-gray-400"
                  }`}
                >
                  {ROLE_LABELS[entry.role] || entry.role}
                </span>
                <div
                  className={`rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
                    ROLE_STYLES[entry.role] || ""
                  }`}
                >
                  <div dangerouslySetInnerHTML={{ __html: renderMarkdown(entry.content) }} />
                  {entry.spoken_at && (
                    <p
                      className={`text-[10px] mt-1 ${
                        entry.role === "user" ? "text-gray-300" : "text-gray-400"
                      }`}
                    >
                      {new Date(entry.spoken_at).toLocaleTimeString()}
                    </p>
                  )}
                </div>
              </div>
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>
      </div>
    </div>
  );
}

function EngagementBadge({ label, small }: { label: string; small?: boolean }) {
  const styles: Record<string, string> = {
    high: "bg-emerald-100 text-emerald-800",
    medium: "bg-amber-100 text-amber-800",
    low: "bg-rose-100 text-rose-800",
  };
  const cls = styles[label] || "bg-gray-100 text-gray-700";
  return (
    <span
      className={`inline-flex items-center rounded-full font-semibold uppercase tracking-wide ${cls} ${
        small ? "px-1.5 py-0.5 text-[9px]" : "px-2 py-0.5 text-[10px]"
      }`}
    >
      {label}
    </span>
  );
}

function ChevronRight() {
  return (
    <svg className="h-3.5 w-3.5 text-gray-300" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
    </svg>
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
