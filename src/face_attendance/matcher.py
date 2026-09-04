"""Module thuật toán so khớp khuôn mặt tập mở (Open-Set Face Recognition).

Thực hiện tính khoảng cách Euclidean L2 giữa vector khuôn mặt đầu vào (128D) và các mẫu tham chiếu,
gom nhóm theo từng sinh viên và áp dụng cơ chế từ chối người lạ (Unknown Rejection) bằng hai ngưỡng:
1. Ngưỡng khoảng cách tối đa (FACE_TOLERANCE).
2. Ngưỡng chênh lệch giữa Top-1 và Top-2 (MIN_IDENTITY_MARGIN) nhằm loại bỏ sự mơ hồ danh tính.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

import numpy as np


class MauKhuonMat(Protocol):
    """Protocol đại diện cho mẫu khuôn mặt tham chiếu."""

    student_id: int
    embedding: np.ndarray


@dataclass(frozen=True)
class KetQuaSoKhop:
    """Kết quả so khớp khuôn mặt.

    Attributes:
        mau (MauKhuonMat | None): Mẫu khuôn mặt khớp nhất (None nếu bị từ chối).
        khoang_cach (float): Khoảng cách Euclidean nhỏ nhất tìm được.
        do_phan_biet (float): Chênh lệch khoảng cách giữa Top-1 và Top-2.
    """

    mau: MauKhuonMat | None
    khoang_cach: float
    do_phan_biet: float


def tim_danh_tinh_tot_nhat(
    embedding: np.ndarray,
    danh_sach_mau: Sequence[MauKhuonMat],
    nguong_khoang_cach: float,
    nguong_phan_biet: float,
) -> KetQuaSoKhop:
    """Xác định danh tính phù hợp nhất từ vector đầu vào sử dụng thuật toán Open-Set Matching.

    Args:
        embedding (np.ndarray): Vector khuôn mặt đầu vào (128 chiều).
        danh_sach_mau (Sequence[MauKhuonMat]): Danh sách tất cả ảnh mẫu tham chiếu.
        nguong_khoang_cach (float): Khoảng cách L2 tối đa chấp nhận (FACE_TOLERANCE).
        nguong_phan_biet: Chênh lệch tối thiểu giữa hai ứng viên đầu.

    Returns:
        KetQuaSoKhop: Đối tượng chứa thông tin danh tính khớp nhất hoặc None nếu bị từ chối.

    Raises:
        ValueError: Nếu ngưỡng hoặc dữ liệu vector đầu vào/mẫu không hợp lệ.
    """
    if not 0 <= nguong_khoang_cach <= 2:
        raise ValueError("Ngưỡng khoảng cách phải nằm trong khoảng 0-2.")
    if not 0 <= nguong_phan_biet <= 2:
        raise ValueError("Ngưỡng phân biệt phải nằm trong khoảng 0-2.")
    if not danh_sach_mau:
        return KetQuaSoKhop(None, float("inf"), float("inf"))

    vector = np.asarray(embedding, dtype=np.float64)
    if vector.shape != (128,) or not np.isfinite(vector).all():
        raise ValueError("Embedding đầu vào phải có 128 giá trị hữu hạn.")

    # Mỗi sinh viên có nhiều ảnh; chỉ giữ khoảng cách L2 tốt nhất của người đó.
    theo_sinh_vien: dict[int, tuple[float, MauKhuonMat]] = {}
    for mau in danh_sach_mau:
        vector_mau = np.asarray(mau.embedding, dtype=np.float64)
        if vector_mau.shape != (128,) or not np.isfinite(vector_mau).all():
            raise ValueError("Embedding mẫu phải có 128 giá trị hữu hạn.")
        # Khoảng cách Euclidean L2 = sqrt(sum((v1 - v2)^2))
        khoang_cach = float(np.linalg.norm(vector_mau - vector))
        hien_tai = theo_sinh_vien.get(mau.student_id)
        if hien_tai is None or khoang_cach < hien_tai[0]:
            theo_sinh_vien[mau.student_id] = (khoang_cach, mau)

    # Sắp xếp các danh tính ứng viên theo khoảng cách tăng dần
    xep_hang = sorted(theo_sinh_vien.values(), key=lambda item: item[0])
    khoang_cach_tot_nhat, mau_tot_nhat = xep_hang[0]
    khoang_cach_thu_hai = xep_hang[1][0] if len(xep_hang) > 1 else float("inf")
    do_phan_biet = khoang_cach_thu_hai - khoang_cach_tot_nhat

    # Kiểm tra điều kiện từ chối người lạ (Unknown Rejection)
    # 1. Khoảng cách tốt nhất phải <= nguong_khoang_cach
    # 2. Độ chênh lệch giữa ứng viên #1 và ứng viên #2 phải >= nguong_phan_biet
    if (
        khoang_cach_tot_nhat > nguong_khoang_cach
        or do_phan_biet < nguong_phan_biet
    ):
        mau_tot_nhat = None

    return KetQuaSoKhop(mau_tot_nhat, khoang_cach_tot_nhat, do_phan_biet)
