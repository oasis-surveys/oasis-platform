/**
 * OASIS — Participant interview widget.
 *
 * Accessible at /interview/:widgetKey — this is the page a study participant
 * sees when they join a voice or text interview via the shareable link.
 *
 * Features:
 *  - Fetches widget config (title, description, colour, participant ID mode, modality)
 *  - Handles participant identification: random / predefined (via ?pid=) / user input
 *  - Voice mode: animated orb visualisation with voice wave + listening state
 *  - Text mode: modern chat interface with avatars and typing indicators
 *  - Call timer
 *  - Backend logs diarised transcripts for researcher review
 */

import { useEffect, useRef, useState, useCallback } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { widget, type WidgetConfig } from "../lib/api";
import { MicCapture, AudioPlayer } from "../lib/audio";
import { encodeAudioFrame, decodeFrame } from "../lib/pipecat-proto";

type Status = "loading" | "idle" | "input" | "connecting" | "active" | "ended" | "error";

interface ChatMessage {
  id: string;
  role: "agent" | "user";
  text: string;
  timestamp: Date;
}

const AVATAR_EMOJI: Record<string, string> = {
  robot: "🤖",
  neutral: "🧑‍💼",
  female: "👩‍💼",
  male: "👨‍💼",
  none: "",
};

/** Convert hex colour (#RRGGBB) to rgba with given alpha */
function hexToRgba(hex: string, alpha: number): string {
  const h = hex.replace("#", "");
  const r = parseInt(h.substring(0, 2), 16);
  const g = parseInt(h.substring(2, 4), 16);
  const b = parseInt(h.substring(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

/** Extract RGB components as comma-separated string */
function hexToRgb(hex: string): string {
  const h = hex.replace("#", "");
  return `${parseInt(h.substring(0, 2), 16)}, ${parseInt(h.substring(2, 4), 16)}, ${parseInt(h.substring(4, 6), 16)}`;
}

/**
 * Lightweight markdown-to-HTML renderer for chat messages.
 * Handles: **bold**, *italic*, `inline code`, [links](url), line breaks,
 * unordered lists (- item), ordered lists (1. item).
 * Sanitises HTML entities to prevent XSS.
 */
function renderMarkdown(text: string): string {
  // Escape HTML entities first
  let html = text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

  // Code blocks (``` ... ```)
  html = html.replace(/```([\s\S]*?)```/g, '<pre class="bg-black/5 rounded-lg p-2 my-1 text-xs font-mono overflow-x-auto whitespace-pre-wrap">$1</pre>');

  // Inline code
  html = html.replace(/`([^`]+)`/g, '<code class="bg-black/10 rounded px-1 py-0.5 text-xs font-mono">$1</code>');

  // Bold
  html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");

  // Italic (single asterisk, not inside a word)
  html = html.replace(/(?<!\w)\*(.+?)\*(?!\w)/g, "<em>$1</em>");

  // Links [text](url)
  html = html.replace(
    /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener noreferrer" class="underline hover:opacity-80">$1</a>'
  );

  // Process lines for lists
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

  // Join lines, convert remaining newlines to <br>
  html = result.join("\n").replace(/\n/g, "<br>");
  // Clean up double <br> from list boundaries
  html = html.replace(/<br><(ul|ol)/g, "<$1");
  html = html.replace(/<\/(ul|ol)><br>/g, "</$1>");

  return html;
}

/** Chat bubble content component that renders markdown safely */
function ChatBubbleContent({ text, isUser }: { text: string; isUser: boolean }) {
  const html = renderMarkdown(text);
  return (
    <div
      className={isUser ? "chat-content-user" : "chat-content-agent"}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}

export default function InterviewPage() {
  const { widgetKey } = useParams<{ widgetKey: string }>();
  const [searchParams] = useSearchParams();
  const pidFromUrl = searchParams.get("pid");

  const [status, setStatus] = useState<Status>("loading");
  const [errorMsg, setErrorMsg] = useState("");
  const [config, setConfig] = useState<WidgetConfig | null>(null);
  const [participantId, setParticipantId] = useState(pidFromUrl || "");
  const [agentSpeaking, setAgentSpeaking] = useState(false);
  const [userSpeaking, setUserSpeaking] = useState(false);
  const [audioLevel, setAudioLevel] = useState(0);
  const [elapsed, setElapsed] = useState(0);

  // ── Text chat state ──
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatInput, setChatInput] = useState("");
  const [agentTyping, setAgentTyping] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const micRef = useRef<MicCapture | null>(null);
  const playerRef = useRef<AudioPlayer | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const speakingTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const userSpeakingTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Derived
  const modality = config?.modality || "voice";
  const isTextChat = modality === "text";
  const agentAvatar = config?.avatar || "neutral";
  const primaryColor = config?.widget_primary_color || "#0D7377";
  const listeningMessage = config?.widget_listening_message || "Agent is listening…";

  // ── 1. Fetch widget config on mount ─────────────────────────
  useEffect(() => {
    if (!widgetKey) return;
    widget
      .config(widgetKey)
      .then((cfg) => {
        setConfig(cfg);
        if (cfg.participant_id_mode === "predefined") {
          if (!pidFromUrl) {
            setStatus("error");
            setErrorMsg(
              "This interview requires a valid participant link. Please use the link provided by your researcher."
            );
          } else {
            setParticipantId(pidFromUrl);
            setStatus("idle");
          }
        } else if (cfg.participant_id_mode === "input") {
          setStatus("input");
        } else {
          setStatus("idle");
        }
      })
      .catch(() => {
        setStatus("error");
        setErrorMsg("This interview is not available. Please check the link or contact your researcher.");
      });
  }, [widgetKey, pidFromUrl]);

  // ── Auto-scroll chat to bottom ──────────────────────────────
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatMessages, agentTyping]);

  // ── Cleanup on unmount ──────────────────────────────────────
  useEffect(() => {
    return () => {
      wsRef.current?.close();
      micRef.current?.stop();
      playerRef.current?.destroy();
      if (timerRef.current) clearInterval(timerRef.current);
      if (speakingTimeoutRef.current) clearTimeout(speakingTimeoutRef.current);
      if (userSpeakingTimeoutRef.current) clearTimeout(userSpeakingTimeoutRef.current);
    };
  }, []);

  // ── Audio level handler (for voice wave) ────────────────────
  const handleAudioLevel = useCallback((level: number) => {
    setAudioLevel(level);

    if (level > 0.05) {
      setUserSpeaking(true);
      if (userSpeakingTimeoutRef.current) clearTimeout(userSpeakingTimeoutRef.current);
      userSpeakingTimeoutRef.current = setTimeout(() => setUserSpeaking(false), 400);
    }
  }, []);

  // ── 2. Start interview ──────────────────────────────────────
  const handleStart = useCallback(async () => {
    if (!widgetKey) return;
    setStatus("connecting");
    setErrorMsg("");
    setElapsed(0);

    try {
      const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
      let wsUrl = `${proto}//${window.location.host}/ws/interview/${widgetKey}`;

      const pid =
        config?.participant_id_mode === "random"
          ? undefined
          : participantId.trim() || undefined;
      if (pid) {
        wsUrl += `?pid=${encodeURIComponent(pid)}`;
      }

      const ws = new WebSocket(wsUrl);
      ws.binaryType = "arraybuffer";
      wsRef.current = ws;

      const player = new AudioPlayer();
      playerRef.current = player;

      ws.onopen = async () => {
        setStatus("active");

        const start = Date.now();
        timerRef.current = setInterval(() => {
          setElapsed(Math.floor((Date.now() - start) / 1000));
        }, 1000);

        const mic = new MicCapture();
        micRef.current = mic;

        await mic.start(
          (pcm16) => {
            if (ws.readyState === WebSocket.OPEN) {
              const frame = encodeAudioFrame(pcm16);
              ws.send(frame);
            }
          },
          handleAudioLevel
        );
      };

      // Track whether we received a server-side error so ws.onclose
      // doesn't overwrite the error state with "ended" (race condition).
      let receivedError = false;

      ws.onmessage = (event) => {
        const data =
          event.data instanceof ArrayBuffer
            ? new Uint8Array(event.data)
            : null;

        if (!data) {
          try {
            const json = JSON.parse(event.data as string);
            if (json.error) {
              receivedError = true;
              setStatus("error");
              setErrorMsg(json.error);
            }
          } catch {
            /* ignore */
          }
          return;
        }

        const decoded = decodeFrame(data);

        switch (decoded.type) {
          case "audio":
            setAgentSpeaking(true);
            player.play(decoded.audio, decoded.sampleRate);
            if (speakingTimeoutRef.current)
              clearTimeout(speakingTimeoutRef.current);
            speakingTimeoutRef.current = setTimeout(
              () => setAgentSpeaking(false),
              600
            );
            break;
        }
      };

      ws.onclose = (event) => {
        micRef.current?.stop();
        if (timerRef.current) clearInterval(timerRef.current);

        // Don't overwrite error status — the error message is more useful
        // than a generic "Interview complete" screen.
        if (receivedError) return;

        // WebSocket close codes 4000+ are application-level errors
        if (event.code >= 4000) {
          setStatus("error");
          setErrorMsg(
            event.reason || "The interview could not be started. Please check the link or contact your researcher."
          );
          return;
        }

        setStatus("ended");
      };

      ws.onerror = () => {
        receivedError = true;
        setStatus("error");
        setErrorMsg("Connection lost. Please try again.");
      };
    } catch (err) {
      setStatus("error");
      setErrorMsg(
        err instanceof Error ? err.message : "Failed to start interview"
      );
    }
  }, [widgetKey, config, participantId, handleAudioLevel]);

  // ── 2b. Start text chat ─────────────────────────────────────
  const handleStartChat = useCallback(async () => {
    if (!widgetKey) return;
    setStatus("connecting");
    setErrorMsg("");
    setElapsed(0);
    setChatMessages([]);
    setAgentTyping(false);

    try {
      const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
      let wsUrl = `${proto}//${window.location.host}/ws/chat/${widgetKey}`;

      const pid =
        config?.participant_id_mode === "random"
          ? undefined
          : participantId.trim() || undefined;
      if (pid) {
        wsUrl += `?pid=${encodeURIComponent(pid)}`;
      }

      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        setStatus("active");
        const start = Date.now();
        timerRef.current = setInterval(() => {
          setElapsed(Math.floor((Date.now() - start) / 1000));
        }, 1000);
      };

      let receivedError = false;

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data as string);
          switch (msg.type) {
            case "welcome":
              setChatMessages((prev) => [
                ...prev,
                { id: crypto.randomUUID(), role: "agent", text: msg.text, timestamp: new Date() },
              ]);
              setAgentTyping(false);
              break;
            case "message":
              setChatMessages((prev) => [
                ...prev,
                { id: crypto.randomUUID(), role: msg.role || "agent", text: msg.text, timestamp: new Date() },
              ]);
              setAgentTyping(false);
              break;
            case "typing":
              setAgentTyping(true);
              break;
            case "ended":
              setStatus("ended");
              setAgentTyping(false);
              break;
            case "error":
              receivedError = true;
              setStatus("error");
              setErrorMsg(msg.text);
              setAgentTyping(false);
              break;
          }
        } catch {
          /* ignore */
        }
      };

      ws.onclose = (event) => {
        if (timerRef.current) clearInterval(timerRef.current);
        if (receivedError) return;
        if (event.code >= 4000) {
          setStatus("error");
          setErrorMsg(event.reason || "The interview could not be started.");
          return;
        }
        setStatus("ended");
      };

      ws.onerror = () => {
        receivedError = true;
        setStatus("error");
        setErrorMsg("Connection lost. Please try again.");
      };
    } catch (err) {
      setStatus("error");
      setErrorMsg(err instanceof Error ? err.message : "Failed to start");
    }
  }, [widgetKey, config, participantId]);

  // ── Send text message ──────────────────────────────────────
  const handleSendMessage = useCallback(() => {
    const text = chatInput.trim();
    if (!text || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;

    // Add user message to UI
    setChatMessages((prev) => [
      ...prev,
      { id: crypto.randomUUID(), role: "user", text, timestamp: new Date() },
    ]);
    setChatInput("");

    // Send to server
    wsRef.current.send(JSON.stringify({ type: "message", text }));
  }, [chatInput]);

  const handleStop = useCallback(() => {
    wsRef.current?.close();
    micRef.current?.stop();
    playerRef.current?.stop();
    if (timerRef.current) clearInterval(timerRef.current);
    setStatus("ended");
  }, []);

  const handleSubmitParticipantId = (e: React.FormEvent) => {
    e.preventDefault();
    if (participantId.trim()) {
      setStatus("idle");
    }
  };

  // ── Format elapsed time ─────────────────────────────────────
  const formatTime = (s: number) => {
    const m = Math.floor(s / 60);
    const sec = s % 60;
    return `${m.toString().padStart(2, "0")}:${sec.toString().padStart(2, "0")}`;
  };

  // ── Determine orb visual state ──────────────────────────────
  const orbState: "idle" | "connecting" | "listening" | "speaking" =
    status === "connecting" ? "connecting"
    : agentSpeaking ? "speaking"
    : status === "active" ? "listening"
    : "idle";

  // ── Render ──────────────────────────────────────────────────

  if (status === "loading") {
    return (
      <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100 flex items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <div className="h-8 w-8 rounded-full border-2 border-gray-300 border-t-gray-800 animate-spin" />
          <span className="text-gray-400 text-sm">Loading…</span>
        </div>
      </div>
    );
  }

  return (
    <div
      className="min-h-screen flex flex-col items-center justify-center p-6 selection:bg-gray-900/10"
      style={{
        background: `radial-gradient(ellipse at 50% 30%, ${hexToRgba(primaryColor, 0.06)} 0%, transparent 70%), linear-gradient(180deg, #fafafa 0%, #f3f4f6 100%)`,
        "--orb-rgb": hexToRgb(primaryColor),
      } as React.CSSProperties}
    >
      <div className="w-full max-w-md flex flex-col items-center">
        {/* ── Title & description ─────────────────────────────── */}
        <div className="text-center mb-10 animate-fade-in">
          <h1 className="text-2xl font-bold text-gray-900 tracking-tight mb-2">
            {config?.widget_title || (isTextChat ? "Chat Interview" : "Voice Interview")}
          </h1>
          {status !== "active" && status !== "ended" && config?.widget_description && (
            <p className="text-sm text-gray-500 max-w-sm mx-auto leading-relaxed">
              {config.widget_description}
            </p>
          )}
          {status === "active" && (
            <p className="text-sm text-gray-500 animate-fade-in">
              {isTextChat ? "Chat in progress — type naturally" : "Interview in progress — speak naturally"}
            </p>
          )}
          {status === "ended" && (
            <div className="animate-fade-in">
              <div className="inline-flex items-center gap-2 rounded-full bg-emerald-50 text-emerald-700 px-4 py-2 text-sm font-medium">
                <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                  <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                </svg>
                Interview complete
              </div>
              <p className="text-sm text-gray-400 mt-3">
                Thank you for your participation!
              </p>
            </div>
          )}
        </div>

        {/* ── Text Chat UI ───────────────────────────────────── */}
        {isTextChat && (status === "active" || status === "connecting") && (
          <div className="w-full max-w-lg mb-6 animate-scale-in">
            {/* Chat messages area */}
            <div
              className="rounded-2xl border border-gray-200 bg-white shadow-sm overflow-hidden flex flex-col"
              style={{ height: "min(60vh, 500px)" }}
            >
              <div className="flex-1 overflow-y-auto p-4 space-y-3" id="chat-scroll">
                {chatMessages.map((msg) => (
                  <div
                    key={msg.id}
                    className={`flex items-end gap-2 animate-fade-in ${
                      msg.role === "user" ? "flex-row-reverse" : "flex-row"
                    }`}
                  >
                    {/* Agent avatar */}
                    {msg.role === "agent" && agentAvatar !== "none" && (
                      <div
                        className="flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-sm"
                        style={{ backgroundColor: hexToRgba(primaryColor, 0.1) }}
                      >
                        {AVATAR_EMOJI[agentAvatar] || "🤖"}
                      </div>
                    )}

                    {/* Bubble */}
                    <div
                      className={`max-w-[75%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
                        msg.role === "user"
                          ? "text-white rounded-br-md"
                          : "bg-gray-100 text-gray-800 rounded-bl-md"
                      }`}
                      style={msg.role === "user" ? { backgroundColor: primaryColor } : undefined}
                    >
                      <ChatBubbleContent text={msg.text} isUser={msg.role === "user"} />
                    </div>

                    {/* User avatar */}
                    {msg.role === "user" && agentAvatar !== "none" && (
                      <div className="flex-shrink-0 w-8 h-8 rounded-full bg-gray-200 flex items-center justify-center text-sm">
                        👤
                      </div>
                    )}
                  </div>
                ))}

                {/* Typing indicator */}
                {agentTyping && (
                  <div className="flex items-end gap-2 animate-fade-in">
                    {agentAvatar !== "none" && (
                      <div
                        className="flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-sm"
                        style={{ backgroundColor: hexToRgba(primaryColor, 0.1) }}
                      >
                        {AVATAR_EMOJI[agentAvatar] || "🤖"}
                      </div>
                    )}
                    <div className="bg-gray-100 rounded-2xl rounded-bl-md px-4 py-3 flex items-center gap-1">
                      <span className="typing-dot" style={{ animationDelay: "0s" }} />
                      <span className="typing-dot" style={{ animationDelay: "0.15s" }} />
                      <span className="typing-dot" style={{ animationDelay: "0.3s" }} />
                    </div>
                  </div>
                )}

                <div ref={chatEndRef} />
              </div>

              {/* Input area */}
              <div className="border-t border-gray-200 p-3 bg-gray-50">
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    handleSendMessage();
                  }}
                  className="flex items-center gap-2"
                >
                  <input
                    type="text"
                    value={chatInput}
                    onChange={(e) => setChatInput(e.target.value)}
                    className="flex-1 rounded-xl border border-gray-200 bg-white px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-gray-300 focus:border-transparent transition-all placeholder:text-gray-400"
                    placeholder="Type your response…"
                    autoFocus
                    disabled={status !== "active"}
                  />
                  <button
                    type="submit"
                    disabled={!chatInput.trim() || status !== "active"}
                    className="flex-shrink-0 rounded-xl p-2.5 text-white transition-all hover:opacity-90 active:scale-95 disabled:opacity-40 disabled:cursor-not-allowed"
                    style={{ backgroundColor: primaryColor }}
                  >
                    <svg className="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
                      <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z" />
                    </svg>
                  </button>
                </form>
              </div>
            </div>
          </div>
        )}

        {/* ── Voice Orb ──────────────────────────────────────── */}
        {!isTextChat && (status === "active" || status === "connecting") && (
          <div className="relative mb-6 flex flex-col items-center animate-scale-in">
            <div className="relative flex items-center justify-center" style={{ width: 200, height: 200 }}>
              {/* Expanding rings when agent is speaking */}
              {orbState === "speaking" && (
                <>
                  <div
                    className="absolute inset-0 rounded-full orb-ring"
                    style={{
                      border: `2px solid ${hexToRgba(primaryColor, 0.25)}`,
                      animationDelay: "0s",
                    }}
                  />
                  <div
                    className="absolute inset-0 rounded-full orb-ring"
                    style={{
                      border: `2px solid ${hexToRgba(primaryColor, 0.15)}`,
                      animationDelay: "0.8s",
                    }}
                  />
                  <div
                    className="absolute inset-0 rounded-full orb-ring"
                    style={{
                      border: `1.5px solid ${hexToRgba(primaryColor, 0.1)}`,
                      animationDelay: "1.6s",
                    }}
                  />
                </>
              )}

              {/* Breathing ring when listening (user not speaking) */}
              {orbState === "listening" && !userSpeaking && (
                <div
                  className="absolute rounded-full animate-orb-breathe"
                  style={{
                    inset: -12,
                    border: `1.5px solid ${hexToRgba(primaryColor, 0.2)}`,
                  }}
                />
              )}

              {/* Main orb */}
              <div
                className={`relative rounded-full flex items-center justify-center transition-all duration-700 ease-out ${
                  orbState === "speaking" ? "scale-105" : "scale-100"
                }`}
                style={{
                  width: 160,
                  height: 160,
                  background: `radial-gradient(circle at 35% 30%, ${hexToRgba(primaryColor, 0.85)}, ${primaryColor} 80%)`,
                  boxShadow: [
                    `0 0 0 1px ${hexToRgba(primaryColor, 0.1)}`,
                    orbState === "speaking"
                      ? `0 0 80px ${hexToRgba(primaryColor, 0.3)}, 0 20px 60px ${hexToRgba(primaryColor, 0.15)}`
                      : `0 0 40px ${hexToRgba(primaryColor, 0.1)}, 0 10px 30px ${hexToRgba(primaryColor, 0.08)}`,
                  ].join(", "),
                }}
              >
                {/* Glass highlight */}
                <div
                  className="absolute rounded-full"
                  style={{
                    top: "12%",
                    left: "18%",
                    width: "42%",
                    height: "28%",
                    background: "linear-gradient(180deg, rgba(255,255,255,0.35) 0%, rgba(255,255,255,0) 100%)",
                    borderRadius: "50%",
                    filter: "blur(6px)",
                  }}
                />

                {/* Icon / state indicator */}
                {orbState === "connecting" ? (
                  <Spinner className="w-8 h-8 text-white" />
                ) : orbState === "speaking" ? (
                  <SoundWaveIcon className="w-10 h-10 text-white opacity-90" />
                ) : userSpeaking ? (
                  // Voice wave bars when user is speaking
                  <VoiceWaveBars level={audioLevel} color="white" />
                ) : (
                  <MicIcon className="w-7 h-7 text-white opacity-70" />
                )}
              </div>
            </div>

            {/* Status label below orb */}
            <div className="mt-5 h-7 flex items-center justify-center">
              {orbState === "connecting" && (
                <span className="text-xs text-gray-400 animate-pulse">Connecting…</span>
              )}
              {orbState === "listening" && !userSpeaking && (
                <span className="text-xs text-gray-500 animate-fade-in font-medium">
                  {listeningMessage}
                </span>
              )}
              {orbState === "listening" && userSpeaking && (
                <span className="text-xs text-gray-500 animate-fade-in font-medium flex items-center gap-1.5">
                  <span className="relative flex h-2 w-2">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
                  </span>
                  You are speaking
                </span>
              )}
              {orbState === "speaking" && (
                <span className="text-xs text-gray-500 animate-fade-in font-medium flex items-center gap-1.5">
                  <span className="relative flex h-2 w-2">
                    <span
                      className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75"
                      style={{ backgroundColor: hexToRgba(primaryColor, 0.6) }}
                    />
                    <span
                      className="relative inline-flex rounded-full h-2 w-2"
                      style={{ backgroundColor: primaryColor }}
                    />
                  </span>
                  Agent is speaking
                </span>
              )}
            </div>
          </div>
        )}

        {/* ── Idle orb/icon (before starting) ─────────────────── */}
        {status === "idle" && isTextChat && (
          <div className="relative mb-10 flex items-center justify-center animate-scale-in">
            <div
              className="absolute rounded-full animate-orb-breathe"
              style={{
                width: 140,
                height: 140,
                backgroundColor: hexToRgba(primaryColor, 0.06),
              }}
            />
            <div
              className="rounded-full flex items-center justify-center"
              style={{
                width: 120,
                height: 120,
                background: `radial-gradient(circle at 35% 30%, ${hexToRgba(primaryColor, 0.75)}, ${hexToRgba(primaryColor, 0.55)} 80%)`,
                boxShadow: `0 0 0 1px ${hexToRgba(primaryColor, 0.08)}, 0 8px 24px ${hexToRgba(primaryColor, 0.12)}`,
              }}
            >
              <ChatIcon className="w-8 h-8 text-white opacity-80" />
            </div>
          </div>
        )}
        {status === "idle" && !isTextChat && (
          <div className="relative mb-10 flex items-center justify-center animate-scale-in">
            {/* Breathing glow */}
            <div
              className="absolute rounded-full animate-orb-breathe"
              style={{
                width: 140,
                height: 140,
                backgroundColor: hexToRgba(primaryColor, 0.06),
              }}
            />
            <div
              className="rounded-full flex items-center justify-center"
              style={{
                width: 120,
                height: 120,
                background: `radial-gradient(circle at 35% 30%, ${hexToRgba(primaryColor, 0.75)}, ${hexToRgba(primaryColor, 0.55)} 80%)`,
                boxShadow: `0 0 0 1px ${hexToRgba(primaryColor, 0.08)}, 0 8px 24px ${hexToRgba(primaryColor, 0.12)}`,
              }}
            >
              {/* Glass highlight */}
              <div
                className="absolute rounded-full"
                style={{
                  top: "calc(50% - 60px + 14%)",
                  left: "calc(50% - 60px + 20%)",
                  width: "36px",
                  height: "24px",
                  background: "linear-gradient(180deg, rgba(255,255,255,0.3) 0%, transparent 100%)",
                  borderRadius: "50%",
                  filter: "blur(4px)",
                }}
              />
              <MicIcon className="w-7 h-7 text-white opacity-70" />
            </div>
          </div>
        )}

        {/* ── Timer ───────────────────────────────────────────── */}
        {status === "active" && (
          <div className="mb-8 text-center animate-fade-in">
            <span className="font-mono text-lg text-gray-400 tracking-[0.15em] tabular-nums">
              {formatTime(elapsed)}
            </span>
          </div>
        )}

        {/* ── Error message ───────────────────────────────────── */}
        {status === "error" && (
          <div className="mb-6 w-full animate-slide-up">
            <div className="rounded-2xl bg-red-50 border border-red-100 px-5 py-4 text-center">
              <p className="text-sm text-red-700">{errorMsg}</p>
            </div>
          </div>
        )}

        {/* ── Participant ID input (input mode) ───────────────── */}
        {status === "input" && (
          <form
            onSubmit={handleSubmitParticipantId}
            className="mb-6 w-full rounded-2xl border border-gray-200 bg-white p-6 shadow-sm animate-slide-up"
          >
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Enter your Participant ID
            </label>
            <p className="text-xs text-gray-400 mb-4">
              Please enter the identifier provided to you by the researcher.
            </p>
            <div className="flex gap-2">
              <input
                type="text"
                value={participantId}
                onChange={(e) => setParticipantId(e.target.value)}
                className="input-styled flex-1"
                placeholder="e.g. P001"
                autoFocus
                required
              />
              <button
                type="submit"
                className="rounded-xl px-5 py-2.5 text-sm font-medium text-white transition-all hover:opacity-90 active:scale-[0.98]"
                style={{ backgroundColor: primaryColor }}
              >
                Continue
              </button>
            </div>
          </form>
        )}

        {/* ── Action buttons ──────────────────────────────────── */}
        <div className="flex justify-center animate-fade-in">
          {status === "idle" && (
            <button
              onClick={isTextChat ? handleStartChat : handleStart}
              className="group flex items-center gap-3 rounded-2xl px-8 py-4 text-white font-semibold shadow-lg hover:shadow-xl transition-all duration-300 hover:scale-[1.03] active:scale-[0.98]"
              style={{
                backgroundColor: primaryColor,
                boxShadow: `0 8px 30px ${hexToRgba(primaryColor, 0.25)}`,
              }}
            >
              {isTextChat ? <ChatIcon className="w-5 h-5" /> : <MicIcon className="w-5 h-5" />}
              {isTextChat ? "Start Chat" : "Start Interview"}
            </button>
          )}

          {status === "connecting" && (
            <button
              disabled
              className="flex items-center gap-3 rounded-2xl bg-gray-300 px-8 py-4 text-white font-semibold cursor-not-allowed"
            >
              <Spinner className="w-5 h-5" />
              Connecting…
            </button>
          )}

          {status === "active" && (
            <button
              onClick={handleStop}
              className="flex items-center gap-3 rounded-2xl bg-red-600 px-8 py-4 text-white font-semibold shadow-lg hover:bg-red-700 hover:shadow-xl transition-all duration-300 hover:scale-[1.03] active:scale-[0.98]"
            >
              <StopIcon className="w-5 h-5" />
              End Interview
            </button>
          )}

          {status === "ended" && (
            <p className="text-gray-400 text-sm animate-fade-in">
              You may close this page now.
            </p>
          )}

          {status === "error" && (
            <button
              onClick={() => {
                setStatus(
                  config?.participant_id_mode === "input" ? "input" : "idle"
                );
                setErrorMsg("");
              }}
              className="rounded-2xl px-8 py-4 text-white font-semibold shadow-lg transition-all duration-300 hover:scale-[1.03] active:scale-[0.98]"
              style={{
                backgroundColor: primaryColor,
                boxShadow: `0 8px 30px ${hexToRgba(primaryColor, 0.25)}`,
              }}
            >
              Try Again
            </button>
          )}
        </div>
      </div>

      {/* Branding footer */}
      <p className="mt-16 text-[11px] text-gray-300 tracking-wider uppercase">
        Powered by OASIS
      </p>
    </div>
  );
}

