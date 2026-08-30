"""Module xử lý nhận diện khuôn mặt, đăng ký mẫu tham chiếu và WebRTC Video Engine.

Chịu trách nhiệm:
1. Đăng ký & kiểm tra chất lượng ảnh sinh viên (độ mờ Laplacian, độ sáng mean, kích thước khuôn mặt, duy nhất 1 mặt).
2. Tải và quản lý bộ cache vector mẫu (FaceTemplate) theo buổi học.
3. Engine nhận diện thời gian thực (RecognitionEngine) tích hợp skip-frame (0.25x scaling), liveness chớp mắt và xác nhận đa khung hình.
4. Streamlit WebRTC VideoProcessor cho luồng camera trình duyệt.
"""

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
from .liveness import BoKiemTraChopMat, ti_le_mat
from .matcher import tim_danh_tinh_tot_nhat
from .utils import utc_iso

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class EnrollmentResult:
    """Kết quả giải mã và xác thực ảnh đăng ký sinh viên.

    Attributes:
        embedding (np.ndarray): Vector khuôn mặt 128 chiều.
        image_hash (str): Hash SHA-256 của file ảnh gốc.
        blur_score (float): Điểm độ sắc nét (Laplacian variance).
        brightness (float): Độ sáng trung bình (0-255).
        face_width (int): Chiều rộng vùng mặt (px).
        face_height (int): Chiều cao vùng mặt (px).
    """

    embedding: np.ndarray
    image_hash: str
    blur_score: float
    brightness: float
    face_width: int
    face_height: int


def decode_and_validate_face(image_bytes: bytes) -> EnrollmentResult:
    """Giải mã file ảnh, kiểm tra tiêu chuẩn chất lượng và trích xuất vector khuôn mặt 128D.

    Các bước kiểm tra:
    1. Giới hạn dung lượng file <= 8 MB.
    2. Đọc định dạng ảnh (OpenCV imdecode).
    3. Điểm sắc nét (Laplacian Variance >= MIN_BLUR_SCORE).
    4. Độ sáng trung bình (MIN_BRIGHTNESS <= Mean <= MAX_BRIGHTNESS).
    5. Phát hiện duy nhất 1 khuôn mặt trong ảnh.
    6. Kích thước vùng mặt tối thiểu (>= 100x100px).
    7. Trích xuất vector đặc trưng 128D bằng dlib resnet model.

    Args:
        image_bytes (bytes): Dữ liệu nhị phân của file ảnh.

    Returns:
        EnrollmentResult: Kết quả trích xuất hợp lệ.

    Raises:
        ValueError: Nếu ảnh vi phạm bất kỳ tiêu chuẩn chất lượng nào.
    """
    if not image_bytes:
        raise ValueError("File ảnh đang trống.")
    if len(image_bytes) > MAX_UPLOAD_BYTES:
        raise ValueError("Ảnh vượt quá giới hạn 8 MB.")

    buffer = np.frombuffer(image_bytes, dtype=np.uint8)
    image_bgr = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    if image_bgr is None:
        raise ValueError("Nội dung file không phải ảnh hợp lệ.")

    # 1. Kiểm tra độ mờ bằng biến thiên Laplacian
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    blur_score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    brightness = float(gray.mean())
    if blur_score < MIN_BLUR_SCORE:
        raise ValueError(
            f"Ảnh quá mờ (blur={blur_score:.1f}, yêu cầu ≥ {MIN_BLUR_SCORE:.0f})."
        )

    # 2. Kiểm tra độ sáng trung bình
    if not MIN_BRIGHTNESS <= brightness <= MAX_BRIGHTNESS:
        raise ValueError(
            f"Ánh sáng chưa phù hợp (brightness={brightness:.1f}, "
            f"yêu cầu {MIN_BRIGHTNESS:.0f}-{MAX_BRIGHTNESS:.0f})."
        )

    # 3. Phát hiện số lượng khuôn mặt
    image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    locations = face_recognition.face_locations(image_rgb, number_of_times_to_upsample=1)
    if len(locations) != 1:
        raise ValueError(
            f"Mỗi ảnh phải có đúng 1 khuôn mặt; hệ thống tìm thấy {len(locations)}."
        )

    # 4. Kiểm tra kích thước khuôn mặt
    top, right, bottom, left = locations[0]
    face_width = right - left
    face_height = bottom - top
    if face_width < MIN_FACE_SIZE_PX or face_height < MIN_FACE_SIZE_PX:
        raise ValueError(
            f"Khuôn mặt quá nhỏ ({face_width}×{face_height}px); hãy đứng gần camera hơn."
        )

    # 5. Trích xuất 128-dimensional face encoding
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
    """Đăng ký sinh viên và lưu các mẫu vector khuôn mặt vào cơ sở dữ liệu.

    Args:
        student_code (str): Mã sinh viên.
        full_name (str): Họ tên sinh viên.
        class_name (str): Lớp sinh hoạt.
        image_sources (Iterable[Any]): Danh sách đối tượng chứa dữ liệu ảnh (Streamlit UploadFile / CameraInput).

    Returns:
        tuple[int, list[str]]: (Số ảnh đã lưu thành công, Danh sách cảnh báo/lỗi nếu có).
    """
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
    """Mẫu khuôn mặt tham chiếu được nạp vào RAM cho quá trình so khớp realtime."""

    student_id: int
    student_code: str
    full_name: str
    embedding: np.ndarray


