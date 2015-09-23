import pytest

import marm


@pytest.mark.parametrize(
    ('stored,pt,ssrc,packet_type,frame_rate'), [
    ('sonic-v.mjr', 100, 1653789901, marm.vp8.VP8RTPPacket, 31),
    ('streets-of-rage.pcap', 100, 3830765780, marm.vp8.VP8RTPPacket, 21),
])
def test_estimate_video_frame_rate(
        fixtures,
        stored,
        pt,
        ssrc,
        packet_type,
        frame_rate):
    s_path = fixtures.join(stored)
    with s_path.open() as fo:
        pkts = marm.rtp.RTPPacketReader.open(
            fo,
            packet_filter=lambda pkt: (
                pkt.header.type == pt and pkt.header.ssrc == ssrc
            ),
            packet_type=packet_type,
        )
        assert int(marm.rtp.estimate_video_frame_rate(pkts)) == frame_rate


@pytest.mark.parametrize(
    ('stored,pt,ssrc,packet_type,width,height'), [
    ('sonic-v.mjr', 100, 1653789901, marm.vp8.VP8RTPPacket, 320, 240),
    ('streets-of-rage.pcap', 100, 3830765780, marm.vp8.VP8RTPPacket, 960, 720),
])
def test_video_dimensions(
        fixtures,
        stored,
        pt,
        ssrc,
        packet_type,
        width,
        height):
    s_path = fixtures.join(stored)
    with s_path.open() as fo:
        pkts = marm.rtp.RTPPacketReader.open(
            fo,
            packet_filter=lambda pkt: (
                pkt.header.type == pt and pkt.header.ssrc == ssrc
            ),
            packet_type=packet_type,
        )
        assert marm.rtp.probe_video_dimensions(pkts) == (width, height)
