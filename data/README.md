# Data card

Dự án không phân phối ảnh khuôn mặt hoặc embedding thật. Người vận hành phải có sự đồng ý của chủ thể dữ liệu trước khi đăng ký.

## Schema dữ liệu đầu vào

- Ảnh JPEG/PNG, tối đa 8 MB.
- Chính xác một khuôn mặt trong mỗi ảnh.
- Khuôn mặt tối thiểu 100 x 100 px.
- Khuyến nghị 3-5 ảnh/người với ánh sáng và góc nhìn khác nhau.

## Quyền riêng tư

- Ảnh gốc chỉ được xử lý trong bộ nhớ và không được ghi xuống đĩa.
- Embedding vẫn là dữ liệu sinh trắc học nhạy cảm.
- Dữ liệu chạy thật phải nằm ngoài Git và được bảo vệ bằng quyền truy cập/mã hóa ổ đĩa.
- `BIOMETRIC_RETENTION_DAYS` quy định thời hạn lưu embedding; tác vụ xóa cần được gọi định kỳ khi triển khai.

## Protocol đánh giá đề xuất

Tách danh tính và ảnh thành enrollment, validation và test trước khi hiệu chỉnh threshold. Chọn threshold trên validation; chỉ dùng test để báo cáo FAR, FRR, TAR và latency. Không có metric nào được công bố trong repository cho đến khi có tập dữ liệu có consent và script tái tạo kết quả.
