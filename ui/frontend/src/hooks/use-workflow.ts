"use client";

import { useEffect, useRef, useState } from "react";
import type { WorkflowProgress } from "@/lib/types";

const WS_BASE = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000/api/ws";

export function useWorkflowProgress(workflowId: string | null) {
  const [progress, setProgress] = useState<WorkflowProgress | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!workflowId) return;

    const ws = new WebSocket(`${WS_BASE}/workflow/${workflowId}`);
    wsRef.current = ws;

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data) as WorkflowProgress;
      setProgress(data);
      if (data.status === "completed" || data.status === "failed") {
        ws.close();
      }
    };

    ws.onerror = () => ws.close();

    return () => {
      ws.close();
    };
  }, [workflowId]);

  return progress;
}
