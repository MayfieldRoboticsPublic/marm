import marm


def test_formats():
    assert isinstance(marm.formats().next(), marm.Format)
    assert any(c.name == 'matroska' for c in marm.formats())