def load_templates(session_id: int | None = None) -> list[FaceTemplate]:
    """Tải danh sách các mẫu khuôn mặt (FaceTemplate) active từ cơ sở dữ liệu.

    Tùy chọn lọc theo `session_id` để chỉ tải các sinh viên thuộc danh sách môn học của buổi đó.

    Args:
        session_id (int | None): ID buổi học hoặc None nếu nạp toàn bộ.

    Returns:
        list[FaceTemplate]: Danh sách mẫu tham chiếu.
    """
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


class RecognitionEngine:
    """Bộ máy xử lý và điều phối nhận diện khuôn mặt realtime qua luồng camera WebRTC.

    Tích hợp:
    - Skip-frame processing (thu nhỏ ảnh 0.25x) để duy trì tốc độ FPS cao.
    - So khớp Open-Set với từ chối người lạ (Matcher).
    - Máy trạng thái liveness chớp mắt (BoKiemTraChopMat).
    - Đếm xác nhận liên tiếp nhiều khung hình (Confirmation frames).
    - Khóa Threading Lock cho đồng bộ sự kiện sang UI Streamlit.
    """

    def __init__(self, session_id: int, require_blink: bool) -> None:
        self.session_id = session_id
        self.require_blink = require_blink
        self.templates = load_templates(session_id)
        self.frame_number = 0
        self.confirm_counts: dict[int, int] = {}
        self.blink_checker = BoKiemTraChopMat(
            BLINK_EAR_CLOSED, BLINK_EAR_OPEN, BLINK_VERIFICATION_SECONDS
        )
        self.last_attempt: dict[int, float] = {}
        self.last_event = "Đang chờ khuôn mặt..."
        self.last_event_type = "info"
        self.last_event_at = utc_iso()
        self.lock = threading.Lock()
        self.last_annotations: list[tuple[int, int, int, int, tuple[int, int, int], str]] = []

    def snapshot(self) -> tuple[str, str, str]:
        """Trích xuất ảnh chụp trạng thái sự kiện mới nhất cho UI (thread-safe)."""
        with self.lock:
            return self.last_event_type, self.last_event, self.last_event_at

    def set_event(self, event_type: str, message: str) -> None:
        """Cập nhật thông báo sự kiện điểm danh cho UI (thread-safe)."""
        with self.lock:
            self.last_event_type = event_type
            self.last_event = message
            self.last_event_at = utc_iso()

    def best_identity(
        self, encoding: np.ndarray
    ) -> tuple[FaceTemplate | None, float, float]:
        """Tìm danh tính khớp nhất sử dụng module matcher."""
        if not self.templates:
            return None, float("inf"), float("inf")
        result = tim_danh_tinh_tot_nhat(
            encoding, self.templates, FACE_TOLERANCE, MIN_IDENTITY_MARGIN
        )
        return result.mau, result.khoang_cach, result.do_phan_biet

    def update_blink(self, student_id: int, landmarks: dict[str, Any] | None) -> bool:
        """Cập nhật tỉ lệ mắt và máy trạng thái chớp mắt."""
        if not self.require_blink:
            return True
        if not landmarks:
            return False
        left = ti_le_mat(landmarks.get("left_eye", []))
        right = ti_le_mat(landmarks.get("right_eye", []))
        if left is None or right is None:
            return False
        return self.blink_checker.cap_nhat(student_id, (left + right) / 2.0)

    def draw_annotations(self, image_bgr: np.ndarray) -> np.ndarray:
        """Vẽ các ô bounding box và nhãn tên/trạng thái lên hình ảnh."""
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
        """Xử lý chính cho mỗi khung hình (Frame processing pipeline).

        Args:
            image_bgr (np.ndarray): Khung hình BGR từ camera WebRTC.

        Returns:
            np.ndarray: Khung hình sau khi vẽ bounding box và nhãn nhận diện.
        """
        self.frame_number += 1
        # Chỉ xử lý các frame cách nhau PROCESS_EVERY_N_FRAMES để tăng tốc độ xử lý
        if self.frame_number % PROCESS_EVERY_N_FRAMES != 0:
            return self.draw_annotations(image_bgr)

        # Thu nhỏ khung hình 0.25x để phát hiện khuôn mặt nhanh hơn
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

        # Reset đếm khung hình nếu sinh viên rời khỏi camera
        for student_id in list(self.confirm_counts):
            if student_id not in seen_students:
                self.confirm_counts[student_id] = 0
                self.blink_checker.dat_lai(student_id)
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

        # Chuẩn bị danh sách nhãn vẽ đồ họa
        new_annotations: list[
            tuple[int, int, int, int, tuple[int, int, int], str]
        ] = []
        for observation in observations:
            top, right, bottom, left = observation["location"]
            # Nhân 4 lần tọa độ do đã thu nhỏ 0.25x
            top, right, bottom, left = top * 4, right * 4, bottom * 4, left * 4
            template: FaceTemplate | None = observation["template"]
            distance = float(observation["distance"])

            if template is None:
                color = (0, 0, 255)  # Đỏ: Người lạ
                label = "KHÔNG XÁC ĐỊNH"
            else:
                count = self.confirm_counts.get(template.student_id, 0)
                if not observation["live"]:
                    color = (0, 215, 255)  # Vàng: Cần chớp mắt
                    label = f"{template.student_code} - CHỚP MẮT"
                    self.set_event("warning", f"{template.student_code}: hãy chớp mắt một lần.")
                elif count < CONFIRMATION_FRAMES:
                    color = (0, 215, 255)  # Vàng: Đang xác nhận giữ yên
                    label = (
                        f"{template.student_code} - GIỮ YÊN "
                        f"{count}/{CONFIRMATION_FRAMES}"
                    )
                else:
                    color = (0, 255, 0)  # Xanh lá: Khớp thành công
                    label = f"{template.student_code} - KHỚP {distance:.3f}"
                    now_mono = time.monotonic()
                    last = self.last_attempt.get(template.student_id, 0.0)
                    # Ghi điểm danh có cooldown tránh ghi liên tục
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
    """Processor tương thích với streamlit_webrtc để xử lý từng VideoFrame từ webcam trình duyệt."""

    def __init__(self, engine: RecognitionEngine) -> None:
        self.engine = engine

    def recv(self, frame: av.VideoFrame) -> av.VideoFrame:
        """Hàm callback nhận khung hình video từ WebRTC streamer."""
        image = frame.to_ndarray(format="bgr24")
        try:
            output = self.engine.process(image)
        except Exception:
            LOGGER.exception("Không thể xử lý khung hình từ camera")
            self.engine.set_event("error", "Không thể xử lý hình ảnh từ camera.")
            output = image
        return av.VideoFrame.from_ndarray(output, format="bgr24")

