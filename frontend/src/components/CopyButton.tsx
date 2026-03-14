/**
 * SURVEYOR — Copy-to-clipboard button with icon and tooltip.
 *
 * Shows a clipboard icon that changes to a checkmark briefly after copying.
 */

import { useState, useCallback } from "react";

interface CopyButtonProps {
  /** The text to copy to clipboard */
  text: string;
  /** Optional label shown next to the icon */
  label?: string;
  /** Toast callback (optional) */
  onCopied?: (msg: string) => void;
  /** Toast message */
  toastMessage?: string;
  /** Additional className */
  className?: string;
  /** Button size variant */
  size?: "sm" | "md";
}

export default function CopyButton({
  text,
  label,
  onCopied,
  toastMessage = "Copied to clipboard",
  className = "",
  size = "sm",
}: CopyButtonProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      onCopied?.(toastMessage);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback for older browsers
      const el = document.createElement("textarea");
      el.value = text;
      document.body.appendChild(el);
      el.select();
      document.execCommand("copy");
      document.body.removeChild(el);
      setCopied(true);
      onCopied?.(toastMessage);
      setTimeout(() => setCopied(false), 2000);
    }
  }, [text, onCopied, toastMessage]);

  const sizeClasses = size === "sm"
    ? "h-7 w-7 rounded-lg"
    : "h-8 w-8 rounded-xl";

  const iconSize = size === "sm" ? "h-3.5 w-3.5" : "h-4 w-4";

  return (
    <button
      type="button"
      onClick={handleCopy}
      className={`inline-flex items-center justify-center gap-1.5 ${sizeClasses} border border-gray-200 bg-white text-gray-500 hover:text-gray-700 hover:bg-gray-50 hover:border-gray-300 transition-all active:scale-95 ${className}`}
      title="Copy to clipboard"
    >
      {copied ? (
        <svg className={`${iconSize} text-emerald-500`} viewBox="0 0 20 20" fill="currentColor">
          <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
        </svg>
      ) : (
        <svg className={iconSize} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
        </svg>
      )}
      {label && <span className="text-xs font-medium">{label}</span>}
    </button>
  );
}
