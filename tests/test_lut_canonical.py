from neurogabber.backend.tools.neuroglancer_state import set_lut


def test_set_lut_creates_normalized_range():
    state = {"layers": [
        {"type": "image", "name": "vol", "source": "precomputed://dummy"}
    ]}
    set_lut(state, 'vol', 2, 9)
    layer = state['layers'][0]
    assert 'shaderControls' in layer
    assert 'normalized' in layer['shaderControls']
    assert layer['shaderControls']['normalized']['range'] == [2, 9]


def test_set_lut_updates_existing():
    state = {"layers": [
        {"type": "image", "name": "vol", "source": "precomputed://dummy",
         "shaderControls": {"normalized": {"range": [0,1], "otherKey": 5}}}
    ]}
    set_lut(state, 'vol', 10, 20)
    rng = state['layers'][0]['shaderControls']['normalized']['range']
    assert rng == [10, 20]
    # Ensure unrelated keys preserved
    assert state['layers'][0]['shaderControls']['normalized']['otherKey'] == 5