"""
ConductorAI UI — WebSocket Router for workflow progress
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


@router.websocket("/workflow/{workflow_id}")
async def workflow_progress(websocket: WebSocket, workflow_id: str):
    await websocket.accept()
    conductor_svc = websocket.app.state.conductor

    try:
        while True:
            try:
                state_mgr = conductor_svc.conductor.state_manager
                state = await state_mgr.get_workflow_state(workflow_id)
            except Exception:
                state = None

            if state:
                payload = {
                    "workflow_id": workflow_id,
                    "status": state.status.value,
                    "current_phase": (
                        state.current_phase.value
                        if hasattr(state, "current_phase") and state.current_phase
                        else "unknown"
                    ),
                    "completed_tasks": state.completed_task_count,
                    "failed_tasks": state.failed_task_count,
                    "feedback_count": getattr(state, "feedback_count", 0),
                    "phase_history": getattr(state, "phase_history", []),
                }
                await websocket.send_json(payload)

                if state.status.value in ("completed", "failed"):
                    break
            else:
                await websocket.send_json(
                    {"workflow_id": workflow_id, "status": "pending"}
                )

            await asyncio.sleep(2)
    except WebSocketDisconnect:
        pass
    except Exception:
        try:
            await websocket.close()
        except Exception:
            pass
