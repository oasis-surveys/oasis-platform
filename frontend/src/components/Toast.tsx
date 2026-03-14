/**
 * OASIS — Toast notification component.
 *
 * Usage:
 *   const [toast, showToast] = useToast();
 *   showToast("Link copied!");
 *   {toast}
 */

import { useCallback, useState, useEffect, type ReactNode } from "react";

interface ToastProps {
  message: string;
  icon?: "success" | "info" | "warning";
  onDone: () => void;
}

function Toast({ message, icon = "success", onDone }: ToastProps) {
  useEffect(() => {
    const t = setTimeout(onDone, 2800);
    return () => clearTimeout(t);
  }, [onDone]);

  const icons = {
    success: (
      <svg className="h-4 w-4 text-emerald-400 flex-shrink-0" viewBox="0 0 20 20" fill="currentColor">
        <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
      </svg>
    ),
    info: (
      <svg className="h-4 w-4 text-blue-400 flex-shrink-0" viewBox="0 0 20 20" fill="currentColor">
        <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
      </svg>
    ),
    warning: (
      <svg className="h-4 w-4 text-amber-400 flex-shrink-0" viewBox="0 0 20 20" fill="currentColor">
        <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
      </svg>
    ),
  };

  return (
    <div className="fixed bottom-6 right-6 z-50 animate-toast-in">
      <div className="flex items-center gap-2.5 rounded-2xl bg-gray-900 px-5 py-3.5 text-sm font-medium text-white shadow-2xl shadow-gray-900/20 backdrop-blur-sm border border-white/10">
        {icons[icon]}
        {message}
      </div>
    </div>
  );
}

export function useToast(): [ReactNode, (msg: string, icon?: "success" | "info" | "warning") => void] {
  const [state, setState] = useState<{ msg: string; icon: "success" | "info" | "warning" } | null>(null);

  const show = useCallback((msg: string, icon: "success" | "info" | "warning" = "success") => {
    setState({ msg, icon });
  }, []);

  const node = state ? (
    <Toast message={state.msg} icon={state.icon} onDone={() => setState(null)} />
  ) : null;

  return [node, show];
}

export default Toast;
