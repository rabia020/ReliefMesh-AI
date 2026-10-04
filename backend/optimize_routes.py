"""Phase 19: /optimize endpoints (now with an optional budget)."""
from fastapi import APIRouter, Depends

from agents import optimizer


def _clean_budget(budget):
    return budget if budget and budget > 0 else None   # 0 or missing = no limit


def build_optimize_router(get_db) -> APIRouter:
    router = APIRouter(prefix="/optimize", tags=["optimize"])

    @router.get("/plan")
    def plan(budget: float | None = None, conn=Depends(get_db)):
        """Read-only. Computes the recommended allocation. Changes nothing."""
        return optimizer.optimize(conn, budget=_clean_budget(budget))

    @router.post("/propose")
    def propose(budget: float | None = None, conn=Depends(get_db)):
        """Creates PROPOSED actions from the current plan. Dispatches nothing;
        a human must approve each one in the Approval Center."""
        return optimizer.optimize_and_propose(conn, budget=_clean_budget(budget))

    return router