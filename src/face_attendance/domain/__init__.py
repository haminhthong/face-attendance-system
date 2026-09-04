"""Domain package cho hệ thống điểm danh khuôn mặt."""

from .entities import AttendanceResult, build_accepted_result, build_rejected_result
from .enums import AttendanceDecision, AttendanceStatus, ConfidenceLevel, RejectionReason
from .exceptions import (
    AttendanceError,
    BiometricConsentMissingError,
    DuplicateAttendanceError,
    FaceNotFoundError,
    InvalidImageError,
    MultipleFacesError,
    SessionClosedError,
    StudentNotInRosterError,
    UnknownFaceError,
)

__all__ = [
    "AttendanceResult",
    "build_accepted_result",
    "build_rejected_result",
    "AttendanceStatus",
    "AttendanceDecision",
    "RejectionReason",
    "ConfidenceLevel",
    "AttendanceError",
    "StudentNotInRosterError",
    "DuplicateAttendanceError",
    "SessionClosedError",
    "BiometricConsentMissingError",
    "InvalidImageError",
    "FaceNotFoundError",
    "MultipleFacesError",
    "UnknownFaceError",
]
