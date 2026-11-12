import pytest
from midminton.vision.geometry import Court


def test_court_corners_and_center_map_to_plane():
    court = Court([[0.1, 0.9], [0.9, 0.9], [0.7, 0.2], [0.3, 0.2]])
    assert court.project([0.1, 0.9]) == pytest.approx([0, 0])
    assert court.project([0.7, 0.2]) == pytest.approx([1, 1])
    assert court.contains([0.5, 0.5])
    assert not court.contains([0.99, 0.1])


def test_crossed_or_degenerate_court_is_rejected():
    with pytest.raises(ValueError):
        Court([[0, 0], [1, 1], [1, 0], [0, 1]])
    with pytest.raises(ValueError):
        Court([[0, 0]]*4)
