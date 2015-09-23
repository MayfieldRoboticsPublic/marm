import pytest

import marm


@pytest.mark.parametrize(
    ('capture,pt,ssrc,packet_type,expected'), [
    ('streets-of-rage.pcap', 100, 3830765780, marm.vp8.VP8RTPPacket, 1239),
    ('streets-of-rage.pcap', 111, 4286666423, marm.opus.OpusRTPPacket, 490),
])
def test_extract_frames_from_pcap(
        fixtures,
        capture,
        pt,
        ssrc,
        packet_type,
        expected):

    c_path = fixtures.join(capture)
    with c_path.open('rb') as fo:
        pkts = marm.pcap.PCapRTPPacketReader(
            fo,
            packet_type=packet_type,
            packet_filter=lambda pkt: (
                pkt.header.type == pt and
                pkt.header.ssrc == ssrc
            )
        )
        count = 0
        for _ in pkts:
            count += 1
        assert count == expected


@pytest.mark.parametrize(
    ('capture,'
     'a_pt,a_ssrc,a_pkt_type,a_enc,'
     'v_pt,v_ssrc,v_pkt_type,v_enc,'
     'fmt,'
     'expected'), [
    ('streets-of-rage.pcap',
     111, 4286666423, marm.opus.OpusRTPPacket, 'libopus',
     100, 3830765780, marm.vp8.VP8RTPPacket, 'libvpx',
     'mkv',
     0),
])
def test_mux_frames_from_pcap(
        tmpdir,
        fixtures,
        capture,
        a_pt, a_ssrc, a_pkt_type, a_enc,
        v_pt, v_ssrc, v_pkt_type, v_enc,
        fmt,
        expected):
    c_path = fixtures.join(capture)
    m_path = tmpdir.join('m.{0}'.format(fmt))

    with m_path.open('wb') as m_fo, \
            c_path.open('rb') as a_fo, \
            c_path.open('rb') as v_fo:
        a_pkts = marm.pcap.PCapRTPPacketReader(
            a_fo,
            packet_type=a_pkt_type,
            packet_filter=lambda pkt: (
                pkt.header.type == a_pt and
                pkt.header.ssrc == v_ssrc
            )
        )
        a_pkts = marm.rtp.head_packets(a_pkts, duration=10)

        v_pkts = marm.pcap.PCapRTPPacketReader(
            v_fo,
            packet_type=v_pkt_type,
            packet_filter=lambda pkt: (
                pkt.header.type == v_pt and
                pkt.header.ssrc == v_ssrc
            )
        )
        v_frame_rate = marm.rtp.estimate_video_frame_rate(v_pkts)
        v_pkts.reset()
        v_width, v_height = marm.rtp.probe_video_dimensions(v_pkts)
        v_pkts.reset()
        v_pkts = marm.rtp.head_packets(v_pkts, duration=10)

        marm.mux_frames(
            m_fo,
            audio_profile={
                'encoder_name': a_enc,
                'bit_rate': 96000,
                'sample_rate': 48000,
            },
            audio_packets=marm.Frames(a_pkts),
            video_profile={
                'encoder_name': v_enc,
                'pix_fmt': marm.VideoFrame.PIX_FMT_YUV420P,
                'width': v_width,
                'height': v_height,
                'frame_rate': v_frame_rate,
                'bit_rate': 4000000,

            },
            video_packets=marm.VideoFrames(v_pkts),
        )

    with m_path.open('rb') as fo:
        m_stat = marm.stat_format(fo)
    assert m_stat.nb_streams == 2
    assert fmt in m_stat.iformat.extensions.split(',')
