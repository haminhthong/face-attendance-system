"""Module định nghĩa các Exception nghiệp vụ (Domain Exceptions) cho hệ thống điểm danh."""

from __future__ import annotations


class AttendanceError(Exception):
    """Exception gốc cho tất cả các lỗi nghiệp vụ trong hệ thống điểm danh."""


class StudentNotInRosterError(AttendanceError):
    """Sinh viên không thuộc danh sách lớp/môn của buổi học."""


class DuplicateAttendanceError(AttendanceError):
    """Sinh viên đã được điểm danh trong buổi học này."""


class SessionClosedError(AttendanceError):
    """Buổi học chưa mở hoặc đã kết thúc thời gian điểm danh."""


class BiometricConsentMissingError(AttendanceError):
    """Sinh viên chưa đồng ý đăng ký và sử dụng dữ liệu sinh trắc học."""


class InvalidImageError(AttendanceError):
    """File tải lên không hợp lệ hoặc không phải định dạng ảnh."""


class FaceNotFoundError(AttendanceError):
    """Không tìm thấy khuôn mặt trong hình ảnh."""


class MultipleFacesError(AttendanceError):
    """Phát hiện nhiều khuôn mặt trong hình ảnh đơn."""


class UnknownFaceError(AttendanceError):
    """Khuôn mặt không khớp với sinh viên nào trong cơ sở dữ liệu."""
