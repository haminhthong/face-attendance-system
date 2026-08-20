from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from typing import Any, Iterable

import numpy as np
import pandas as pd

from .config import DB_PATH, FACE_TOLERANCE
from .utils import (
    display_datetime,
    normalize_course_code,
    normalize_person_name,
    normalize_student_code,
    utc_iso,
    utc_now,
)


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH, timeout=15, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 15000")
    return connection

def init_database() -> None:
    schema = """
    CREATE TABLE IF NOT EXISTS app_settings (
        setting_key TEXT PRIMARY KEY,
        setting_value TEXT NOT NULL,
        updated_at_utc TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS students (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_code TEXT NOT NULL UNIQUE,
        full_name TEXT NOT NULL,
        class_name TEXT NOT NULL,
        active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
        consent_at_utc TEXT NOT NULL,
        created_at_utc TEXT NOT NULL,
        updated_at_utc TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS face_embeddings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL,
        embedding BLOB NOT NULL,
        image_sha256 TEXT NOT NULL,
        blur_score REAL NOT NULL,
        brightness REAL NOT NULL,
        face_width INTEGER NOT NULL,
        face_height INTEGER NOT NULL,
        created_at_utc TEXT NOT NULL,
        UNIQUE (student_id, image_sha256),
        FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS courses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        course_code TEXT NOT NULL UNIQUE,
        course_name TEXT NOT NULL,
        lecturer TEXT NOT NULL,
        created_at_utc TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS course_enrollments (
        course_id INTEGER NOT NULL,
        student_id INTEGER NOT NULL,
        enrolled_at_utc TEXT NOT NULL,
        PRIMARY KEY (course_id, student_id),
        FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
        FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS attendance_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        course_id INTEGER NOT NULL,
        session_name TEXT NOT NULL,
        start_at_utc TEXT NOT NULL,
        end_at_utc TEXT NOT NULL,
        late_after_minutes INTEGER NOT NULL DEFAULT 15,
        status TEXT NOT NULL DEFAULT 'scheduled'
            CHECK (status IN ('scheduled', 'open', 'closed')),
        created_at_utc TEXT NOT NULL,
        FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE RESTRICT
    );

    CREATE TABLE IF NOT EXISTS session_enrollments (
        session_id INTEGER NOT NULL,
        student_id INTEGER NOT NULL,
        enrolled_at_utc TEXT NOT NULL,
        PRIMARY KEY (session_id, student_id),
        FOREIGN KEY (session_id) REFERENCES attendance_sessions(id) ON DELETE CASCADE,
        FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE RESTRICT
    );

    CREATE TABLE IF NOT EXISTS attendance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER NOT NULL,
        student_id INTEGER NOT NULL,
        check_in_at_utc TEXT NOT NULL,
        attendance_status TEXT NOT NULL CHECK (attendance_status IN ('present', 'late')),
        recognition_distance REAL NOT NULL,
        threshold_used REAL NOT NULL,
        source TEXT NOT NULL DEFAULT 'face_webrtc',
        UNIQUE (session_id, student_id),
        FOREIGN KEY (session_id) REFERENCES attendance_sessions(id) ON DELETE CASCADE,
        FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE RESTRICT
    );

    CREATE TABLE IF NOT EXISTS audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_type TEXT NOT NULL,
        event_detail TEXT NOT NULL,
        created_at_utc TEXT NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_embeddings_student
        ON face_embeddings(student_id);
    CREATE INDEX IF NOT EXISTS idx_course_enrollments_student
        ON course_enrollments(student_id);
    CREATE INDEX IF NOT EXISTS idx_attendance_session
        ON attendance(session_id);
    CREATE INDEX IF NOT EXISTS idx_session_enrollments_student
        ON session_enrollments(student_id);
    CREATE INDEX IF NOT EXISTS idx_sessions_status
        ON attendance_sessions(status);
    """
    with get_connection() as connection:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.executescript(schema)
        migration_key = "session_roster_migrated_v1"
        migrated = connection.execute(
            "SELECT 1 FROM app_settings WHERE setting_key = ?", (migration_key,)
        ).fetchone()
        if migrated is None:
            # Chuyển danh sách của các buổi cũ đúng một lần khi nâng cấp dữ liệu.
            connection.execute(
                """
                INSERT OR IGNORE INTO session_enrollments(
                    session_id, student_id, enrolled_at_utc
                )
                SELECT ses.id, ce.student_id, ses.created_at_utc
                FROM attendance_sessions ses
                JOIN course_enrollments ce ON ce.course_id = ses.course_id
                """
            )
            connection.execute(
                """
                INSERT INTO app_settings(setting_key, setting_value, updated_at_utc)
                VALUES (?, '1', ?)
                """,
                (migration_key, utc_iso()),
            )


