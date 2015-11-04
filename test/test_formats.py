import marm


def test_formats():
    assert isinstance(marm.frame.formats().next(), marm.frame.Format)
    assert any(c.name == 'matroska' for c in marm.frame.formats())
