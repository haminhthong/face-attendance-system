from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
from datetime import date, datetime, time as dt_time, timezone

from .config import COURSE_CODE_PATTERN, PIN_ITERATIONS, STUDENT_CODE_PATTERN, VN_TZ


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_iso(value: datetime | None = None) -> str:
    value = value or utc_now()
    return value.astimezone(timezone.utc).isoformat(timespec="seconds")


def local_datetime(day: date, clock: dt_time) -> datetime:
    return datetime.combine(day, clock).replace(tzinfo=VN_TZ)


def display_datetime(value: str | None) -> str:
    if not value:
        return ""
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(VN_TZ).strftime("%d/%m/%Y %H:%M:%S")
    except ValueError:
        return value


def normalize_student_code(value: str) -> str:
    code = value.strip().upper()
    if not STUDENT_CODE_PATTERN.fullmatch(code):
        raise ValueError(
            "Mã sinh viên phải dài 3-30 ký tự và chỉ gồm chữ, số, '_' hoặc '-'."
        )
    return code


def normalize_course_code(value: str) -> str:
    code = value.strip().upper()
    if not COURSE_CODE_PATTERN.fullmatch(code):
        raise ValueError(
            "Mã môn học phải dài 2-30 ký tự và chỉ gồm chữ, số, '_', '-' hoặc '.'."
        )
    return code


def normalize_person_name(value: str) -> str:
    name = " ".join(value.strip().split())
    if not (2 <= len(name) <= 100):
        raise ValueError("Họ tên phải dài từ 2 đến 100 ký tự.")
    allowed_punctuation = {" ", "-", "'", "."}
    if not all(ch.isalpha() or ch in allowed_punctuation for ch in name):
        raise ValueError("Họ tên chứa ký tự không hợp lệ.")
    return name


def make_pin_hash(pin: str) -> str:
    if not re.fullmatch(r"\d{6,12}", pin):
        raise ValueError("PIN phải gồm từ 6 đến 12 chữ số.")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", pin.encode("utf-8"), salt, PIN_ITERATIONS
    )
    return "pbkdf2_sha256${}${}${}".format(
        PIN_ITERATIONS,
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(digest).decode("ascii"),
    )


def verify_pin(pin: str, stored_value: str) -> bool:
    try:
        algorithm, iterations, encoded_salt, encoded_digest = stored_value.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iteration_count = int(iterations)
        if not 100_000 <= iteration_count <= 1_000_000:
            return False
        salt = base64.b64decode(encoded_salt)
        expected = base64.b64decode(encoded_digest)
        if len(salt) != 16 or len(expected) != 32:
            return False
        actual = hashlib.pbkdf2_hmac(
            "sha256", pin.encode("utf-8"), salt, iteration_count
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False
