import marm


def test_codecs():
    assert isinstance(marm.frame.codecs().next(), marm.frame.Codec)
    assert any(c.name == 'mpeg4' for c in marm.frame.codecs())
    assert any(c.name == 'flac' for c in marm.frame.codecs())