// ── Voice Wave Bars (user speaking visualisation) ────────────────

function VoiceWaveBars({ level, color }: { level: number; color: string }) {
  const barCount = 5;
  const bars = [];
  for (let i = 0; i < barCount; i++) {
    // Create varied heights based on position and audio level
    const centerDistance = Math.abs(i - (barCount - 1) / 2);
    const baseHeight = 1 - centerDistance * 0.3;
    const speed = 0.4 + Math.random() * 0.3;
    const delay = i * 0.08;

    bars.push(
      <div
        key={i}
        className="voice-bar rounded-full"
        style={{
          width: 4,
          height: 24 * baseHeight * Math.max(0.3, level),
          backgroundColor: color,
          opacity: 0.85,
          "--bar-speed": `${speed}s`,
          "--bar-delay": `${delay}s`,
        } as React.CSSProperties}
      />
    );
  }

  return (
    <div className="flex items-end gap-[3px]" style={{ height: 24 }}>
      {bars}
    </div>
  );
}

// ── SVG Icons ──────────────────────────────────────────────────

function MicIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={1.8}
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M12 1a3 3 0 00-3 3v8a3 3 0 006 0V4a3 3 0 00-3-3z"
      />
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M19 10v2a7 7 0 01-14 0v-2"
      />
      <line x1="12" y1="19" x2="12" y2="23" />
      <line x1="8" y1="23" x2="16" y2="23" />
    </svg>
  );
}

function StopIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="currentColor" viewBox="0 0 24 24">
      <rect x="6" y="6" width="12" height="12" rx="2" />
    </svg>
  );
}

function Spinner({ className }: { className?: string }) {
  return (
    <svg className={`animate-spin ${className}`} fill="none" viewBox="0 0 24 24">
      <circle
        className="opacity-25"
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeWidth="4"
      />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"
      />
    </svg>
  );
}

function ChatIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
      />
    </svg>
  );
}

function SoundWaveIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="currentColor" viewBox="0 0 24 24">
      <rect x="4" y="9" width="2" height="6" rx="1">
        <animate attributeName="height" values="6;12;6" dur="0.8s" repeatCount="indefinite" />
        <animate attributeName="y" values="9;6;9" dur="0.8s" repeatCount="indefinite" />
      </rect>
      <rect x="8" y="7" width="2" height="10" rx="1">
        <animate attributeName="height" values="10;4;10" dur="0.6s" repeatCount="indefinite" />
        <animate attributeName="y" values="7;10;7" dur="0.6s" repeatCount="indefinite" />
      </rect>
      <rect x="12" y="5" width="2" height="14" rx="1">
        <animate attributeName="height" values="14;8;14" dur="0.7s" repeatCount="indefinite" />
        <animate attributeName="y" values="5;8;5" dur="0.7s" repeatCount="indefinite" />
      </rect>
      <rect x="16" y="7" width="2" height="10" rx="1">
        <animate attributeName="height" values="10;6;10" dur="0.65s" repeatCount="indefinite" />
        <animate attributeName="y" values="7;9;7" dur="0.65s" repeatCount="indefinite" />
      </rect>
      <rect x="20" y="9" width="2" height="6" rx="1">
        <animate attributeName="height" values="6;10;6" dur="0.75s" repeatCount="indefinite" />
        <animate attributeName="y" values="9;7;9" dur="0.75s" repeatCount="indefinite" />
      </rect>
    </svg>
  );
}
