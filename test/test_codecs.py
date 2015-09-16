import marm


def test_codecs():
    assert any(c.name == 'mpeg4' for c in marm.codecs())
    assert any(c.name == 'flac' for c in marm.codecs())
