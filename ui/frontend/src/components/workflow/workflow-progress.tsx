"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { PhaseIndicator } from "./phase-indicator";
import { useWorkflowProgress } from "@/hooks/use-workflow";

const STATUS_COLORS: Record<string, string> = {
  pending: "bg-gray-100 text-gray-800",
  in_progress: "bg-blue-100 text-blue-800",
  completed: "bg-green-100 text-green-800",
  failed: "bg-red-100 text-red-800",
};

interface Props {
  workflowId: string | null;
}

export function WorkflowProgressPanel({ workflowId }: Props) {
  const progress = useWorkflowProgress(workflowId);

  if (!workflowId || !progress) {
    return null;
  }

  const total = progress.completed_tasks + progress.failed_tasks;
  const pct = total > 0 ? Math.round((progress.completed_tasks / Math.max(total, 1)) * 100) : 0;

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">Workflow Progress</CardTitle>
          <Badge
            variant="outline"
            className={STATUS_COLORS[progress.status] || ""}
          >
            {progress.status}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <PhaseIndicator
          currentPhase={progress.current_phase}
          status={progress.status}
        />
        <div className="space-y-1">
          <div className="flex justify-between text-xs text-muted-foreground">
            <span>
              {progress.completed_tasks} completed, {progress.failed_tasks}{" "}
              failed
            </span>
            {progress.feedback_count > 0 && (
              <span>{progress.feedback_count} feedback loops</span>
            )}
          </div>
          <Progress value={pct} className="h-2" />
        </div>
      </CardContent>
    </Card>
  );
}
