from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

import numpy as np


class MauKhuonMat(Protocol):
    student_id: int
    embedding: np.ndarray


@dataclass(frozen=True)
class KetQuaSoKhop:
    mau: MauKhuonMat | None
    khoang_cach: float
    do_phan_biet: float


def tim_danh_tinh_tot_nhat(
    embedding: np.ndarray,
    danh_sach_mau: Sequence[MauKhuonMat],
    nguong_khoang_cach: float,
    nguong_phan_biet: float,
) -> KetQuaSoKhop:
    """So khớp mở: gom theo sinh viên rồi áp dụng hai ngưỡng từ cấu hình."""
    if not 0 <= nguong_khoang_cach <= 2:
        raise ValueError("Ngưỡng khoảng cách phải nằm trong khoảng 0-2.")
    if not 0 <= nguong_phan_biet <= 2:
        raise ValueError("Ngưỡng phân biệt phải nằm trong khoảng 0-2.")
    if not danh_sach_mau:
        return KetQuaSoKhop(None, float("inf"), float("inf"))

    vector = np.asarray(embedding, dtype=np.float64)
    if vector.shape != (128,) or not np.isfinite(vector).all():
        raise ValueError("Embedding đầu vào phải có 128 giá trị hữu hạn.")

    theo_sinh_vien: dict[int, tuple[float, MauKhuonMat]] = {}
    for mau in danh_sach_mau:
        vector_mau = np.asarray(mau.embedding, dtype=np.float64)
        if vector_mau.shape != (128,) or not np.isfinite(vector_mau).all():
            raise ValueError("Embedding mẫu phải có 128 giá trị hữu hạn.")
        khoang_cach = float(np.linalg.norm(vector_mau - vector))
        hien_tai = theo_sinh_vien.get(mau.student_id)
        if hien_tai is None or khoang_cach < hien_tai[0]:
            theo_sinh_vien[mau.student_id] = (khoang_cach, mau)

    xep_hang = sorted(theo_sinh_vien.values(), key=lambda item: item[0])
    khoang_cach_tot_nhat, mau_tot_nhat = xep_hang[0]
    khoang_cach_thu_hai = xep_hang[1][0] if len(xep_hang) > 1 else float("inf")
    do_phan_biet = khoang_cach_thu_hai - khoang_cach_tot_nhat

    if (
        khoang_cach_tot_nhat > nguong_khoang_cach
        or do_phan_biet < nguong_phan_biet
    ):
        mau_tot_nhat = None
    return KetQuaSoKhop(mau_tot_nhat, khoang_cach_tot_nhat, do_phan_biet)
