import { type ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import { useTutorial, type TutorialStep } from "./Tutorial";

const TUTORIAL_STEPS: TutorialStep[] = [
  {
    title: "Welcome to SURVEYOR",
    body: "This guided tour will walk you through the key features of the platform. Let's get started!",
  },
  {
    title: "Create a Study",
    body: "Start by creating a study. A study is a research project that contains one or more conversational agents. Click '+ New Study' to begin.",
    selector: "[data-tour='new-study']",
  },
  {
    title: "Configure an Agent",
    body: "Each study has agents — AI interviewers with their own prompt, voice model, and settings. Create and configure agents from the study detail page.",
  },
  {
    title: "Choose a Pipeline",
    body: "Select 'Modular' for STT → LLM → TTS chains, or 'Voice-to-Voice' for direct multimodal models like OpenAI Realtime or Gemini Live.",
  },
  {
    title: "Share the Interview Link",
    body: "Once your agent is active, copy the interview link or embed code and share it with participants. Each interview is recorded with a diarised transcript.",
  },
  {
    title: "Monitor Sessions",
    body: "View live sessions, read transcripts, and export data from the Sessions page. You can also terminate sessions remotely.",
  },
  {
    title: "You're Ready!",
    body: "That's it! Create your first study and start conducting AI-powered interviews. Use the ? icons throughout the dashboard for contextual help.",
  },
];

interface LayoutProps {
  children: ReactNode;
}

export default function Layout({ children }: LayoutProps) {
  const location = useLocation();
  const [tutorial, startTutorial] = useTutorial(TUTORIAL_STEPS);

  return (
    <div className="min-h-screen bg-gray-50/80">
      {tutorial}

      {/* ── Top Navigation ── */}
      <nav className="sticky top-0 z-40 border-b border-gray-200/80 bg-white/80 backdrop-blur-xl">
        <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
          <Link to="/" className="flex items-center gap-2.5 hover:opacity-80 transition-opacity">
            {/* Logo mark */}
            <div className="h-7 w-7 rounded-lg bg-gray-900 flex items-center justify-center">
              <svg className="h-4 w-4 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 1a3 3 0 00-3 3v8a3 3 0 006 0V4a3 3 0 00-3-3z" />
                <path strokeLinecap="round" strokeLinejoin="round" d="M19 10v2a7 7 0 01-14 0v-2" />
              </svg>
            </div>
            <span className="text-lg font-bold tracking-tight text-gray-900">
              SURVEYOR
            </span>
            <span className="rounded-full bg-gray-100 px-2 py-0.5 text-[10px] font-semibold text-gray-500 uppercase tracking-wider">
              Beta
            </span>
          </Link>
          <div className="flex items-center gap-3">
            <button
              onClick={startTutorial}
              className="inline-flex items-center gap-1.5 rounded-xl border border-gray-200 bg-white px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50 hover:border-gray-300 transition-all"
            >
              <svg className="h-3.5 w-3.5" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-8-3a1 1 0 00-.867.5 1 1 0 11-1.731-1A3 3 0 0113 8a3.001 3.001 0 01-2 2.83V11a1 1 0 11-2 0v-1a1 1 0 011-1 1 1 0 100-2zm0 8a1 1 0 100-2 1 1 0 000 2z" clipRule="evenodd" />
              </svg>
              Get Started
            </button>
            <span className="text-xs text-gray-400 hidden sm:block">Admin Dashboard</span>
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
