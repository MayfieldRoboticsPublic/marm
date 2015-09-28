import pytest

import marm


@pytest.mark.parametrize(
    'file_name,packet_type,expected', [
        ('sonic-a.mjr', marm.opus.OpusRTPPacket, 5996),
        ('sonic-v.mjr', marm.vp8.VP8RTPPacket, 9654),
    ]
)
def test_read_mjr(fixtures, file_name, packet_type, expected):
    path = fixtures.join(file_name)
    mjr = marm.mjr.MJRRTPPacketReader(path.open('rb'), packet_type=packet_type)
    assert sum(1 for _ in mjr) == expected
