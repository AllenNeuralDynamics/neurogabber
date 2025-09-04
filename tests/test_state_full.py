import copy
from neurogabber.backend.tools.neuroglancer_state import from_url, to_url, set_view, add_annotations
from neurogabber.examples.ng_state_dict import STATE_DICT


def test_round_trip_full_state():
    url = to_url(STATE_DICT)
    parsed = from_url(url)
    # Deterministic serialization: should match exactly for keys/values
    assert parsed == STATE_DICT


def test_set_view_preserves_extra_keys():
    state = copy.deepcopy(STATE_DICT)
    original_keys = set(state.keys())
    set_view(state, {"x": 10, "y": 11, "z": 12}, "fit", "xy")
    assert set(state.keys()) == original_keys  # no loss of top-level keys
    # If original had 4D position keep 4th component
    if len(STATE_DICT.get("position", [])) == 4:
        assert len(state["position"]) == 4


def test_add_annotations_does_not_remove_layers():
    state = copy.deepcopy(STATE_DICT)
    n_layers = len(state.get("layers", []))
    add_annotations(state, "TestAnn", [{"point": [1,2,3]}])
    assert len(state.get("layers", [])) == n_layers + 1