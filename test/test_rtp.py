import inspect

import pytest

import marm


@pytest.mark.parametrize(
    ('stored,pt,ssrc,packet_type,min_window,frame_rate'), [
        ('sonic-v.mjr',
         100,
         1653789901,
         marm.vp8.VP8RTPPacket,
         10,
         31),
        ('streets-of-rage.pcap',
         100,
         3830765780,
         marm.vp8.VP8RTPPacket,
         10,
         21),
        ('streets-of-rage.pcap',
         100,
         3830765780,
         marm.vp8.VP8RTPPacket,
         10 ** 10,
         ValueError),
    ])
def test_rtp_estimate_video_frame_rate(
        fixtures,
        stored,
        pt,
        ssrc,
        packet_type,
        min_window,
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
        if inspect.isclass(frame_rate) and issubclass(frame_rate, Exception):
            with pytest.raises(frame_rate):
                marm.rtp.estimate_video_frame_rate(pkts, min_window=min_window)
        else:
            assert int(
                marm.rtp.estimate_video_frame_rate(pkts, min_window=min_window)
            ) == frame_rate


@pytest.mark.parametrize(
    ('stored,pt,ssrc,packet_type,width,height'), [
        ('sonic-v.mjr', 100, 1653789901, marm.vp8.VP8RTPPacket, 320, 240),
        ('streets-of-rage.pcap', 100, 3830765780, marm.vp8.VP8RTPPacket, 960,
         720),
    ])
def test_rtp_video_dimensions(
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


@pytest.mark.parametrize(
    ('v_store,v_count,v_p_kf, v_n_kf,a_store,a_count,dur,parts'), [
        ('sonic-v.mjr', 9654, [
            ((False, (0, 0), None, (None, None))),
            ((True, (0, 164), -5.899999999999636, (0, 204))),
            ((True, (1, 462), -0.8659999999999854, (1, 456))),
            ((True, (1, 462), -10.865999999999985, (1, 456))),
            ((True, (3, 250), -5.899999999999636, (3, 204))),
            ((True, (4, 621), -0.7999999999992724, (4, 460))),
            ((True, (4, 621), -10.799999999999272, (4, 460))),
            ((True, (6, 312), -5.798999999999978, (6, 210))),
            ((True, (7, 931), -0.7999999999992724, (7, 460))),
            ((True, (7, 931), -10.799999999999272, (7, 460))),
            ((True, (9, 574), -0.9659999999994398, (9, 451))),
            ((True, (10, 394), -6.8659999999999854, (10, 156))),
         ], [
            ((True, (0, 4), 0.052999999999883585, (0, 3))),
            ((True, (1, 462), 9.134000000000015, (1, 457))),
            ((True, (3, 250), 14.100000000000364, (3, 205))),
            ((True, (3, 250), 4.100000000000364, (3, 205))),
            ((True, (4, 621), 9.200000000000728, (4, 460))),
            ((True, (6, 312), 14.201000000000022, (6, 211))),
            ((True, (6, 312), 4.201000000000022, (6, 211))),
            ((True, (7, 931), 9.200000000000728, (7, 460))),
            ((True, (9, 403), 14.234000000000378, (9, 212))),
            ((True, (9, 403), 4.234000000000378, (9, 212))),
            ((True, (10, 2), 0.06700000000000728, (10, 4))),
            ((True, (11, 1069), 8.167000000000371, (11, 409))),
         ],
         'sonic-a.mjr', 5996,
         10.0, 12),
    ])
def test_rtp_cursor(
        tmpdir, fixtures,
        v_store, v_count, v_p_kf, v_n_kf,
        a_store, a_count,
        dur, parts):
    # split v
    v_path = fixtures.join(v_store)
    v_parts = 0
    v_pkts = marm.mjr.MJRRTPPacketReader(
        str(v_path),
        packet_type=marm.vp8.VP8RTPPacket
    )
    for i, part in enumerate(marm.rtp.split_packets(v_pkts, duration=dur)):
        t_path = tmpdir.join('v-{0}.mjr'.format(i + 1))
        with t_path.open('wb') as t_fo:
            marm.mjr.write_header(t_fo, 'video')
            for pkt in part:
                marm.mjr.write_packet(t_fo, pkt)
        v_parts += 1
    assert v_parts == parts

    # split a
    a_path = fixtures.join(a_store)
    a_parts = 0
    a_pkts = marm.mjr.MJRRTPPacketReader(
        str(a_path),
        packet_type=marm.opus.OpusRTPPacket
    )
    for i, part in enumerate(marm.rtp.split_packets(a_pkts, duration=dur)):
        t_path = tmpdir.join('a-{0}.mjr'.format(i + 1))
        with t_path.open('wb') as t_fo:
            marm.mjr.write_header(t_fo, 'audio')
            for pkt in part:
                marm.mjr.write_packet(t_fo, pkt)
        a_parts += 1
    assert a_parts == parts

    # cursors
    v_cur = marm.rtp.RTPCursor([
            str(tmpdir.join('v-{0}.mjr'.format(i + 1)))
            for i in range(v_parts)
        ],
        marm.mjr.MJRRTPPacketReader,
        packet_type=marm.vp8.VP8RTPPacket,
    )
    a_cur = marm.rtp.RTPCursor([
            str(tmpdir.join('a-{0}.mjr'.format(i + 1)))
            for i in range(a_parts)
        ],
        marm.mjr.MJRRTPPacketReader,
        packet_type=marm.opus.OpusRTPPacket,
    )

    # count packets
    assert sum(1 for _ in v_cur) == v_count
    assert sum(1 for _ in v_cur) == 1  # exhausted
    assert sum(1 for _ in a_cur) == a_count
    assert sum(1 for _ in a_cur) == 1  # exhausted

    # prev key-frames
    for i in range(v_parts):
        hit, v_tell, v_delta, a_tell = v_p_kf[i]
        v_cur.seek((i, 0))
        s_pkt = v_cur.current()
        pkt = v_cur.prev_key_frame()
        assert v_cur.tell() == v_tell
        if hit:
            assert pkt is not None and pkt.data.is_key_frame
            delta = pkt.secs - s_pkt.secs
            assert v_delta == delta
            a_cur.seek((i, 0))
            a_cur.rewind(-v_delta)
            assert a_cur.tell() == a_tell
        else:
            assert pkt is None

    # next key-frames
    for i in range(v_parts):
        (hit, v_tell, v_delta, a_tell) = v_n_kf[i]
        v_cur.seek((i, 0))
        s_pkt = v_cur.current()
        pkt = v_cur.next_key_frame()
        assert v_cur.tell() == v_tell
        if hit:
            assert pkt is not None and pkt.data.is_key_frame
            delta = pkt.secs - s_pkt.secs
            assert v_delta == delta
            a_cur.seek((i, 0))
            a_cur.fastforward(v_delta)
            assert a_cur.tell() == a_tell


@pytest.mark.parametrize(
    ('store,samples'), [
        ('sonic-a.mjr', 5756160),
        ('streets-of-rage.pcap', 706920),
    ],
)
def test_rtp_audio_samples(fixtures, tmpdir, store, samples):
    p = fixtures.join(store)
    pkts = marm.rtp.RTPPacketReader.open(
        p.strpath, packet_type=marm.opus.OpusRTPPacket,
    )
    assert sum(pkt.data.nb_samples for pkt in pkts) == samples


@pytest.mark.parametrize(
    ('src,pkt_type,expected'), [
        ('sonic-v.mjr', marm.vp8.VP8RTPPacket, {
             'bit_rate': 4000000,
             'frame_rate': 30.127814972610544,
             'height': 240,
             'pix_fmt': marm.frame.VideoFrame.PIX_FMT_YUV420P,
             'width': 320
         }),
        ('sonic-a.mjr', marm.opus.OpusRTPPacket, {
             'bit_rate': 96000,
             'channel_layout': 4,
             'sample_rate': 48000
         }),
    ],
)
def test_rtp_cursor_probe(fixtures, src, pkt_type, expected):
    src = fixtures.join(src)
    cur = marm.rtp.RTPCursor(
        [src.strpath],
        packet_type=pkt_type,
    )
    result = cur.probe()
    assert result == expected


@pytest.mark.parametrize(
    ('src,pkt_type,map_func,reduce_func,stop,cache,expected'), [
        ('sonic-a.mjr',
         marm.opus.OpusRTPPacket,
         lambda pkt: pkt.data.nb_samples * pkt.data.nb_channels,
         lambda x, y: x + y,
         None,
         True,
         5756162),
    ],
)
def test_rtp_cursor_compute(
        fixtures,
        src,
        pkt_type,
        map_func,
        reduce_func,
        stop,
        cache,
        expected):
    src = fixtures.join(src)
    cur = marm.rtp.RTPCursor([src.strpath], packet_type=pkt_type)
    with cur.restoring():
        assert cur.compute(map_func, reduce_func, stop, cache) == expected
    if cache:
        with cur.restoring():
            assert cur.compute(map_func, reduce_func, stop, cache) == expected


@pytest.mark.parametrize(
    ('srcs,pkt_type,expected'), [
        ([], marm.vp8.VP8RTPPacket, None),
        ([], marm.opus.OpusRTPPacket, None),
        (['sonic-v.mjr'], marm.vp8.VP8RTPPacket, 119.98599999999988),
        (['sonic-a.mjr'], marm.opus.OpusRTPPacket, 119.97999999999956),
    ],
)
def test_rtp_cursor_interval(fixtures, srcs, pkt_type, expected):
    cur = marm.rtp.RTPCursor(
        [fixtures.join(src).strpath for src in srcs],
        packet_type=pkt_type,
    )
    assert cur.interval() == expected


@pytest.mark.parametrize(
    ('srcs,pkt_type,empty,expected'), [
        (['empty.mjr', 'empty.mjr', 'sonic-v.mjr'],
         marm.vp8.VP8RTPPacket,
         False,
         1),
        (['empty.mjr', 'empty.mjr', 'sonic-v.mjr'],
         marm.vp8.VP8RTPPacket,
         True,
         3),
    ],
)
def test_rtp_cursor_empty(fixtures, srcs, pkt_type, empty, expected):
    cur = marm.rtp.RTPCursor(
        [fixtures.join(src).strpath for src in srcs],
        packet_type=pkt_type,
        empty=empty,
    )
    assert len(cur.parts) == expected


@pytest.mark.parametrize(
    ('srcs,pkt_type,expected'), [
        (['padded-v.mjr'], marm.vp8.VP8RTPPacket, {
             'pix_fmt': marm.VideoFrame.PIX_FMT_YUV420P,
             'width': 640,
             'height': 480,
             'bit_rate': 4000000,
             'frame_rate': 29.49940405244543,
         }),
    ],
)
def test_rtp_cursor_padded(fixtures, srcs, pkt_type, expected):
    cur = marm.rtp.RTPCursor(
        [fixtures.join(src).strpath for src in srcs],
        packet_type=pkt_type,
    )
    assert cur.probe() == expected
