def test_package_importable():
    """Smoke: package imports cleanly."""
    import signalk_mcp
    assert signalk_mcp is not None