def audit(connection: sqlite3.Connection, event_type: str, detail: str) -> None:
    connection.execute(
        "INSERT INTO audit_logs(event_type, event_detail, created_at_utc) VALUES (?, ?, ?)",
        (event_type, detail[:500], utc_iso()),
    )

def get_setting(key: str) -> str | None:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT setting_value FROM app_settings WHERE setting_key = ?", (key,)
        ).fetchone()
    return str(row["setting_value"]) if row else None

def set_setting(key: str, value: str) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO app_settings(setting_key, setting_value, updated_at_utc)
            VALUES (?, ?, ?)
            ON CONFLICT(setting_key) DO UPDATE SET
                setting_value = excluded.setting_value,
                updated_at_utc = excluded.updated_at_utc
            """,
            (key, value, utc_iso()),
        )
        audit(connection, "setting_updated", key)

def upsert_student(
    student_code: str, full_name: str, class_name: str
) -> sqlite3.Row:
    code = normalize_student_code(student_code)
    name = normalize_person_name(full_name)
    class_value = " ".join(class_name.strip().split())
    if not (1 <= len(class_value) <= 80):
        raise ValueError("Tên lớp phải dài từ 1 đến 80 ký tự.")

    now = utc_iso()
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO students(
                student_code, full_name, class_name, active,
                consent_at_utc, created_at_utc, updated_at_utc
            ) VALUES (?, ?, ?, 1, ?, ?, ?)
            ON CONFLICT(student_code) DO UPDATE SET
                full_name = excluded.full_name,
                class_name = excluded.class_name,
                active = 1,
                updated_at_utc = excluded.updated_at_utc
            """,
            (code, name, class_value, now, now, now),
        )
        row = connection.execute(
            "SELECT * FROM students WHERE student_code = ?", (code,)
        ).fetchone()
        audit(connection, "student_upserted", code)
        if row is None:
            raise RuntimeError("Không thể tạo hồ sơ sinh viên.")
        return row

def save_embedding(
    student_id: int,
    embedding: np.ndarray,
    image_hash: str,
    blur_score: float,
    brightness: float,
    face_width: int,
    face_height: int,
) -> bool:
    payload = sqlite3.Binary(np.asarray(embedding, dtype=np.float64).tobytes())
    with get_connection() as connection:
        try:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO face_embeddings(
                    student_id, embedding, image_sha256, blur_score,
                    brightness, face_width, face_height, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    student_id,
                    payload,
                    image_hash,
                    blur_score,
                    brightness,
                    face_width,
                    face_height,
                    utc_iso(),
                ),
            )
            if cursor.rowcount == 0:
                return False
            audit(connection, "face_embedding_added", f"student_id={student_id}")
            return True
        except sqlite3.IntegrityError as exc:
            raise ValueError("Không thể lưu dữ liệu khuôn mặt cho sinh viên này.") from exc

def student_table() -> pd.DataFrame:
    query = """
    SELECT s.id, s.student_code AS 'MSSV', s.full_name AS 'Họ tên',
           s.class_name AS 'Lớp', s.active AS 'Hoạt động',
           COUNT(fe.id) AS 'Số ảnh tham chiếu'
    FROM students s
    LEFT JOIN face_embeddings fe ON fe.student_id = s.id
    GROUP BY s.id
    ORDER BY s.student_code
    """
    with get_connection() as connection:
        frame = pd.read_sql_query(query, connection)
    if not frame.empty:
        frame["Hoạt động"] = frame["Hoạt động"].map({1: "Có", 0: "Không"})
    return frame

def remove_student_biometrics(student_id: int) -> None:
    with get_connection() as connection:
        connection.execute("DELETE FROM face_embeddings WHERE student_id = ?", (student_id,))
        connection.execute(
            "UPDATE students SET active = 0, updated_at_utc = ? WHERE id = ?",
            (utc_iso(), student_id),
        )
        audit(connection, "student_biometrics_removed", f"student_id={student_id}")

