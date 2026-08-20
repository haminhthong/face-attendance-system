from __future__ import annotations

import hashlib
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Iterable

import av
import cv2
import face_recognition
import numpy as np
from streamlit_webrtc import VideoProcessorBase

from .config import (
    ATTEMPT_COOLDOWN_SECONDS,
    BLINK_EAR_CLOSED,
    BLINK_EAR_OPEN,
    BLINK_VERIFICATION_SECONDS,
    CONFIRMATION_FRAMES,
    FACE_TOLERANCE,
    MAX_BRIGHTNESS,
    MAX_UPLOAD_BYTES,
    MIN_BLUR_SCORE,
    MIN_BRIGHTNESS,
    MIN_FACE_SIZE_PX,
    MIN_IDENTITY_MARGIN,
    PROCESS_EVERY_N_FRAMES,
)
from .database import get_connection, mark_attendance, save_embedding, upsert_student
from .utils import utc_iso

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class EnrollmentResult:
    embedding: np.ndarray
    image_hash: str
    blur_score: float
    brightness: float
    face_width: int
    face_height: int

def decode_and_validate_face(image_bytes: bytes) -> EnrollmentResult:
    if not image_bytes:
        raise ValueError("File ảnh đang trống.")
    if len(image_bytes) > MAX_UPLOAD_BYTES:
        raise ValueError("Ảnh vượt quá giới hạn 8 MB.")

    buffer = np.frombuffer(image_bytes, dtype=np.uint8)
    image_bgr = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    if image_bgr is None:
        raise ValueError("Nội dung file không phải ảnh hợp lệ.")

    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    blur_score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    brightness = float(gray.mean())
    if blur_score < MIN_BLUR_SCORE:
        raise ValueError(
            f"Ảnh quá mờ (blur={blur_score:.1f}, yêu cầu ≥ {MIN_BLUR_SCORE:.0f})."
        )
    if not MIN_BRIGHTNESS <= brightness <= MAX_BRIGHTNESS:
        raise ValueError(
            f"Ánh sáng chưa phù hợp (brightness={brightness:.1f}, "
            f"yêu cầu {MIN_BRIGHTNESS:.0f}-{MAX_BRIGHTNESS:.0f})."
        )

    image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    locations = face_recognition.face_locations(image_rgb, number_of_times_to_upsample=1)
    if len(locations) != 1:
        raise ValueError(
            f"Mỗi ảnh phải có đúng 1 khuôn mặt; hệ thống tìm thấy {len(locations)}."
        )

    top, right, bottom, left = locations[0]
    face_width = right - left
    face_height = bottom - top
    if face_width < MIN_FACE_SIZE_PX or face_height < MIN_FACE_SIZE_PX:
        raise ValueError(
            f"Khuôn mặt quá nhỏ ({face_width}×{face_height}px); hãy đứng gần camera hơn."
        )

    encodings = face_recognition.face_encodings(
        image_rgb, known_face_locations=locations, num_jitters=2, model="small"
    )
    if len(encodings) != 1:
        raise ValueError("Không thể tạo vector khuôn mặt từ ảnh này.")

    return EnrollmentResult(
        embedding=np.asarray(encodings[0], dtype=np.float64),
        image_hash=hashlib.sha256(image_bytes).hexdigest(),
        blur_score=blur_score,
        brightness=brightness,
        face_width=face_width,
        face_height=face_height,
    )

def enroll_student_images(
    student_code: str,
    full_name: str,
    class_name: str,
    image_sources: Iterable[Any],
) -> tuple[int, list[str]]:
    sources = list(image_sources)
    if not sources:
        raise ValueError("Hãy tải ảnh lên hoặc chụp ít nhất một ảnh.")

    # Chỉ tạo/cập nhật sinh viên sau khi đã có ít nhất một ảnh hợp lệ.
    validated: list[tuple[str, EnrollmentResult]] = []
    errors: list[str] = []
    for index, source in enumerate(sources, start=1):
        source_name = getattr(source, "name", f"Ảnh {index}")
        try:
            image_bytes = source.getvalue()
            validated.append((source_name, decode_and_validate_face(image_bytes)))
        except (AttributeError, OSError, ValueError) as exc:
            errors.append(f"{source_name}: {exc}")

    if not validated:
        raise ValueError("Không có ảnh hợp lệ. " + " | ".join(errors))

    student = upsert_student(student_code, full_name, class_name)
    saved = 0
    duplicates = 0
    for _, result in validated:
        if save_embedding(
            int(student["id"]),
            result.embedding,
            result.image_hash,
            result.blur_score,
            result.brightness,
            result.face_width,
            result.face_height,
        ):
            saved += 1
        else:
            duplicates += 1

    messages = errors
    if duplicates:
        messages.append(f"Bỏ qua {duplicates} ảnh trùng đã đăng ký trước đó.")
    return saved, messages

