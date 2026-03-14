/**
 * OASIS — Help tooltip with ? icon.
 *
 * Hover to show an explanation popup.
 *
 * Usage:
 *   <HelpTooltip text="This is the model used to generate responses." />
 */

import { useState, useRef, useEffect } from "react";

interface HelpTooltipProps {
  text: string;
  /** Optional className for the wrapper */
  className?: string;
}

export default function HelpTooltip({ text, className = "" }: HelpTooltipProps) {
  const [show, setShow] = useState(false);
  const [position, setPosition] = useState<"top" | "bottom">("top");
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (show && ref.current) {
      const rect = ref.current.getBoundingClientRect();
      // If tooltip would go above viewport, show below instead
      setPosition(rect.top < 80 ? "bottom" : "top");
    }
  }, [show]);

  return (
    <div
      className={`relative inline-flex ${className}`}
      ref={ref}
      onMouseEnter={() => setShow(true)}
      onMouseLeave={() => setShow(false)}
    >
      <button
        type="button"
        tabIndex={-1}
        className="inline-flex items-center justify-center h-4 w-4 rounded-full bg-gray-200 text-gray-500 text-[10px] font-bold leading-none hover:bg-gray-300 hover:text-gray-700 transition-colors cursor-help"
        aria-label="Help"
      >
        ?
      </button>
      {show && (
        <div
          className={`absolute z-50 w-64 px-3.5 py-2.5 rounded-xl bg-gray-900 text-white text-xs leading-relaxed shadow-xl animate-tooltip-in ${
            position === "top"
              ? "bottom-full mb-2 left-1/2 -translate-x-1/2"
              : "top-full mt-2 left-1/2 -translate-x-1/2"
          }`}
        >
          {text}
          {/* Arrow */}
          <div
            className={`absolute left-1/2 -translate-x-1/2 w-2 h-2 bg-gray-900 rotate-45 ${
              position === "top" ? "top-full -mt-1" : "bottom-full -mb-1"
            }`}
          />
        </div>
      )}
    </div>
  );
}
