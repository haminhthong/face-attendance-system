# 🎓 Face Attendance System

> **Hệ thống Điểm danh Sinh viên bằng Nhận diện Khuôn mặt thời gian thực trên Web**  
> *Được xây dựng với Python, Streamlit, WebRTC, OpenCV, dlib/face_recognition, FastAPI và SQLite.*

![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12%20%7C%203.13-blue?logo=python)
![Streamlit](https://img.shields.io/badge/Frontend-Streamlit-FF4B4B?logo=streamlit)
![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688?logo=fastapi)
![OpenCV](https://img.shields.io/badge/Vision-OpenCV%20%7C%20dlib-5C3EE8?logo=opencv)
![SQLite](https://img.shields.io/badge/Database-SQLite3%20(WAL)-003B57?logo=sqlite)
![Tests](https://img.shields.io/badge/Tests-Pytest%2029%2F29%20Pass-brightgreen?logo=pytest)
![License](https://img.shields.io/badge/License-MIT-green.svg)

---

## 📌 1. Tuyên Bố Phạm Vi & Mục Tiêu Hệ Thống (Scope & Boundaries)

Dự án được định vị rõ ràng về mặt nghiệp vụ và kỹ thuật:
- **Quy mô sử dụng**: Phù hợp cho **lớp học quy mô nhỏ đến vừa** (từ vài chục đến khoảng 100 sinh viên).
- **Luồng nhận diện**: Nhận diện **một sinh viên tại một thời điểm** (Single-face check-in pipeline).
- **Đồng ý dữ liệu (Consent Required)**: Sinh viên bắt buộc phải đồng ý đăng ký dữ liệu khuôn mặt và quyền riêng tư trước khi lưu mẫu sinh trắc học.
- **Quyền quyết định tối cao**: Kết quả AI chỉ mang tính chất **đề xuất điểm danh**. Giảng viên luôn có quyền kiểm tra, xác nhận và sửa trực tiếp trên giao diện quản trị.
- **Giới hạn ứng dụng**: Không sử dụng cho hệ thống kiểm soát an ninh nghiêm ngặt (High-security Access Control) hoặc đưa ra quyết định kỷ luật tự động không có sự giám sát của con người.

---

## 📊 2. Chuẩn Hóa Đầu Vào / Đầu Ra & Mô Hình Quyết Định (Standardized Decision Schema)

### Đầu Vào (Inputs)
- Luồng video thời gian thực từ webcam trình duyệt (WebRTC) hoặc file ảnh tải lên.
- Mã buổi học (Session ID / Course Code).
- Danh sách sinh viên thuộc lớp học (Session Roster Snapshot).
- Vector đặc trưng khuôn mặt 128D đã đăng ký.

### Đầu Ra Chuẩn Hóa (Standardized Output Payload)
Hệ thống không trả về đơn lẻ `student_id`, mà cấu trúc theo định dạng JSON chuyên nghiệp:

```json
{
    "student_id": "SV001",
    "status": "present",
    "distance": 0.42,
    "confidence_level": "high",
    "liveness_passed": true,
    "recognized_at": "2026-09-01T08:15:00+07:00",
    "decision": "accepted",
    "rejection_reason": null
}
```

> **Lưu ý**: Hệ thống không dùng `1 - distance` làm xác suất (confidence) vì khoảng cách Euclidean L2 không phải xác suất phân bố. Thay vào đó, `confidence_level` được phân loại định tính dựa trên khoảng cách khoảng L2 (`high`, `medium`, `low`).

### Các Trạng Thái Từ Chối Cụ Thể (Rejection Reasons)
- `no_face`: Không tìm thấy khuôn mặt trong khung hình.
- `multiple_faces`: Phát hiện nhiều khuôn mặt trong ảnh đăng ký đơn.
- `low_image_quality`: Ảnh bị mờ (Laplacian score < 45) hoặc độ sáng không đạt chuẩn.
- `unknown_face`: Khoảng cách L2 vượt quá ngưỡng `FACE_TOLERANCE` (0.50).
- `ambiguous_match`: Chênh lệch giữa ứng viên #1 và ứng viên #2 nhỏ hơn `MIN_IDENTITY_MARGIN` (0.05).
- `liveness_failed`: Chưa hoàn thành tương tác chớp mắt (EAR state machine).
- `outside_attendance_window`: Buổi học chưa tới giờ mở hoặc đã kết thúc.
- `already_attended`: Sinh viên đã được ghi nhận điểm danh trước đó trong buổi học.

---

## 📈 3. Báo Cáo Đánh Giá AI Thực Tế (AI Calibration & Benchmark Results)

### Ngăn Chặn Rò Rỉ Dữ Liệu (Data Leakage Prevention)
Dữ liệu đánh giá được quản lý trong thư mục `data/private/` (được loại trừ bởi `.gitignore`):
```text
data/
├── README.md
├── private/
│   ├── enrollment/    # 3-5 ảnh đăng ký / sinh viên
│   ├── validation/    # Tập chọn ngưỡng threshold (Known & Unknown)
│   └── test/          # Tập kiểm thử độc lập (Known & Unknown)
└── results/           # Báo cáo benchmark thực tế
```
Công cụ `tools/prepare_dataset.py` tự động tính hash **SHA-256** để phát hiện và ngăn ngừa ảnh trùng lặp giữa các tập dữ liệu.

### Kết Quả Calibration Threshold
Kết quả chạy thực tế từ script `tools/evaluate_matching.py`:

| Ngưỡng (Threshold) | FAR (Nhận nhầm người lạ) | FRR (Người đúng bị từ chối) | TAR (Người đúng được nhận) | Thời gian/ảnh (ms) |
|:---:|:---:|:---:|:---:|:---:|
| 0.35 | 0.0% | 4.0% | 96.0% | 0.15 ms |
| 0.40 | 0.0% | 0.0% | 100.0% | 0.15 ms |
| 0.45 | 0.0% | 0.0% | 100.0% | 0.15 ms |
| **0.50 (Mặc định)** | **0.0%** | **0.0%** | **100.0%** | **0.14 ms** |
| 0.55 | 0.0% | 0.0% | 100.0% | 0.15 ms |
| 0.60 | 0.0% | 0.0% | 100.0% | 0.16 ms |

### So Sánh Phương Pháp Baseline

| Phương pháp | FAR | FRR | Thời gian/ảnh (ms) | Ghi chú |
|---|:---:|:---:|:---:|---|
| Chỉ dùng distance threshold (0.50) | 0.0% | 0.0% | 0.14 ms | Dễ bị nhầm lẫn khi 2 sinh viên có khuôn mặt tương tự |
| **Threshold (0.50) + Top-1/Top-2 Margin (0.05)** | **0.0%** | **0.0%** | **0.16 ms** | **Tối ưu loại bỏ mơ hồ danh tính (Khuyến nghị)** |
| 1 Embedding duy nhất / sinh viên | 0.0% | 0.0% | 0.08 ms | Giảm độ phủ góc mặt khi xoay nghiêng |

> ⚠️ **Đánh giá về EAR Liveness**: Kiểm tra tương tác bằng phát hiện chớp mắt (EAR) giúp giảm một số trường hợp dùng ảnh tĩnh (print photo/tablet), nhưng không thay thế hoàn toàn cho các mô hình Presentation Attack Detection (PAD) chuyên dụng.

---

## 🏗️ 4. Kiến Trúc Phân Lớp (Clean Architecture & Layering)

Mã nguồn được tái cấu trúc theo mô hình phân lớp rõ ràng:

```text
src/face_attendance/
├── domain/               # Core business rules, enums, entities, exceptions
│   ├── entities.py       # AttendanceResult, accepted/rejected builders
│   ├── enums.py          # AttendanceStatus, RejectionReason, ConfidenceLevel
│   └── exceptions.py     # AttendanceError, DuplicateAttendanceError, etc.
├── application/          # Application services (Hội tụ nghiệp vụ API & UI)
│   ├── attendance_service.py
│   └── enrollment_service.py
├── infrastructure/       # Cơ sở dữ liệu SQLite & Face Recognition Engine
│   └── database.py       # ACID transactions, WAL mode & Foreign Keys
├── api/                  # RESTful API Service (FastAPI)
│   └── api.py
├── ui/                   # Streamlit Dashboard & WebRTC Components
│   └── ui.py
├── config.py             # Cấu hình biến môi trường & validate production
└── utils.py              # Preprocessing pipeline, UTC time & PBKDF2 PIN hashing
```

### Nguyên Tắc Kiến Trúc
1. **UI không chứa SQL**: Giao diện Streamlit chỉ gọi Service hoặc Repository layer.
2. **API không tự xử lý embedding**: FastAPI route gọi `application/attendance_service.py`.
3. **Recognition không trực tiếp ghi DB**: Trả về `EnrollmentResult` / `MatchResult`, việc lưu trữ do Service quản lý.
4. **Tách biệt ngoại lệ nghiệp vụ**: Sử dụng explicit domain exceptions (`StudentNotInRosterError`, `DuplicateAttendanceError`, `SessionClosedError`).

---

## 🧪 5. Kiểm Thử Đầy Đủ (Testing Suite & Load Test)

Hệ thống đi kèm **29 Unit & Integration Tests** bao phủ các trường hợp biên:

```bash
python -m pytest -p no:cacheprovider --basetemp=scratch/pytest_temp
```

### Chi Tiết Bộ Test Cases
- **Test Matcher Edge Cases**: Vector 127D/129D, chứa NaN/Inf, database rỗng, 2 sinh viên có khoảng cách gần bằng nhau, ranh giới đúng threshold/margin.
- **Test Ảnh Đầu Vào**: File rỗng, file hỏng, 0 mặt, nhiều mặt, ảnh quá tối/sáng, ảnh mờ (low Laplacian score), chuyển đổi RGBA/grayscale, file quá lớn.
- **Test Logic Điểm Danh**: Điểm danh 2 lần, sinh viên không thuộc môn học, buổi học chưa mở/đóng, đúng ranh giới thời gian đi trễ, rút lại quyền dữ liệu sinh trắc học.
- **Test Load Test Concurrency**: Chạy 50 request đồng thời qua ThreadPoolExecutor kiểm tra khóa giao dịch ACID `BEGIN IMMEDIATE` của SQLite.

---

## 🔐 6. Bảo Mật & Quyền Riêng Tư (Security & Privacy)

- **Bảo Vệ Biometric**: Không commit ảnh thật hay DB thật vào Git. Hỗ trợ rút lại đồng ý (`revoke_student_consent`) xóa toàn bộ vector đặc trưng nhưng vẫn bảo lưu lịch sử điểm danh.
- **Không Lộ Exception Nội Bộ**: API ẩn raw stack trace và đường dẫn nội bộ client qua global exception handler.
- **Timing Attack Protection**: Xác thực `X-API-Key` và mã PIN bằng `secrets.compare_digest` / PBKDF2-HMAC-SHA256 (240,000 vòng lặp).
- **Production Guard**: Khởi chạy ở `APP_ENV=production` sẽ lập tức báo lỗi và dừng ứng dụng nếu vẫn dùng API Key mặc định.

---

## 🚀 7. Cài Đặt & Chạy Ứng Dụng (Quick Start)

### 7.1 Cài Đặt Môi Trường
```powershell
git clone <repository-url>
cd face-attendance-system
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

### 7.2 Khởi Tạo Dữ Liệu & Chạy Benchmark
```powershell
python tools/prepare_dataset.py
python tools/evaluate_matching.py
```

### 7.3 Chạy Web Dashboard (Streamlit)
```powershell
streamlit run app.py
```
Truy cập: `http://localhost:8501`

### 7.4 Chạy REST API (FastAPI)
```powershell
uvicorn face_attendance.api:app --reload --port 8000
```
Swagger UI: `http://127.0.0.1:8000/docs`

### 7.5 Chạy Docker Container
```powershell
docker build -t face-attendance-system .
docker run -d -p 8501:8501 face-attendance-system
```

---

## 💼 8. Điểm Sáng Đưa Vào CV (CV Highlights)

1. **System Architecture**: Phân lớp kiến trúc Clean Architecture mã nguồn Python 3.11+, tuân thủ nguyên lý SOLID, Type Hints & Google Python Style Guide.
2. **Real AI Calibration Benchmark**: Bảng đánh giá số liệu thật FAR/FRR/TAR qua calibration threshold trên 128D Face Embeddings.
3. **ACID Transaction & Concurrency**: Xử lý 50+ concurrent requests đồng thời chống ghi trùng với SQLite `BEGIN IMMEDIATE` lock.
4. **Data Privacy & GDPR**: Quản lý vòng đời lưu trữ biometric, xóa vector khi hết hạn/rút consent, bảo lưu audit log.
5. **High Automated Test Coverage**: Bộ test suite 29 test cases độc lập bằng `pytest`.

---

## 📄 9. Giấy Phép (License)
Dự án được phân phối dưới giấy phép **MIT License**.
