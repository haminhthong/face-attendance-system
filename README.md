# Face Attendance System

Hệ thống điểm danh sinh viên bằng nhận diện khuôn mặt, chạy trên trình duyệt với Streamlit và WebRTC. Dự án quản lý sinh viên, môn học, danh sách lớp, buổi học, ghi nhận có mặt/đi trễ và xuất báo cáo CSV.

> Đây là dự án học tập/portfolio. Kiểm tra chớp mắt chỉ là liveness cơ bản, không thay thế giải pháp anti-spoofing chuyên dụng trong môi trường production.

## Tính năng

- Đăng ký sinh viên bằng nhiều ảnh tham chiếu hoặc camera.
- Chỉ nhận ảnh có đúng một khuôn mặt; kiểm tra độ mờ, độ sáng và kích thước mặt.
- Không lưu ảnh gốc, chỉ lưu face embedding 128 chiều và metadata chất lượng.
- Nhận diện thời gian thực bằng camera trình duyệt qua WebRTC.
- Xác nhận danh tính qua nhiều khung hình, face-distance và khoảng cách Top-1/Top-2.
- Kiểm tra chu trình mở → nhắm → mở mắt; trạng thái liveness tự hết hạn và reset khi khuôn mặt rời camera.
- Quản lý môn học, danh sách sinh viên và buổi học.
- Phân loại có mặt, đi trễ và vắng.
- Bảo đảm một sinh viên chỉ có một bản ghi trong mỗi buổi bằng unique constraint và transaction.
- Khu vực quản trị bằng PIN PBKDF2; tạm khóa sau nhiều lần đăng nhập sai.
- Xuất báo cáo CSV UTF-8 tương thích Excel.
- Audit log cho các thao tác quan trọng.
- API FastAPI có health check, danh sách buổi học và nghiệp vụ điểm danh.
- Chính sách retention cho embedding và tác vụ xóa dữ liệu quá hạn.
- Unit test cho matcher/liveness, smoke test API và CI bằng GitHub Actions.

## Công nghệ

| Thành phần | Công nghệ |
|---|---|
| Giao diện | Streamlit |
| Camera trình duyệt | streamlit-webrtc, PyAV |
| Computer vision | OpenCV, face-recognition/dlib |
| Dữ liệu | SQLite, Pandas, NumPy |
| Bảo mật PIN | PBKDF2-HMAC-SHA256 |
| API | FastAPI, Pydantic |
| Chất lượng | Pytest, GitHub Actions, Docker |

## Kiến trúc

```text
Face_Attendance_System/
├── app.py
├── pyproject.toml
├── requirements.txt
├── .env.example
├── src/face_attendance/
│   ├── config.py       # cấu hình và kiểm tra biến môi trường
│   ├── utils.py        # thời gian, chuẩn hóa input, mã hóa PIN
│   ├── database.py     # schema, repository và nghiệp vụ điểm danh
│   ├── recognition.py  # enrollment và video processor
│   ├── matcher.py      # unknown rejection và Top-1/Top-2 margin
│   ├── liveness.py     # máy trạng thái chớp mắt
│   ├── api.py          # REST API
│   └── ui.py           # các trang Streamlit
├── tests/
├── data/README.md
├── Dockerfile
└── .github/workflows/ci.yml
```

Luồng điểm danh:

```text
Camera WebRTC
  → phát hiện khuôn mặt
  → tạo embedding
  → so khớp theo từng sinh viên
  → kiểm tra tolerance + Top-1/Top-2 margin
  → xác nhận nhiều frame + chớp mắt
  → kiểm tra buổi học và roster
  → transaction SQLite
```

## Yêu cầu

- Python 3.11 hoặc 3.12 được khuyến nghị.
- Webcam và trình duyệt hiện đại.
- Windows cần CMake/Visual C++ Build Tools nếu `dlib` không có wheel phù hợp.

## Cài đặt

### Windows PowerShell

```powershell
git clone <repository-url>
cd Face_Attendance_System
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -e .
```

### Linux/macOS

```bash
git clone <repository-url>
cd Face_Attendance_System
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -e .
```

## Cấu hình

Sao chép `.env.example` thành `.env`, hoặc thiết lập biến môi trường trước khi chạy. Streamlit không tự đọc `.env`; có thể export biến bằng shell hoặc dùng nền tảng deploy để cấu hình.

