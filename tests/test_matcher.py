from dataclasses import dataclass

import numpy as np
import pytest

from face_attendance.matcher import tim_danh_tinh_tot_nhat


@dataclass(frozen=True)
class Mau:
    student_id: int
    embedding: np.ndarray


def test_matcher_accepts_clear_identity() -> None:
    query = np.zeros(128)
    samples = [Mau(1, np.zeros(128)), Mau(2, np.ones(128))]
    result = tim_danh_tinh_tot_nhat(query, samples, 0.5, 0.05)
    assert result.mau is samples[0]


def test_matcher_rejects_ambiguous_identity() -> None:
    query = np.zeros(128)
    samples = [Mau(1, np.full(128, 0.01)), Mau(2, np.full(128, 0.011))]
    result = tim_danh_tinh_tot_nhat(query, samples, 0.5, 0.05)
    assert result.mau is None


def test_matcher_rejects_invalid_template() -> None:
    with pytest.raises(ValueError, match="Embedding mẫu"):
        tim_danh_tinh_tot_nhat(
            np.zeros(128), [Mau(1, np.zeros(127))], 0.5, 0.05
        )
