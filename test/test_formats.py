import marm


def test_formats():
    assert any(c.name == 'matroska' for c in marm.formats())
