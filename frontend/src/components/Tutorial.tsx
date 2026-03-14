/**
 * SURVEYOR — Get Started tutorial walkthrough.
 *
 * A step-by-step guided tour with spotlight overlay and popups.
 * Steps can point to elements by CSS selector.
 *
 * Usage:
 *   const [tutorial, startTutorial] = useTutorial(steps);
 *   <button onClick={startTutorial}>Get Started</button>
 *   {tutorial}
 */

import { useCallback, useState, useEffect, useRef, type ReactNode } from "react";

export interface TutorialStep {
  /** Title of this step */
  title: string;
  /** Description / explanation */
  body: string;
  /** CSS selector to highlight (optional — if omitted, shows centered modal) */
  selector?: string;
}

interface TutorialOverlayProps {
  steps: TutorialStep[];
  currentStep: number;
  onNext: () => void;
  onPrev: () => void;
  onDone: () => void;
}

function TutorialOverlay({ steps, currentStep, onNext, onPrev, onDone }: TutorialOverlayProps) {
  const step = steps[currentStep];
  const isLast = currentStep === steps.length - 1;
  const isFirst = currentStep === 0;
  const popupRef = useRef<HTMLDivElement>(null);
  const [targetRect, setTargetRect] = useState<DOMRect | null>(null);

  useEffect(() => {
    if (step.selector) {
      const el = document.querySelector(step.selector);
      if (el) {
        const rect = el.getBoundingClientRect();
        setTargetRect(rect);
        el.scrollIntoView({ behavior: "smooth", block: "center" });
      } else {
        setTargetRect(null);
      }
    } else {
      setTargetRect(null);
    }
  }, [step.selector, currentStep]);

  // Position popup relative to target
  const getPopupStyle = (): React.CSSProperties => {
    if (!targetRect) {
      // Center in viewport
      return {
        top: "50%",
        left: "50%",
        transform: "translate(-50%, -50%)",
      };
    }

    const viewportH = window.innerHeight;
    const popupH = 200;

    // Show below if there's room, otherwise above
    if (targetRect.bottom + popupH + 16 < viewportH) {
      return {
        top: targetRect.bottom + 12,
        left: Math.max(16, Math.min(targetRect.left, window.innerWidth - 380)),
      };
    }
    return {
      top: targetRect.top - popupH - 12,
      left: Math.max(16, Math.min(targetRect.left, window.innerWidth - 380)),
    };
  };

  return (
    <div className="fixed inset-0 z-[100]">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/50 animate-spotlight" onClick={onDone} />

      {/* Spotlight cutout */}
      {targetRect && (
        <div
          className="absolute bg-transparent rounded-xl ring-4 ring-white/30 z-[101]"
          style={{
            top: targetRect.top - 6,
            left: targetRect.left - 6,
            width: targetRect.width + 12,
            height: targetRect.height + 12,
            boxShadow: "0 0 0 9999px rgba(0,0,0,0.5)",
          }}
        />
      )}

      {/* Popup */}
      <div
        ref={popupRef}
        className="absolute z-[102] w-[360px] animate-scale-in"
        style={getPopupStyle()}
      >
        <div className="rounded-2xl bg-white shadow-2xl border border-gray-200 overflow-hidden">
          {/* Progress bar */}
          <div className="h-1 bg-gray-100">
            <div
              className="h-1 bg-gray-900 transition-all duration-300"
              style={{ width: `${((currentStep + 1) / steps.length) * 100}%` }}
            />
          </div>

          <div className="p-5">
            {/* Step counter */}
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs font-medium text-gray-400 uppercase tracking-wider">
                Step {currentStep + 1} of {steps.length}
              </span>
              <button
                onClick={onDone}
                className="text-gray-400 hover:text-gray-600 transition-colors"
                aria-label="Close"
              >
                <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <h3 className="text-base font-semibold text-gray-900 mb-2">{step.title}</h3>
            <p className="text-sm text-gray-600 leading-relaxed mb-5">{step.body}</p>

            {/* Navigation */}
            <div className="flex items-center justify-between">
              <button
                onClick={onPrev}
                disabled={isFirst}
                className="text-sm text-gray-500 hover:text-gray-700 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
              >
                ← Back
              </button>
              <button
                onClick={isLast ? onDone : onNext}
                className="btn-primary !py-2 !px-4 !text-sm"
              >
                {isLast ? "Done ✓" : "Next →"}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export function useTutorial(steps: TutorialStep[]): [ReactNode, () => void] {
  const [active, setActive] = useState(false);
  const [currentStep, setCurrentStep] = useState(0);

  const start = useCallback(() => {
    setCurrentStep(0);
    setActive(true);
  }, []);

  const handleNext = useCallback(() => {
    setCurrentStep((s) => Math.min(s + 1, steps.length - 1));
  }, [steps.length]);

  const handlePrev = useCallback(() => {
    setCurrentStep((s) => Math.max(s - 1, 0));
  }, []);

  const handleDone = useCallback(() => {
    setActive(false);
  }, []);

  const node = active ? (
    <TutorialOverlay
      steps={steps}
      currentStep={currentStep}
      onNext={handleNext}
      onPrev={handlePrev}
      onDone={handleDone}
    />
  ) : null;

  return [node, start];
}
