import pytest

from face_attendance.liveness import BoKiemTraChopMat


def test_blink_requires_open_closed_open_cycle() -> None:
    checker = BoKiemTraChopMat(0.19, 0.23, 10)
    assert not checker.cap_nhat(1, 0.25)
    assert not checker.cap_nhat(1, 0.15)
    assert checker.cap_nhat(1, 0.25)
    checker.dat_lai(1)
    assert not checker.cap_nhat(1, 0.25)


def test_blink_thresholds_must_be_ordered() -> None:
    with pytest.raises(ValueError, match="Ngưỡng nhắm mắt"):
        BoKiemTraChopMat(0.3, 0.2, 10)
