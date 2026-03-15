"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Play } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ComponentSelector } from "@/components/project/component-selector";
import { WorkflowProgressPanel } from "@/components/workflow/workflow-progress";
import { projectsApi, workflowsApi } from "@/lib/api";
import type { ComponentSelection } from "@/lib/types";

const STATUS_COLORS: Record<string, string> = {
  pending: "bg-gray-100 text-gray-800",
  in_progress: "bg-blue-100 text-blue-800",
  completed: "bg-green-100 text-green-800",
  failed: "bg-red-100 text-red-800",
};

export default function ProjectDetailPage() {
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const [components, setComponents] = useState<ComponentSelection[]>([
    "code",
    "unit_test",
  ]);
  const [activeWorkflowId, setActiveWorkflowId] = useState<string | null>(null);

  const { data: project, isLoading } = useQuery({
    queryKey: ["project", id],
    queryFn: () => projectsApi.get(id),
  });

  const { data: runs } = useQuery({
    queryKey: ["workflow-runs", id],
    queryFn: () => workflowsApi.listByProject(id),
    refetchInterval: activeWorkflowId ? 5000 : false,
  });

  const runMutation = useMutation({
    mutationFn: () =>
      projectsApi.run(id, { selected_components: components }),
    onSuccess: (run) => {
      toast.success("Workflow started");
      setActiveWorkflowId(run.workflow_id || null);
      queryClient.invalidateQueries({ queryKey: ["workflow-runs", id] });
    },
    onError: (err: any) => toast.error(err.message),
  });

  if (isLoading || !project) {
    return <p className="text-muted-foreground">Loading...</p>;
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold">{project.name}</h1>
        <p className="text-muted-foreground">{project.github_repo}</p>
      </div>

      {/* Run workflow */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Run Workflow</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <ComponentSelector value={components} onChange={setComponents} />
          <Button
            onClick={() => runMutation.mutate()}
            disabled={runMutation.isPending || components.length === 0}
          >
            <Play className="h-4 w-4 mr-2" />
            {runMutation.isPending ? "Starting..." : "Run Workflow"}
          </Button>
        </CardContent>
      </Card>

      {/* Active workflow progress */}
      <WorkflowProgressPanel workflowId={activeWorkflowId} />

      {/* Past runs */}
      {runs && runs.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Workflow History</CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Status</TableHead>
                  <TableHead>Components</TableHead>
                  <TableHead>Started</TableHead>
                  <TableHead>Completed</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {runs.map((run) => (
                  <TableRow key={run.id}>
                    <TableCell>
                      <Badge
                        variant="outline"
                        className={STATUS_COLORS[run.status] || ""}
                      >
                        {run.status}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <div className="flex gap-1 flex-wrap">
                        {run.selected_components.map((c) => (
                          <Badge key={c} variant="outline" className="text-xs">
                            {c}
                          </Badge>
                        ))}
                      </div>
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {new Date(run.created_at).toLocaleString()}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {run.completed_at
                        ? new Date(run.completed_at).toLocaleString()
                        : "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
