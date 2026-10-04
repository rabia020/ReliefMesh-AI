"""Phase 20: /copilot endpoint."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from agents import copilot

router = APIRouter(prefix="/copilot", tags=["copilot"])


class AskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=500)
    use_llm: bool = True
    use_osrm: bool = True


@router.post("/ask")
def ask(body: AskRequest):
    try:
        return copilot.ask(body.question, use_llm=body.use_llm, use_osrm=body.use_osrm)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))