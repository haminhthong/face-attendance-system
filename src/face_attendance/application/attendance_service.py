"""Service xử lý nghiệp vụ điểm danh sinh viên (Attendance Application Service)."""

from __future__ import annotations

from ..database import mark_attendance
from ..domain import (
    AttendanceResult,
    DuplicateAttendanceError,
    RejectionReason,
    SessionClosedError,
    StudentNotInRosterError,
    build_accepted_result,
    build_rejected_result,
)
from ..utils import utc_iso


def process_attendance_record(
    session_id: int,
    student_id: int,
    distance: float,
    tolerance: float = 0.50,
) -> AttendanceResult:
    """Xử lý yêu cầu điểm danh cho sinh viên và trả về kết quả cấu trúc chuẩn hóa.

    Args:
        session_id: ID buổi học.
        student_id: ID sinh viên trong DB.
        distance: Khoảng cách Euclidean L2 nhận diện được.
        tolerance: Ngưỡng khoảng cách tối đa chấp nhận.

    Returns:
        AttendanceResult: Đối tượng kết quả điểm danh chuẩn hóa.

    Raises:
        DuplicateAttendanceError: Nếu sinh viên đã được điểm danh trước đó.
        SessionClosedError: Nếu buổi học đã đóng hoặc ngoài giờ.
        StudentNotInRosterError: Nếu sinh viên không thuộc danh sách lớp của buổi học.
    """
    now_str = utc_iso()
    result_code, message = mark_attendance(session_id, student_id, distance)

    if result_code == "created":
        return build_accepted_result(
            student_id=str(student_id),
            status="present",
            distance=distance,
            liveness_passed=True,
            recognized_at=now_str,
            tolerance=tolerance,
        )
    elif result_code == "already":
        raise DuplicateAttendanceError(message)
    elif result_code in {"closed", "outside"}:
        raise SessionClosedError(message)
    elif result_code in {"not_in_roster", "inactive"}:
        raise StudentNotInRosterError(message)
    else:
        return build_rejected_result(
            reason=RejectionReason.UNKNOWN_FACE,
            recognized_at=now_str,
            student_id=str(student_id),
            distance=distance,
            tolerance=tolerance,
        )
