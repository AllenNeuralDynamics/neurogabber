from neurogabber.backend.tools.neuroglancer_state import new_state, set_view, set_lut, add_annotations


def test_set_view_updates_position_and_scale():
    s = new_state()
    s2 = set_view(s, {"x": 5, "y": 6, "z": 7}, "fit", "xy")
    assert s2["position"] == [5, 6, 7]
    assert s2["crossSectionScale"] == 1.0


def test_add_annotations_appends_items():
    s = new_state()
    add_annotations(
        s,
        "ROIs",
        [
            {"point": [1, 2, 3], "id": "a"},
            {"type": "box", "point": [0, 0, 0], "size": [1, 2, 3], "id": "b"},
        ],
    )
    # Adding more should append
    add_annotations(s, "ROIs", [{"point": [4, 5, 6]}])
    ann_layers = [L for L in s["layers"] if L.get("type") == "annotation"]
    assert len(ann_layers) == 1
    anns = ann_layers[0]["source"]["annotations"]
    assert len(anns) == 3


def test_set_lut_no_error_when_layer_missing():
    s = new_state()
    # No exception if layer not present
    set_lut(s, "missing", 0.0, 1.0)
