import numpy as np
import pytest
from midminton.vision.models import heatmap_observation


def test_shuttle_confidence_belongs_to_selected_component():
    heatmap = np.zeros((288, 512), dtype=np.float32)
    heatmap[100:104, 200:204] = 0.51
    heatmap[10, 10] = 0.99
    observation = heatmap_observation(heatmap)
    assert observation["confidence"] == pytest.approx(0.51)
    assert observation["xy"] == pytest.approx([201.5/512, 101.5/288])


def test_empty_heatmap_remains_missing():
    assert heatmap_observation(np.zeros((288, 512), dtype=np.float32)) is None
