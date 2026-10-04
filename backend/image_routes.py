"""Phase 18: /images endpoints."""
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from agents import image_agent as ia
from llm.client import LLMError

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
STATUS_FOR_KIND = {"not_found": 404, "invalid": 422}


def build_image_router(get_db) -> APIRouter:
    router = APIRouter(prefix="/images", tags=["images"])

    @router.post("/analyze")
    def analyze(file: UploadFile = File(...), report_id: str | None = Form(None),
                force: bool = Form(False), conn=Depends(get_db)):
        data = file.file.read(MAX_UPLOAD_BYTES + 1)
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="Image is larger than 10 MB.")
        try:
            return ia.analyze_and_store(
                conn, data, file.filename or "upload",
                report_id=(report_id or None), force=force,
            )
        except ia.ImageError as error:
            raise HTTPException(status_code=STATUS_FOR_KIND.get(error.kind, 400),
                                detail=str(error))
        except LLMError as error:
            raise HTTPException(status_code=502, detail=str(error))

    @router.get("/report/{report_id}")
    def for_report(report_id: str, conn=Depends(get_db)):
        return {"report_id": report_id, "analyses": ia.list_report_analyses(conn, report_id)}

    return router