@dataclass(frozen=True)
class FaceTemplate:
    student_id: int
    student_code: str
    full_name: str
    embedding: np.ndarray

def load_templates(session_id: int | None = None) -> list[FaceTemplate]:
    query = """
    SELECT s.id AS student_id, s.student_code, s.full_name, fe.embedding
    FROM face_embeddings fe
    JOIN students s ON s.id = fe.student_id
    """
    params: tuple[Any, ...] = ()
    if session_id is not None:
        query += """
        JOIN session_enrollments se ON se.student_id = s.id
        WHERE s.active = 1 AND se.session_id = ?
        """
        params = (session_id,)
    else:
        query += " WHERE s.active = 1"
    query += """
    ORDER BY s.student_code, fe.id
    """
    templates: list[FaceTemplate] = []
    with get_connection() as connection:
        rows = connection.execute(query, params).fetchall()
    for row in rows:
        embedding = np.frombuffer(row["embedding"], dtype=np.float64).copy()
        if embedding.shape == (128,):
            templates.append(
                FaceTemplate(
                    student_id=int(row["student_id"]),
                    student_code=str(row["student_code"]),
                    full_name=str(row["full_name"]),
                    embedding=embedding,
                )
            )
    return templates

def euclidean_distance(point_a: np.ndarray, point_b: np.ndarray) -> float:
    return float(np.linalg.norm(point_a - point_b))

def eye_aspect_ratio(points: list[tuple[int, int]]) -> float | None:
    if len(points) != 6:
        return None
    values = np.asarray(points, dtype=np.float64)
    vertical_1 = euclidean_distance(values[1], values[5])
    vertical_2 = euclidean_distance(values[2], values[4])
    horizontal = euclidean_distance(values[0], values[3])
    if horizontal <= 1e-6:
        return None
    return (vertical_1 + vertical_2) / (2.0 * horizontal)

