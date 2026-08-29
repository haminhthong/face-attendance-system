from __future__ import annotations

from contextlib import asynccontextmanager
import hmac

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from .config import API_KEY
from .database import (
    attendance_report,
    init_database,
    list_sessions,
    mark_attendance,
    purge_expired_biometrics,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_database()
    purge_expired_biometrics()
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


def xac_thuc_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Bảo vệ dữ liệu điểm danh và thông tin sinh viên bằng khóa API."""
    if not API_KEY:
        raise HTTPException(
            status_code=503,
            detail="API chưa được bật vì chưa cấu hình khóa truy cập.",
        )
    if x_api_key is None or not hmac.compare_digest(x_api_key, API_KEY):
        raise HTTPException(status_code=401, detail="Khóa API không hợp lệ.")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/sessions", dependencies=[Depends(xac_thuc_api_key)])
def danh_sach_buoi_hoc() -> list[dict[str, object]]:
    return [dict(row) for row in list_sessions()]


@app.get(
    "/sessions/{session_id}/attendance",
    dependencies=[Depends(xac_thuc_api_key)],
)
def bao_cao_buoi_hoc(session_id: int) -> list[dict[str, object]]:
    report = attendance_report(session_id)
    return report.astype(object).where(report.notna(), None).to_dict(orient="records")


@app.post("/attendance")
def attendance(
    request: YeuCauDiemDanh,
    _: None = Depends(xac_thuc_api_key),
) -> dict[str, str]:
    result, message = mark_attendance(
        request.session_id, request.student_id, request.recognition_distance
    )
    if result in {"error", "rejected"}:
        raise HTTPException(status_code=422, detail=message)
    if result in {"closed", "inactive", "outside"}:
        raise HTTPException(status_code=409, detail=message)
    return {"result": result, "message": message}
