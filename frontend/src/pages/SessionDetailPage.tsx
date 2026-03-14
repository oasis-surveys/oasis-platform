/**
 * SURVEYOR — Session transcript viewer with live streaming.
 */

import { useEffect, useRef, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { sessions, type SessionDetail } from "../lib/api";
import HelpTooltip from "../components/HelpTooltip";

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

const WS_MONITOR_URL = `ws://${window.location.host}/ws/monitor`;

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
  const [isLive, setIsLive] = useState(false);
  const [liveStatus, setLiveStatus] = useState<string>("connecting");
  const [terminating, setTerminating] = useState(false);
  const ws = useRef<WebSocket | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [liveEntries, session?.entries]);

  useEffect(() => {
    if (!studyId || !agentId || !sessionId) return;
    sessions
      .get(studyId, agentId, sessionId)
      .then((s) => {
        setSession(s);
        if (s.status === "active") setIsLive(true);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [studyId, agentId, sessionId]);

  useEffect(() => {
    if (!isLive || !sessionId) return;

    const socket = new WebSocket(`${WS_MONITOR_URL}/${sessionId}`);
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

    socket.onclose = () => setLiveStatus((s) => s === "ended" ? s : "disconnected");
    socket.onerror = () => setLiveStatus("error");

    return () => {
      socket.close();
      ws.current = null;
    };
  }, [isLive, sessionId, studyId, agentId]);

  const handleTerminate = async () => {
    if (!studyId || !agentId || !sessionId) return;
    if (!confirm("Terminate this session? The participant will be disconnected.")) return;
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
      console.error("Terminate failed:", err);
    } finally {
      setTerminating(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-gray-400">
        <div className="h-4 w-4 rounded-full border-2 border-gray-300 border-t-gray-700 animate-spin" />
        Loading…
      </div>
    );
  }

  if (!session) {
    return <p className="text-sm text-red-500">Session not found.</p>;
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

  const exportCsvUrl = sessions.exportCsvUrl(studyId!, agentId!);
  const exportJsonUrl = sessions.exportJsonUrl(studyId!, agentId!);

  return (
    <div>
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
            {isLive && (
              <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700">
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                </span>
                LIVE
              </span>
            )}
            {isLive && (
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
            <a href={exportCsvUrl} download className="btn-secondary !py-1.5 !px-3 !text-xs">
              <DownloadIcon /> CSV
            </a>
            <a href={exportJsonUrl} download className="btn-secondary !py-1.5 !px-3 !text-xs">
              <DownloadIcon /> JSON
            </a>
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
          <div>
            <span className="text-gray-400 block text-[10px] font-semibold uppercase tracking-wider">Status</span>
            <span className="capitalize font-medium text-gray-900">
              {isLive ? "active" : session.status.replace("_", " ")}
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
      </div>

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
              {liveStatus === "disconnected" && "Disconnected"}
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
                  <p>{entry.content}</p>
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