def create_course(course_code: str, course_name: str, lecturer: str) -> None:
    code = normalize_course_code(course_code)
    name = " ".join(course_name.strip().split())
    teacher = normalize_person_name(lecturer)
    if not (2 <= len(name) <= 120):
        raise ValueError("Tên môn học phải dài từ 2 đến 120 ký tự.")
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO courses(course_code, course_name, lecturer, created_at_utc)
            VALUES (?, ?, ?, ?)
            """,
            (code, name, teacher, utc_iso()),
        )
        audit(connection, "course_created", code)

def list_courses() -> list[sqlite3.Row]:
    with get_connection() as connection:
        return connection.execute(
            "SELECT * FROM courses ORDER BY course_code"
        ).fetchall()

def get_course_roster(course_id: int) -> set[int]:
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT student_id FROM course_enrollments WHERE course_id = ?",
            (course_id,),
        ).fetchall()
    return {int(row["student_id"]) for row in rows}

def set_course_roster(course_id: int, student_ids: Iterable[int]) -> int:
    normalized_ids = sorted({int(student_id) for student_id in student_ids})
    with get_connection() as connection:
        course = connection.execute(
            "SELECT id FROM courses WHERE id = ?", (course_id,)
        ).fetchone()
        if course is None:
            raise ValueError("Không tìm thấy môn học.")
        if normalized_ids:
            placeholders = ",".join("?" for _ in normalized_ids)
            rows = connection.execute(
                f"SELECT id FROM students WHERE active = 1 AND id IN ({placeholders})",
                normalized_ids,
            ).fetchall()
            valid_ids = {int(row["id"]) for row in rows}
            if valid_ids != set(normalized_ids):
                raise ValueError("Danh sách có sinh viên không tồn tại hoặc đã bị vô hiệu hóa.")

        connection.execute(
            "DELETE FROM course_enrollments WHERE course_id = ?", (course_id,)
        )
        now = utc_iso()
        connection.executemany(
            """
            INSERT INTO course_enrollments(course_id, student_id, enrolled_at_utc)
            VALUES (?, ?, ?)
            """,
            [(course_id, student_id, now) for student_id in normalized_ids],
        )
        audit(
            connection,
            "course_roster_updated",
            f"course={course_id},students={len(normalized_ids)}",
        )
        return len(normalized_ids)

def create_attendance_session(
    course_id: int,
    session_name: str,
    start_local: datetime,
    end_local: datetime,
    late_after_minutes: int,
) -> None:
    name = " ".join(session_name.strip().split())
    if not 1 <= len(name) <= 120:
        raise ValueError("Tên buổi học phải dài từ 1 đến 120 ký tự.")
    if end_local <= start_local:
        raise ValueError("Thời gian kết thúc phải sau thời gian bắt đầu.")
    if not 0 <= late_after_minutes <= 180:
        raise ValueError("Số phút tính đi trễ phải nằm trong khoảng 0-180.")
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO attendance_sessions(
                course_id, session_name, start_at_utc, end_at_utc,
                late_after_minutes, status, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, 'scheduled', ?)
            """,
            (
                course_id,
                name,
                utc_iso(start_local),
                utc_iso(end_local),
                late_after_minutes,
                utc_iso(),
            ),
        )
        session_id = int(cursor.lastrowid)
        connection.execute(
            """
            INSERT INTO session_enrollments(session_id, student_id, enrolled_at_utc)
            SELECT ?, student_id, ?
            FROM course_enrollments
            WHERE course_id = ?
            """,
            (session_id, utc_iso(), course_id),
        )
        audit(connection, "session_created", name)

def list_sessions(status: str | None = None) -> list[sqlite3.Row]:
    query = """
    SELECT s.*, c.course_code, c.course_name, c.lecturer
    FROM attendance_sessions s
    JOIN courses c ON c.id = s.course_id
    """
    params: tuple[Any, ...] = ()
    if status:
        query += " WHERE s.status = ?"
        params = (status,)
    query += " ORDER BY s.start_at_utc DESC"
    with get_connection() as connection:
        return connection.execute(query, params).fetchall()

