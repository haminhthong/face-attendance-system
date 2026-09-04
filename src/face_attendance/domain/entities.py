"""Module định nghĩa các đối tượng dữ liệu (Entities / Schemas) domain cho hệ thống điểm danh."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .enums import (
    AttendanceDecision,
    AttendanceStatus,
    ConfidenceLevel,
    RejectionReason,
    get_confidence_level,
)


@dataclass(frozen=True)
class AttendanceResult:
    """Cấu trúc kết quả điểm danh chuẩn hóa của hệ thống.

    Attributes:
        student_id: Mã sinh viên (hoặc ID sinh viên dạng chuỗi/số).
        status: Trạng thái điểm danh ('present', 'late', 'absent').
        distance: Khoảng cách Euclidean L2 giữa vector nhận diện và mẫu (None nếu không khớp).
        confidence_level: Mức độ tin cậy định tính ('high', 'medium', 'low').
        liveness_passed: Kết quả kiểm tra tương tác/chớp mắt.
        recognized_at: Thời điểm nhận diện theo chuẩn ISO 8601 UTC/VN.
        decision: Quyết định điểm danh ('accepted' hoặc 'rejected').
        rejection_reason: Lý do từ chối nếu decision == 'rejected'.
    """

    student_id: str | None
    status: AttendanceStatus | str
    distance: float | None
    confidence_level: ConfidenceLevel | str
    liveness_passed: bool
    recognized_at: str
    decision: AttendanceDecision | str
    rejection_reason: RejectionReason | str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Chuyển đổi sang dict định dạng JSON thân thiện."""
        data = asdict(self)
        if isinstance(self.status, Enum_or_str):
            data["status"] = str(self.status.value if hasattr(self.status, "value") else self.status)
        if isinstance(self.decision, Enum_or_str):
            data["decision"] = str(self.decision.value if hasattr(self.decision, "value") else self.decision)
        if isinstance(self.confidence_level, Enum_or_str):
            data["confidence_level"] = str(
                self.confidence_level.value if hasattr(self.confidence_level, "value") else self.confidence_level
            )
        if self.rejection_reason is not None and hasattr(self.rejection_reason, "value"):
            data["rejection_reason"] = self.rejection_reason.value
        return data


Enum_or_str = (AttendanceStatus, AttendanceDecision, ConfidenceLevel, RejectionReason)


def build_accepted_result(
    student_id: str,
    status: AttendanceStatus | str,
    distance: float,
    liveness_passed: bool,
    recognized_at: str,
    tolerance: float = 0.50,
) -> AttendanceResult:
    """Tạo kết quả chấp nhận điểm danh chuẩn hóa.

    Args:
        student_id: Mã sinh viên.
        status: Trạng thái điểm danh ('present' hoặc 'late').
        distance: Khoảng cách Euclidean L2.
        liveness_passed: Trạng thái liveness.
        recognized_at: Chuỗi ISO 8601 thời gian nhận diện.
        tolerance: Ngưỡng tối đa để phân loại confidence level.

    Returns:
        AttendanceResult: Đối tượng kết quả điểm danh được chấp nhận.
    """
    conf = get_confidence_level(distance, tolerance)
    return AttendanceResult(
        student_id=student_id,
        status=status if isinstance(status, AttendanceStatus) else AttendanceStatus(status),
        distance=round(distance, 4),
        confidence_level=conf,
        liveness_passed=liveness_passed,
        recognized_at=recognized_at,
        decision=AttendanceDecision.ACCEPTED,
        rejection_reason=None,
    )


def build_rejected_result(
    reason: RejectionReason | str,
    recognized_at: str,
    student_id: str | None = None,
    distance: float | None = None,
    liveness_passed: bool = False,
    tolerance: float = 0.50,
) -> AttendanceResult:
    """Tạo kết quả từ chối điểm danh chuẩn hóa với lý do rõ ràng.

    Args:
        reason: Lý do từ chối.
        recognized_at: Chuỗi ISO 8601 thời gian.
        student_id: Mã sinh viên (nếu xác định được nhưng bị từ chối).
        distance: Khoảng cách Euclidean L2 nếu có.
        liveness_passed: Kết quả liveness.
        tolerance: Ngưỡng khoảng cách.

    Returns:
        AttendanceResult: Đối tượng kết quả từ chối.
    """
    reason_enum = reason if isinstance(reason, RejectionReason) else RejectionReason(reason)
    conf = get_confidence_level(distance, tolerance) if distance is not None else ConfidenceLevel.LOW
    return AttendanceResult(
        student_id=student_id,
        status=AttendanceStatus.ABSENT,
        distance=round(distance, 4) if distance is not None else None,
        confidence_level=conf,
        liveness_passed=liveness_passed,
        recognized_at=recognized_at,
        decision=AttendanceDecision.REJECTED,
        rejection_reason=reason_enum,
    )
