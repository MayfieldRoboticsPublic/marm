import pytest

import marm


@pytest.mark.parametrize('file_name,packet_type,type,packet_count,', [
        ('sonic-a.mjr', marm.opus.OpusRTPPacket, 'video', 5996),
        ('sonic-v.mjr', marm.vp8.VP8RTPPacket, 'video', 9654),
    ])
def test_read_mjr(fixtures, file_name, packet_type, type, packet_count):
    path = fixtures.join(file_name)
    mjr = marm.mjr.MJRRTPPacketReader(path.open('rb'), packet_type=packet_type)
    count = 0
    for _ in mjr:
        count += 1
    assert packet_count == count