| Biến | Mặc định | Ý nghĩa |
|---|---:|---|
| `FACE_ATTENDANCE_DATA_DIR` | `./face_attendance_data` | Nơi lưu SQLite |
| `FACE_ATTENDANCE_API_KEY` | không có | Khóa bí mật bắt buộc cho API ghi điểm danh |
| `FACE_TOLERANCE` | `0.50` | Face distance tối đa để chấp nhận |
| `MIN_IDENTITY_MARGIN` | `0.05` | Chênh lệch tối thiểu giữa Top-1 và Top-2 |
| `PROCESS_EVERY_N_FRAMES` | `3` | Tần suất xử lý khung hình |
| `CONFIRMATION_FRAMES` | `3` | Số frame liên tiếp để xác nhận |
| `BIOMETRIC_RETENTION_DAYS` | `365` | Thời hạn lưu embedding |

Không nên giảm tolerance hoặc thay đổi margin tùy ý. Hãy hiệu chỉnh bằng tập validation đại diện cho camera, ánh sáng và người dùng thực tế.

## Chạy ứng dụng

```powershell
streamlit run app.py
```

Chạy API ở terminal khác:

```powershell
uvicorn face_attendance.api:app --reload
```

Swagger UI có tại `http://127.0.0.1:8000/docs`.

Lần chạy đầu tiên:

1. Mở trang **Quản trị** và tạo PIN 6–12 chữ số.
2. Đăng ký sinh viên với 3–5 ảnh ở góc nhìn/ánh sáng khác nhau.
3. Tạo môn học và thêm sinh viên vào danh sách môn.
4. Tạo buổi học, chọn **Mở điểm danh**.
5. Sang trang **Điểm danh**, chọn buổi học và cho phép camera.

## Kiểm thử và Docker

```powershell
pip install -e ".[dev]"
python -m compileall app.py src tests
pytest -q
docker build -t face-attendance-system .
docker run --rm -p 8501:8501 face-attendance-system
```

## Mô hình dữ liệu

- `students`: hồ sơ và trạng thái sinh viên.
- `face_embeddings`: vector khuôn mặt, hash ảnh và metadata chất lượng.
- `courses`: môn học.
- `course_enrollments`: quan hệ sinh viên–môn học.
- `attendance_sessions`: thời gian, ngưỡng đi trễ và trạng thái buổi học.
- `attendance`: kết quả nhận diện; unique theo `(session_id, student_id)`.
- `app_settings`: cấu hình ứng dụng, gồm PIN đã hash.
- `audit_logs`: lịch sử thao tác quan trọng.

## Bảo mật và quyền riêng tư

- Cần có sự đồng ý rõ ràng trước khi thu thập dữ liệu khuôn mặt.
- Face embedding vẫn là dữ liệu sinh trắc học nhạy cảm dù không lưu ảnh gốc.
- Giới hạn quyền đọc thư mục dữ liệu, mã hóa ổ đĩa và sao lưu có kiểm soát.
- Không commit database, ảnh thật, PIN hoặc file `.env` lên Git.
- Khi triển khai Internet, dùng HTTPS/TURN phù hợp, reverse proxy, xác thực mạnh và rate limiting phía server.
- Thiết lập chính sách lưu trữ/xóa dữ liệu và cơ chế thu hồi consent.

## Giới hạn

- Blink detection có thể bị vượt qua bởi video replay hoặc kỹ thuật giả mạo nâng cao.
- Độ chính xác phụ thuộc camera, ánh sáng, góc mặt và dữ liệu đăng ký.
- SQLite phù hợp demo hoặc tải nhỏ; triển khai nhiều instance nên chuyển sang PostgreSQL.
- PIN và session-state Streamlit chưa thay thế hệ thống identity provider dành cho tổ chức.

## Hướng phát triển

- Thêm anti-spoofing model và challenge ngẫu nhiên.
- Tách repository/service interface để unit test không phụ thuộc Streamlit.
- Thêm Alembic migration, structured logging và CI.
- Đo precision, recall, FAR, FRR và latency trên tập test có kiểm soát.
- Docker hóa và triển khai HTTPS.
- Thêm RBAC cho quản trị viên/giảng viên.

## Gợi ý mô tả trong CV

> Xây dựng hệ thống điểm danh thời gian thực bằng Python, Streamlit WebRTC, OpenCV và face embeddings; thiết kế SQLite schema với transaction và unique constraints, quality gates cho ảnh, multi-frame confirmation, Top-1/Top-2 identity margin, blink-based liveness và báo cáo CSV.

Chỉ thêm số liệu accuracy/latency vào CV sau khi đã đo và ghi rõ quy mô tập kiểm thử.

## License

Chưa thiết lập license. Nếu công khai repository, hãy chọn license phù hợp và kiểm tra license của các dependency/dataset sử dụng.
