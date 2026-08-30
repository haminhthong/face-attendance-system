"""Module RESTful API sử dụng FastAPI cho hệ thống điểm danh khuôn mặt.

Cung cấp các endpoint tích hợp dịch vụ:
- Health check kiểm tra trạng thái hoạt động (/health).
- Danh sách buổi học (/sessions).
- Báo cáo kết quả điểm danh (/sessions/{session_id}/attendance).
- Ghi nhận điểm danh (/attendance).

Bảo mật bằng Header X-API-Key với cơ chế so sánh hằng số thời gian chống Timing Attack.
"""

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
    """Khởi tạo cơ sở dữ liệu và dọn dẹp vector khuôn mặt quá hạn khi ứng dụng khởi chạy."""
    init_database()
    purge_expired_biometrics()
    yield


app = FastAPI(
    title="Face Attendance API",
    version="1.1.0",
    description="RESTful API nghiệp vụ cho hệ thống điểm danh sinh viên bằng khuôn mặt.",
    lifespan=lifespan,
)


class YeuCauDiemDanh(BaseModel):
    """Schema Pydantic đại diện cho yêu cầu ghi nhận điểm danh từ client."""

    session_id: int = Field(gt=0, description="ID của buổi học đang mở điểm danh")
    student_id: int = Field(gt=0, description="ID sinh viên được nhận diện")
    recognition_distance: float = Field(
        ge=0, le=1, description="Khoảng cách khuôn mặt Euclidean (<= FACE_TOLERANCE)"
    )


def xac_thuc_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Dependency xác thực API Key từ Header 'X-API-Key'.

    Sử dụng hmac.compare_digest để chống tấn công Timing Attack.

    Raises:
        HTTPException(503): Nếu chưa cấu hình biến môi trường FACE_ATTENDANCE_API_KEY.
        HTTPException(401): Nếu API key không khớp hoặc bị thiếu.
    """
    if not API_KEY:
        raise HTTPException(
            status_code=503,
            detail="API chưa được bật vì chưa cấu hình khóa truy cập (FACE_ATTENDANCE_API_KEY).",
        )
    if x_api_key is None or not hmac.compare_digest(x_api_key, API_KEY):
        raise HTTPException(status_code=401, detail="Khóa API không hợp lệ.")


@app.get("/health", summary="Kiểm tra sức khỏe dịch vụ API")
def health() -> dict[str, str]:
    """Endpoint công khai dùng cho Load Balancer hoặc Docker health check."""
    return {"status": "ok"}


@app.get("/sessions", dependencies=[Depends(xac_thuc_api_key)], summary="Lấy danh sách các buổi học")
def danh_sach_buoi_hoc() -> list[dict[str, object]]:
    """Trả về danh sách tất cả các buổi học kèm thông tin môn học và trạng thái."""
    return [dict(row) for row in list_sessions()]


@app.get(
    "/sessions/{session_id}/attendance",
    dependencies=[Depends(xac_thuc_api_key)],
    summary="Trích xuất báo cáo điểm danh của một buổi học",
)
def bao_cao_buoi_hoc(session_id: int) -> list[dict[str, object]]:
    """Trả về danh sách sinh viên kèm trạng thái 'Có mặt', 'Đi trễ', 'Vắng' và khoảng cách nhận diện."""
    report = attendance_report(session_id)
    return report.astype(object).where(report.notna(), None).to_dict(orient="records")


@app.post("/attendance", summary="Ghi nhận kết quả điểm danh cho sinh viên")
def attendance(
    request: YeuCauDiemDanh,
    _: None = Depends(xac_thuc_api_key),
) -> dict[str, str]:
    """Thực hiện transaction ghi nhận điểm danh có kiểm tra thời gian và giới hạn 1 lần/buổi."""
    result, message = mark_attendance(
        request.session_id, request.student_id, request.recognition_distance
    )
    if result in {"error", "rejected"}:
        raise HTTPException(status_code=422, detail=message)
    if result in {"closed", "inactive", "outside"}:
        raise HTTPException(status_code=409, detail=message)
    return {"result": result, "message": message}

