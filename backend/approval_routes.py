"""Phase 17: /approvals endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from database import approvals as ap

STATUS_FOR_KIND = {"not_found": 404, "conflict": 409, "invalid": 422}


class DecisionRequest(BaseModel):
    decided_by: str
    note: str | None = None


def build_approval_router(get_db) -> APIRouter:
    router = APIRouter(prefix="/approvals", tags=["approvals"])

    def run(func, *args):
        try:
            return func(*args)
        except ap.ApprovalError as error:
            raise HTTPException(status_code=STATUS_FOR_KIND.get(error.kind, 400),
                                detail=str(error))

    @router.get("/pending")
    def pending(conn=Depends(get_db)):
        actions = ap.list_pending(conn)
        return {"count": len(actions), "actions": actions}

    @router.get("/history")
    def history(limit: int = 20, conn=Depends(get_db)):
        return {"actions": ap.list_history(conn, limit)}

    @router.get("/{action_id}")
    def one(action_id: int, conn=Depends(get_db)):
        return run(ap.get_action, conn, action_id)

    @router.post("/{action_id}/approve")
    def approve(action_id: int, body: DecisionRequest, conn=Depends(get_db)):
        return run(ap.approve_action, conn, action_id, body.decided_by, body.note)

    @router.post("/{action_id}/reject")
    def reject(action_id: int, body: DecisionRequest, conn=Depends(get_db)):
        return run(ap.reject_action, conn, action_id, body.decided_by, body.note)

    @router.post("/{action_id}/request-info")
    def request_more_info(action_id: int, body: DecisionRequest, conn=Depends(get_db)):
        return run(ap.request_info, conn, action_id, body.decided_by, body.note)

    return router