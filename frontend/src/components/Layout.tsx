import { type ReactNode } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useTutorial, type TutorialStep } from "./Tutorial";
import { useAuth } from "../contexts/AuthContext";

const TUTORIAL_STEPS: TutorialStep[] = [
  {
    title: "Welcome to OASIS",
    body: "This guided tour will walk you through the key features of the platform. Let's get started!",
    route: "/",
  },
  {
    title: "Create a Study",
    body: "Start by creating a study. A study is a research project that contains one or more conversational agents. Click '+ New Study' to begin — or use 'Try a template' to spin up a demo study with a ready-made agent.",
    selector: "[data-tour='new-study']",
    route: "/",
  },
  {
    title: "Configure API Keys",
    body: "Set your provider API keys here (OpenAI, Deepgram, ElevenLabs, etc.) so your agents can connect. Dashboard overrides take priority over .env values.",
    selector: "[data-tour='settings-keys']",
    route: "/settings",
  },
  {
    title: "Configure an Agent",
    body: "Each study has agents — AI interviewers with their own prompt, voice model, and settings. Create and configure agents from the study detail page.",
    route: "/",
  },
  {
    title: "Choose a Pipeline",
    body: "Select 'Modular' for STT → LLM → TTS chains, or 'Voice-to-Voice' for direct multimodal models like OpenAI Realtime or Gemini Live.",
    route: "/",
  },
  {
    title: "Share the Interview Link",
    body: "Once your agent is active, copy the interview link or embed code and share it with participants. Each interview is recorded with a diarised transcript.",
    route: "/",
  },
  {
    title: "Monitor Sessions",
    body: "View live sessions, read transcripts, and export data from the Sessions page. You can also terminate sessions remotely.",
    route: "/",
  },
  {
    title: "You're Ready!",
    body: "That's it! Create your first study and start conducting AI-powered interviews. Use the ? icons throughout the dashboard for contextual help.",
    route: "/",
  },
];

interface LayoutProps {
  children: ReactNode;
}

export default function Layout({ children }: LayoutProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const { authEnabled, username, logout } = useAuth();
  const [tutorial, startTutorial] = useTutorial(TUTORIAL_STEPS);

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <div className="min-h-screen" style={{ backgroundColor: "var(--oasis-bg)" }}>
      {tutorial}

      {/* ── Top Navigation ── */}
      <nav className="sticky top-0 z-40 border-b border-gray-200/80 bg-white/90 backdrop-blur-xl">
        <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
          <Link to="/" className="flex items-center gap-2.5 hover:opacity-80 transition-opacity">
            {/* OASIS Logo */}
            <img
              src="/oasis-logo.png"
              alt="OASIS"
              className="h-9 w-auto"
            />
            <span className="text-lg font-bold tracking-tight" style={{ color: "var(--oasis-charcoal)" }}>
              OASIS
            </span>
            <span
              className="rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider"
              style={{ backgroundColor: "var(--oasis-gold-warm)", color: "var(--oasis-slate)" }}
            >
              Beta
            </span>
          </Link>
          <div className="flex items-center gap-3">
            <button
              onClick={startTutorial}
              className="inline-flex items-center gap-1.5 rounded-xl border border-gray-200 bg-white px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-oasis-50 hover:border-oasis-300 hover:text-oasis-600 transition-all"
            >
              <svg className="h-3.5 w-3.5" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-8-3a1 1 0 00-.867.5 1 1 0 11-1.731-1A3 3 0 0113 8a3.001 3.001 0 01-2 2.83V11a1 1 0 11-2 0v-1a1 1 0 011-1 1 1 0 100-2zm0 8a1 1 0 100-2 1 1 0 000 2z" clipRule="evenodd" />
              </svg>
              Get Started
            </button>
            <Link
              to="/settings"
              className="inline-flex items-center gap-1.5 rounded-xl border border-gray-200 bg-white px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-oasis-50 hover:border-oasis-300 hover:text-oasis-600 transition-all"
            >
              <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                <circle cx="12" cy="12" r="3" />
              </svg>
              Settings
            </Link>
            {authEnabled && username && (
              <div className="flex items-center gap-2">
                <span className="text-xs text-gray-500">{username}</span>
                <button
                  onClick={handleLogout}
                  className="inline-flex items-center gap-1 rounded-xl border border-gray-200 bg-white px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-oasis-50 hover:border-oasis-300 hover:text-oasis-600 transition-all"
                >
                  <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
                  </svg>
                  Logout
                </button>
              </div>
            )}
            {!authEnabled && (
              <span className="text-xs text-gray-400 hidden sm:block">Admin Dashboard</span>
            )}
          </div>
        </div>
      </nav>

      {/* ── Page Content ── */}
      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        <div key={location.pathname} className="page-enter">
          {children}
        </div>
      </main>
    </div>
  );
}
