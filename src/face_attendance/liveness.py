from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np


def ti_le_mat(points: list[tuple[int, int]]) -> float | None:
    """Tính Eye Aspect Ratio từ sáu mốc của một mắt."""
    if len(points) != 6:
        return None
    values = np.asarray(points, dtype=np.float64)
    ngang = float(np.linalg.norm(values[0] - values[3]))
    if ngang <= 1e-6:
        return None
    doc_1 = float(np.linalg.norm(values[1] - values[5]))
    doc_2 = float(np.linalg.norm(values[2] - values[4]))
    return (doc_1 + doc_2) / (2.0 * ngang)


@dataclass
class BoKiemTraChopMat:
    nguong_nham: float
    nguong_mo: float
    thoi_han_giay: float
    trang_thai: dict[int, str] = field(default_factory=dict)
    da_xac_minh_luc: dict[int, float] = field(default_factory=dict)

    def cap_nhat(self, student_id: int, ti_le: float | None) -> bool:
        if ti_le is None:
            return False
        luc_nay = time.monotonic()
        trang_thai = self.trang_thai.get(student_id, "can_mo")
        if trang_thai == "da_xac_minh":
            if luc_nay - self.da_xac_minh_luc.get(student_id, 0) <= self.thoi_han_giay:
                return True
            trang_thai = "can_mo"
        if trang_thai == "can_mo" and ti_le >= self.nguong_mo:
            trang_thai = "can_nham"
        elif trang_thai == "can_nham" and ti_le <= self.nguong_nham:
            trang_thai = "can_mo_lai"
        elif trang_thai == "can_mo_lai" and ti_le >= self.nguong_mo:
            trang_thai = "da_xac_minh"
            self.da_xac_minh_luc[student_id] = luc_nay
        self.trang_thai[student_id] = trang_thai
        return trang_thai == "da_xac_minh"

    def dat_lai(self, student_id: int) -> None:
        self.trang_thai.pop(student_id, None)
        self.da_xac_minh_luc.pop(student_id, None)
