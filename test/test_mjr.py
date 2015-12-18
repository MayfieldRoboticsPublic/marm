import pytest

import marm


@pytest.mark.parametrize(
    'file_name,packet_type,expected', [
        ('sonic-a.mjr', marm.opus.OpusRTPPacket, 5996),
        ('sonic-v.mjr', marm.vp8.VP8RTPPacket, 9654),
    ]
)
def test_mjr_read(fixtures, file_name, packet_type, expected):
    path = fixtures.join(file_name)
    mjr = marm.mjr.MJRRTPPacketReader(path.open('rb'), packet_type=packet_type)
    assert sum(1 for _ in mjr) == expected


@pytest.mark.parametrize(
    'file_name,packet_type,expected', [
        ('empty.mjr', marm.vp8.VP8RTPPacket, True),
        ('sonic-a.mjr', marm.opus.OpusRTPPacket, False),
        ('sonic-v.mjr', marm.vp8.VP8RTPPacket, False),
    ]
)
def test_mjr_empty(fixtures, file_name, packet_type, expected):
    path = fixtures.join(file_name)
    mjr = marm.mjr.MJRRTPPacketReader(path.open('rb'), packet_type=packet_type)
    assert mjr.is_empty is expected
