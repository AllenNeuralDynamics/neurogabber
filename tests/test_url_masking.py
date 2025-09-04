from neurogabber.backend.main import _mask_ng_urls


def test_mask_single_url():
    raw = "Here is a link: https://neuroglancer-demo.appspot.com/#!%7Babc123"  # truncated pattern-like
    masked = _mask_ng_urls(raw)
    assert "Updated Neuroglancer view" in masked
    assert "neuroglancer-demo" in masked  # hyperlink form retains URL inside markdown


def test_mask_multiple_urls():
    u1 = "https://neuroglancer-demo.appspot.com/#!%7Bfirst"
    u2 = "https://neuroglancer-demo.appspot.com/#!%7Bsecond"
    raw = f"Links: {u1} and also {u2} again {u1}"
    masked = _mask_ng_urls(raw)
    # First label appears once, second gets (2)
    assert masked.count("Updated Neuroglancer view") >= 1
    assert "Updated Neuroglancer view (2)" in masked
    # Ensure each URL is now wrapped in markdown link form
    assert f"]({u1})" in masked
    assert f"]({u2})" in masked