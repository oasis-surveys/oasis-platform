/**
 * SURVEYOR — Participant interview widget.
 *
 * Accessible at /interview/:widgetKey — this is the page a study participant
 * sees when they join a voice interview via the shareable link.
 *
 * Features:
 *  - Fetches widget config (title, description, colour, participant ID mode)
 *  - Handles participant identification: random / predefined (via ?pid=) / user input
 *  - Animated orb visualisation with voice wave + listening state
 *  - Call timer
 *  - Backend still logs diarised transcripts for researcher review
 */

import { useEffect, useRef, useState, useCallback } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { widget, type WidgetConfig } from "../lib/api";
import { MicCapture, AudioPlayer } from "../lib/audio";
import { encodeAudioFrame, decodeFrame } from "../lib/pipecat-proto";

type Status = "loading" | "idle" | "input" | "connecting" | "active" | "ended" | "error";

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

  const wsRef = useRef<WebSocket | null>(null);
  const micRef = useRef<MicCapture | null>(null);
  const playerRef = useRef<AudioPlayer | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const speakingTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const userSpeakingTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Derived colours
  const primaryColor = config?.widget_primary_color || "#111827";
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

      ws.onmessage = (event) => {
        const data =
          event.data instanceof ArrayBuffer
            ? new Uint8Array(event.data)
            : null;

        if (!data) {
          try {
            const json = JSON.parse(event.data as string);
            if (json.error) {
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

      ws.onclose = () => {
        micRef.current?.stop();
        if (timerRef.current) clearInterval(timerRef.current);
        setStatus("ended");
      };

      ws.onerror = () => {
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
            {config?.widget_title || "Voice Interview"}
          </h1>
          {status !== "active" && status !== "ended" && config?.widget_description && (
            <p className="text-sm text-gray-500 max-w-sm mx-auto leading-relaxed">
              {config.widget_description}
            </p>
          )}
          {status === "active" && (
            <p className="text-sm text-gray-500 animate-fade-in">
              Interview in progress — speak naturally
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

        {/* ── Orb ─────────────────────────────────────────────── */}
        {(status === "active" || status === "connecting") && (
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

        {/* ── Idle orb (before starting) ──────────────────────── */}
        {status === "idle" && (
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
              onClick={handleStart}
              className="group flex items-center gap-3 rounded-2xl px-8 py-4 text-white font-semibold shadow-lg hover:shadow-xl transition-all duration-300 hover:scale-[1.03] active:scale-[0.98]"
              style={{
                backgroundColor: primaryColor,
                boxShadow: `0 8px 30px ${hexToRgba(primaryColor, 0.25)}`,
              }}
            >
              <MicIcon className="w-5 h-5" />
              Start Interview
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
        Powered by SURVEYOR
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
