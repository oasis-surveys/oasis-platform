/**
 * Collapsible settings section (AI Providers, Self-Hosted, etc.).
 */

import type { ReactNode } from "react";

interface SettingsCollapsibleSectionProps {
  title: string;
  defaultOpen?: boolean;
  children: ReactNode;
  dataTour?: string;
}

export default function SettingsCollapsibleSection({
  title,
  defaultOpen = false,
  children,
  dataTour,
}: SettingsCollapsibleSectionProps) {
  return (
    <details
      className="card group"
      open={defaultOpen}
      data-tour={dataTour}
    >
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-5 py-4 border-b border-gray-100 [&::-webkit-details-marker]:hidden">
        <h2 className="text-sm font-semibold text-gray-900">{title}</h2>
        <span
          className="text-gray-400 transition-transform group-open:rotate-180"
          aria-hidden
        >
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
          </svg>
        </span>
      </summary>
      {children}
    </details>
  );
}
