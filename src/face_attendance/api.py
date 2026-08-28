from __future__ import annotations

from contextlib import asynccontextmanager
import hmac

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from .config import API_KEY
from .database import attendance_report, init_database, list_sessions, mark_attendance


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_database()
    yield


app = FastAPI(
    title="Face Attendance API",
    version="1.1.0",
    description="API nghiệp vụ cho bản demo điểm danh khuôn mặt.",
    lifespan=lifespan,
)


class YeuCauDiemDanh(BaseModel):
    session_id: int = Field(gt=0)
    student_id: int = Field(gt=0)
    recognition_distance: float = Field(ge=0, le=1)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/sessions")
def sessions() -> list[dict[str, object]]:
    return [dict(row) for row in list_sessions()]


@app.get("/sessions/{session_id}/attendance")
def session_attendance(session_id: int) -> list[dict[str, object]]:
    return attendance_report(session_id).where(lambda value: value.notna(), None).to_dict(
        orient="records"
    )


@app.post("/attendance")
def attendance(
    request: YeuCauDiemDanh,
    x_api_key: str | None = Header(default=None),
) -> dict[str, str]:
    if not API_KEY:
        raise HTTPException(
            status_code=503,
            detail="Endpoint ghi chưa được bật vì chưa cấu hình API key.",
        )
    if x_api_key is None or not hmac.compare_digest(x_api_key, API_KEY):
        raise HTTPException(status_code=401, detail="API key không hợp lệ.")
    result, message = mark_attendance(
        request.session_id, request.student_id, request.recognition_distance
    )
    if result in {"error", "rejected"}:
        raise HTTPException(status_code=422, detail=message)
    if result in {"closed", "inactive", "outside"}:
        raise HTTPException(status_code=409, detail=message)
    return {"result": result, "message": message}
