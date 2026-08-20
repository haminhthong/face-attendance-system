from __future__ import annotations

import os
import re
from pathlib import Path
from zoneinfo import ZoneInfo

APP_TITLE = "Hệ thống Điểm danh Sinh viên bằng Khuôn mặt"
VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = Path(
    os.getenv("FACE_ATTENDANCE_DATA_DIR", str(BASE_DIR / "face_attendance_data"))
).expanduser().resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "face_attendance.db"


def _env_float(name: str, default: float, minimum: float, maximum: float) -> float:
    raw = os.getenv(name, str(default))
    try:
        value = float(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} phải là số, nhận được {raw!r}") from exc
    if not minimum <= value <= maximum:
        raise RuntimeError(f"{name} phải nằm trong khoảng {minimum}-{maximum}")
    return value


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} phải là số nguyên, nhận được {raw!r}") from exc
    if not minimum <= value <= maximum:
        raise RuntimeError(f"{name} phải nằm trong khoảng {minimum}-{maximum}")
    return value


FACE_TOLERANCE = _env_float("FACE_TOLERANCE", 0.50, 0.10, 1.00)
MIN_IDENTITY_MARGIN = _env_float("MIN_IDENTITY_MARGIN", 0.05, 0.00, 1.00)
PROCESS_EVERY_N_FRAMES = _env_int("PROCESS_EVERY_N_FRAMES", 3, 1, 60)
CONFIRMATION_FRAMES = _env_int("CONFIRMATION_FRAMES", 3, 1, 60)
MAX_UPLOAD_BYTES = 8 * 1024 * 1024
MIN_FACE_SIZE_PX = 100
MIN_BLUR_SCORE = 45.0
MIN_BRIGHTNESS = 40.0
MAX_BRIGHTNESS = 220.0
BLINK_EAR_CLOSED = 0.19
BLINK_EAR_OPEN = 0.23
BLINK_VERIFICATION_SECONDS = 10.0
ATTEMPT_COOLDOWN_SECONDS = 8.0
PIN_ITERATIONS = 240_000

STUDENT_CODE_PATTERN = re.compile(r"^[A-Za-z0-9_-]{3,30}$")
COURSE_CODE_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{2,30}$")
