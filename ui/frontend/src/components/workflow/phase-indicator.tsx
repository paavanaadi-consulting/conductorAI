"use client";

import { cn } from "@/lib/utils";
import { CheckCircle2, Circle, Loader2, XCircle } from "lucide-react";

const PHASES = ["DEVELOPMENT", "DEVOPS", "MONITORING"];

interface Props {
  currentPhase: string;
  status: string;
}

export function PhaseIndicator({ currentPhase, status }: Props) {
  const currentIdx = PHASES.indexOf(currentPhase.toUpperCase());

  return (
    <div className="flex items-center gap-2">
      {PHASES.map((phase, idx) => {
        const isCurrent = idx === currentIdx;
        const isCompleted = idx < currentIdx || status === "completed";
        const isFailed = isCurrent && status === "failed";

        return (
          <div key={phase} className="flex items-center gap-2">
            {idx > 0 && (
              <div
                className={cn(
                  "h-0.5 w-8",
                  isCompleted ? "bg-green-500" : "bg-muted"
                )}
              />
            )}
            <div className="flex items-center gap-1.5">
              {isCompleted && !isCurrent ? (
                <CheckCircle2 className="h-5 w-5 text-green-500" />
              ) : isFailed ? (
                <XCircle className="h-5 w-5 text-red-500" />
              ) : isCurrent ? (
                <Loader2 className="h-5 w-5 text-blue-500 animate-spin" />
              ) : (
                <Circle className="h-5 w-5 text-muted-foreground" />
              )}
              <span
                className={cn(
                  "text-xs font-medium",
                  isCurrent
                    ? "text-blue-600"
                    : isCompleted
                    ? "text-green-600"
                    : "text-muted-foreground"
                )}
              >
                {phase}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