def change_session_status(session_id: int, new_status: str) -> None:
    if new_status not in {"scheduled", "open", "closed"}:
        raise ValueError("Trạng thái buổi học không hợp lệ.")
    with get_connection() as connection:
        current = connection.execute(
            "SELECT status FROM attendance_sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if current is None:
            raise ValueError("Không tìm thấy buổi học.")
        current_status = str(current["status"])
        if current_status == new_status:
            return
        allowed_transitions = {"scheduled": "open", "open": "closed"}
        if allowed_transitions.get(current_status) != new_status:
            raise ValueError(
                f"Không thể chuyển trạng thái từ {current_status} sang {new_status}."
            )
        connection.execute(
            "UPDATE attendance_sessions SET status = ? WHERE id = ?",
            (new_status, session_id),
        )
        audit(connection, "session_status_changed", f"{session_id}:{new_status}")

def attendance_report(session_id: int) -> pd.DataFrame:
    query = """
    SELECT st.student_code AS 'MSSV', st.full_name AS 'Họ tên',
           st.class_name AS 'Lớp', c.course_code AS 'Mã môn',
           ses.session_name AS 'Buổi học',
           COALESCE(a.attendance_status, 'absent') AS 'Trạng thái',
           a.check_in_at_utc AS 'Thời gian UTC',
           a.recognition_distance AS 'Khoảng cách khuôn mặt',
           a.threshold_used AS 'Ngưỡng'
    FROM attendance_sessions ses
    JOIN courses c ON c.id = ses.course_id
    JOIN session_enrollments se ON se.session_id = ses.id
    JOIN students st ON st.id = se.student_id
    LEFT JOIN attendance a
        ON a.session_id = ses.id AND a.student_id = st.id
    WHERE ses.id = ?
    ORDER BY a.check_in_at_utc IS NULL, a.check_in_at_utc, st.student_code
    """
    with get_connection() as connection:
        frame = pd.read_sql_query(query, connection, params=(session_id,))
    if not frame.empty:
        frame["Thời gian điểm danh"] = frame["Thời gian UTC"].map(display_datetime)
        frame.drop(columns=["Thời gian UTC"], inplace=True)
        frame["Trạng thái"] = frame["Trạng thái"].map(
            {"present": "Có mặt", "late": "Đi trễ", "absent": "Vắng"}
        )
        frame["Khoảng cách khuôn mặt"] = frame["Khoảng cách khuôn mặt"].round(4)
    return frame

def mark_attendance(
    session_id: int, student_id: int, distance: float
) -> tuple[str, str]:
    """Ghi một lần/buổi bằng transaction; trả về (mã kết quả, thông báo)."""
    if not np.isfinite(distance) or not 0 <= distance <= FACE_TOLERANCE:
        return "rejected", "Kết quả nhận diện không đạt ngưỡng cho phép."

    now = utc_now()
    connection = get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        session = connection.execute(
            "SELECT * FROM attendance_sessions WHERE id = ?", (session_id,)
        ).fetchone()
        student = connection.execute(
            """
            SELECT st.*
            FROM students st
            JOIN session_enrollments se ON se.student_id = st.id
            WHERE st.id = ? AND st.active = 1 AND se.session_id = ?
            """,
            (student_id, session_id),
        ).fetchone()
        if session is None or session["status"] != "open":
            connection.rollback()
            return "closed", "Buổi học chưa mở hoặc đã đóng."
        if student is None:
            connection.rollback()
            return "inactive", "Sinh viên không hoạt động hoặc không thuộc môn học này."

        start_at = datetime.fromisoformat(session["start_at_utc"])
        end_at = datetime.fromisoformat(session["end_at_utc"])
        if now < start_at:
            connection.rollback()
            return "outside", "Chưa đến thời gian của buổi học."
        if now > end_at:
            connection.execute(
                "UPDATE attendance_sessions SET status = 'closed' WHERE id = ?",
                (session_id,),
            )
            audit(connection, "session_auto_closed", str(session_id))
            connection.commit()
            return "outside", "Buổi học đã hết thời gian và được đóng tự động."

        existing = connection.execute(
            "SELECT attendance_status, check_in_at_utc FROM attendance "
            "WHERE session_id = ? AND student_id = ?",
            (session_id, student_id),
        ).fetchone()
        if existing:
            connection.rollback()
            return (
                "already",
                f"{student['student_code']} đã điểm danh lúc "
                f"{display_datetime(existing['check_in_at_utc'])}.",
            )

        late_cutoff = start_at + timedelta(minutes=int(session["late_after_minutes"]))
        attendance_status = "late" if now > late_cutoff else "present"

        connection.execute(
            """
            INSERT INTO attendance(
                session_id, student_id, check_in_at_utc, attendance_status,
                recognition_distance, threshold_used, source
            ) VALUES (?, ?, ?, ?, ?, ?, 'face_webrtc')
            """,
            (
                session_id,
                student_id,
                utc_iso(now),
                attendance_status,
                float(distance),
                FACE_TOLERANCE,
            ),
        )
        audit(
            connection,
            "attendance_created",
            f"session={session_id},student={student_id},status={attendance_status}",
        )
        connection.commit()
        label = "ĐI TRỄ" if attendance_status == "late" else "CÓ MẶT"
        return "created", f"{student['student_code']} - {label}"
    except sqlite3.IntegrityError:
        connection.rollback()
        return "already", "Sinh viên đã được điểm danh trong buổi này."
    except sqlite3.Error as exc:
        connection.rollback()
        return "error", f"Lỗi cơ sở dữ liệu: {exc}"
    finally:
        connection.close()