class RecognitionEngine:
    def __init__(self, session_id: int, require_blink: bool) -> None:
        self.session_id = session_id
        self.require_blink = require_blink
        self.templates = load_templates(session_id)
        self.known_matrix = (
            np.vstack([template.embedding for template in self.templates])
            if self.templates
            else np.empty((0, 128), dtype=np.float64)
        )
        self.frame_number = 0
        self.confirm_counts: dict[int, int] = {}
        self.blink_states: dict[int, str] = {}
        self.blink_verified_at: dict[int, float] = {}
        self.last_attempt: dict[int, float] = {}
        self.last_event = "Đang chờ khuôn mặt..."
        self.last_event_type = "info"
        self.last_event_at = utc_iso()
        self.lock = threading.Lock()
        self.last_annotations: list[tuple[int, int, int, int, tuple[int, int, int], str]] = []

    def snapshot(self) -> tuple[str, str, str]:
        with self.lock:
            return self.last_event_type, self.last_event, self.last_event_at

    def set_event(self, event_type: str, message: str) -> None:
        with self.lock:
            self.last_event_type = event_type
            self.last_event = message
            self.last_event_at = utc_iso()

    def best_identity(
        self, encoding: np.ndarray
    ) -> tuple[FaceTemplate | None, float, float]:
        if not self.templates:
            return None, float("inf"), float("inf")
        distances = face_recognition.face_distance(self.known_matrix, encoding)

        # Chọn ảnh gần nhất của từng sinh viên trước khi so sánh hai ứng viên đầu.
        by_student: dict[int, tuple[float, FaceTemplate]] = {}
        for distance, template in zip(distances, self.templates):
            current = by_student.get(template.student_id)
            if current is None or float(distance) < current[0]:
                by_student[template.student_id] = (float(distance), template)
        ranked = sorted(by_student.values(), key=lambda item: item[0])
        best_distance, best_template = ranked[0]
        second_distance = ranked[1][0] if len(ranked) > 1 else float("inf")
        margin = second_distance - best_distance
        if best_distance > FACE_TOLERANCE or margin < MIN_IDENTITY_MARGIN:
            return None, best_distance, margin
        return best_template, best_distance, margin

    def update_blink(self, student_id: int, landmarks: dict[str, Any] | None) -> bool:
        if not self.require_blink:
            return True
        if not landmarks:
            return False
        left = eye_aspect_ratio(landmarks.get("left_eye", []))
        right = eye_aspect_ratio(landmarks.get("right_eye", []))
        if left is None or right is None:
            return False
        ear = (left + right) / 2.0
        state = self.blink_states.get(student_id, "need_open")
        if state == "verified":
            verified_at = self.blink_verified_at.get(student_id, 0.0)
            if time.monotonic() - verified_at <= BLINK_VERIFICATION_SECONDS:
                return True
            state = "need_open"
        if state == "need_open" and ear >= BLINK_EAR_OPEN:
            state = "need_closed"
        elif state == "need_closed" and ear <= BLINK_EAR_CLOSED:
            state = "need_reopen"
        elif state == "need_reopen" and ear >= BLINK_EAR_OPEN:
            state = "verified"
            self.blink_verified_at[student_id] = time.monotonic()
        self.blink_states[student_id] = state
        return state == "verified"

    def draw_annotations(self, image_bgr: np.ndarray) -> np.ndarray:
        for top, right, bottom, left, color, label in self.last_annotations:
            cv2.rectangle(image_bgr, (left, top), (right, bottom), color, 2)
            label_y = max(25, top - 10)
            cv2.putText(
                image_bgr,
                label,
                (left, label_y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                color,
                2,
                cv2.LINE_AA,
            )
        return image_bgr

    def process(self, image_bgr: np.ndarray) -> np.ndarray:
        self.frame_number += 1
        if self.frame_number % PROCESS_EVERY_N_FRAMES != 0:
            return self.draw_annotations(image_bgr)

        small = cv2.resize(image_bgr, (0, 0), fx=0.25, fy=0.25)
        rgb_small = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
        locations = face_recognition.face_locations(rgb_small, model="hog")
        encodings = face_recognition.face_encodings(rgb_small, locations, model="small")
        landmarks_list = (
            face_recognition.face_landmarks(rgb_small, locations, model="small")
            if self.require_blink and locations
            else [{} for _ in locations]
        )

        observations: list[dict[str, Any]] = []
        seen_students: set[int] = set()
        for index, (encoding, location) in enumerate(zip(encodings, locations)):
            template, distance, margin = self.best_identity(encoding)
            landmarks = landmarks_list[index] if index < len(landmarks_list) else {}
            if template:
                seen_students.add(template.student_id)
                live = self.update_blink(template.student_id, landmarks)
            else:
                live = False
            observations.append(
                {
                    "location": location,
                    "template": template,
                    "distance": distance,
                    "margin": margin,
                    "live": live,
                }
            )

        for student_id in list(self.confirm_counts):
            if student_id not in seen_students:
                self.confirm_counts[student_id] = 0
                self.blink_states.pop(student_id, None)
                self.blink_verified_at.pop(student_id, None)
        live_students = {
            observation["template"].student_id
            for observation in observations
            if observation["template"] is not None and observation["live"]
        }
        for student_id in seen_students:
            if student_id in live_students:
                self.confirm_counts[student_id] = (
                    self.confirm_counts.get(student_id, 0) + 1
                )
            else:
                self.confirm_counts[student_id] = 0

        new_annotations: list[
            tuple[int, int, int, int, tuple[int, int, int], str]
        ] = []
        for observation in observations:
            top, right, bottom, left = observation["location"]
            top, right, bottom, left = top * 4, right * 4, bottom * 4, left * 4
            template: FaceTemplate | None = observation["template"]
            distance = float(observation["distance"])

            if template is None:
                color = (0, 0, 255)
                label = "KHÔNG XÁC ĐỊNH"
            else:
                count = self.confirm_counts.get(template.student_id, 0)
                if not observation["live"]:
                    color = (0, 215, 255)
                    label = f"{template.student_code} - CHỚP MẮT"
                    self.set_event("warning", f"{template.student_code}: hãy chớp mắt một lần.")
                elif count < CONFIRMATION_FRAMES:
                    color = (0, 215, 255)
                    label = (
                        f"{template.student_code} - GIỮ YÊN "
                        f"{count}/{CONFIRMATION_FRAMES}"
                    )
                else:
                    color = (0, 255, 0)
                    label = f"{template.student_code} - KHỚP {distance:.3f}"
                    now_mono = time.monotonic()
                    last = self.last_attempt.get(template.student_id, 0.0)
                    if now_mono - last >= ATTEMPT_COOLDOWN_SECONDS:
                        result, message = mark_attendance(
                            self.session_id, template.student_id, distance
                        )
                        self.last_attempt[template.student_id] = now_mono
                        event_type = {
                            "created": "success",
                            "already": "info",
                            "closed": "error",
                            "inactive": "error",
                            "outside": "error",
                            "rejected": "error",
                            "error": "error",
                        }.get(result, "info")
                        self.set_event(event_type, message)

            new_annotations.append((top, right, bottom, left, color, label))
        self.last_annotations = new_annotations
        return self.draw_annotations(image_bgr)

class AttendanceVideoProcessor(VideoProcessorBase):
    def __init__(self, engine: RecognitionEngine) -> None:
        self.engine = engine

    def recv(self, frame: av.VideoFrame) -> av.VideoFrame:
        image = frame.to_ndarray(format="bgr24")
        try:
            output = self.engine.process(image)
        except Exception:
            LOGGER.exception("Không thể xử lý khung hình từ camera")
            self.engine.set_event("error", "Không thể xử lý hình ảnh từ camera.")
            output = image
        return av.VideoFrame.from_ndarray(output, format="bgr24")
