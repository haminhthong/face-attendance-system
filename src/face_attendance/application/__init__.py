"""Application layer package cho hệ thống điểm danh."""

from .attendance_service import process_attendance_record
from .enrollment_service import process_student_enrollment

__all__ = [
    "process_attendance_record",
    "process_student_enrollment",
]
