import itertools
import logging
import math

import pytest

import marm


logger = logging.getLogger(__name__)


@pytest.mark.parametrize(
    'mpegts,ccs', [
        ('sonic.ts', {0: 4, 17: 9, 4096: 4, 256: 2, 257: 8})
    ]
)
def test_mpegts_last_ccs(fixtures, mpegts, ccs):
    with fixtures.join(mpegts).open('rb') as fo:
        assert marm.frame.last_mpegts_ccs(fo) == ccs


@pytest.mark.parametrize(
    'v_mjr,v_pkt_type,frame_rate,'
    'a_mjr,a_pkt_type,sample_rate,'
    'time_range,time_cuts,'
    'stitches', [
        ('sonic-v.mjr', marm.vp8.VP8RTPPacket, '24',
         'sonic-a.mjr', marm.opus.OpusRTPPacket, '44100',
         (10, 55),
         [5, 6, 7, 10, 5], [
            # NOTE: manually check that stitched output is good (e.g. versus
            # full output `--mpegts-full`) and record stitches like this.
            {'a_cut': ((0, 0), (0, 250)),
             'a_first_pts': None,
             'a_range': (1, 214),
             'a_start_sample': None,
             'v_cut': ((0, 0), (0, 0), (0, 272), 0)},
            {'a_cut': ((0, 250), (0, 550)),
             'a_first_pts': 447216,
             'a_range': (16, 273),
             'a_start_sample': 997,
             'v_cut': ((0, 0), (0, 272), (0, 631), 149)},
            {'a_cut': ((0, 550), (0, 900)),
             'a_first_pts': 986383,
             'a_range': (16, 317),
             'a_start_sample': 553,
             'v_cut': ((0, 0), (0, 631), (0, 1065), 327)},
            {'a_cut': ((0, 900), (0, 1396)),
             'a_first_pts': 1617501,
             'a_range': (17, 443),
             'a_start_sample': 35,
             'v_cut': ((0, 875), (0, 1065), (0, 1721), 90)},
            {'a_cut': ((0, 1396), (0, 1646)),
             'a_first_pts': 2517044,
             'a_range': (16, 230),
             'a_start_sample': 906,
             'v_cut': ((0, 875), (0, 1721), (0, 2086), 390)},
            {'a_cut': ((0, 1646), (0, 2245)),
             'a_first_pts': 2966351,
             'a_range': (17, 531),
             'a_start_sample': 536,
             'v_cut': ((0, 1868), (0, 2086), (0, 2306), 87)}
         ]),
        ('sonic-v.mjr', marm.vp8.VP8RTPPacket, '24',
         'sonic-a.mjr', marm.opus.OpusRTPPacket, '44100',
         (0, 60),
         [11, 12, 12, 13], [
            {'a_cut': ((0, 0), (0, 550)),
             'a_first_pts': None,
             'a_range': (1, 472),
             'a_start_sample': None,
             'v_cut': ((0, 0), (0, 0), (0, 405), 0)},
            {'a_cut': ((0, 550), (0, 1150)),
             'a_first_pts': 986383,
             'a_range': (16, 532),
             'a_start_sample': 553,
             'v_cut': ((0, 160), (0, 405), (0, 1036), 166)},
            {'a_cut': ((0, 1150), (0, 1746)),
             'a_first_pts': 2066807,
             'a_range': (16, 528),
             'a_start_sample': 780,
             'v_cut': ((0, 824), (0, 1036), (0, 1764), 116)},
            {'a_cut': ((0, 1746), (0, 2396)),
             'a_first_pts': 3146075,
             'a_range': (16, 575),
             'a_start_sample': 389,
             'v_cut': ((0, 1699), (0, 1764), (0, 2606), 28)},
            {'a_cut': ((0, 2396), (0, 2995)),
             'a_first_pts': 4316361,
             'a_range': (16, 531),
             'a_start_sample': 541,
             'v_cut': ((0, 1699), (0, 2606), (0, 3498), 417)}
         ]),
        ('sonic-v.mjr', marm.vp8.VP8RTPPacket, '24',
         'sonic-a.mjr', marm.opus.OpusRTPPacket, '44100',
         (0, 15),
         [7.5], [
            {'a_cut': ((0, 0), (0, 375)),
             'a_first_pts': None,
             'a_range': (1, 321),
             'a_start_sample': None,
             'v_cut': ((0, 0), (0, 0), (0, 261), 0)},
            {'a_cut': ((0, 375), (0, 749)),
             'a_first_pts': 670824,
             'a_range': (16, 338),
             'a_start_sample': 255,
             'v_cut': ((0, 160), (0, 261), (0, 598), 60)}
         ]),
    ]
)
def test_mpegts_stitch_one(
        fixtures,
        tmpdir,
        v_mjr, v_pkt_type, frame_rate,
        a_mjr, a_pkt_type, sample_rate,
        time_range,
        time_cuts,
        stitches):
    # time slice mjr
    v_mjr = time_slice(
        tmpdir.join('v.mjr'), fixtures.join(v_mjr), v_pkt_type, time_range,
        sort=True,
    )
    a_mjr = time_slice(
        tmpdir.join('a.mjr'), fixtures.join(a_mjr), a_pkt_type, time_range,
        sort=True,
    )

    # v
    v_cur = marm.rtp.RTPCursor([v_mjr.strpath], packet_type=v_pkt_type)
    with v_cur.restoring():
        v_prof = v_cur.probe()
    v_prof.update({
        'encoder_name': 'libvpx',
        'time_base': (1, 1000),
    })
    with v_cur.restoring():
        v_clock = min(
            pkt.msecs for pkt in marm.rtp.head_packets(v_cur)
        )

    # a
    a_cur = marm.rtp.RTPCursor([a_mjr.strpath], packet_type=a_pkt_type)
    with a_cur.restoring():
        a_prof = a_cur.probe()
    a_prof.update({
        'encoder_name': 'libopus',
        'time_base': (1, 1000),
        'initial_padding': 0,
    })
    with a_cur.restoring():
        a_clock = min(
            pkt.msecs for pkt in marm.rtp.head_packets(a_cur)
        )

    # calculate cuts
    with v_cur.restoring(), a_cur.restoring():
        v_cuts, a_cuts = time_cut(v_cur, a_cur, *time_cuts)

    # segments
    tss, ss = [], []
    prev_ts = None
    for i, (v_cut, a_cut) in enumerate(zip(v_cuts, a_cuts)):
        ts, s = xcode_segment(
            tmpdir.join('ts-{0}.ts'.format(i)),
            v_cur, v_prof, v_clock,
            a_cur, a_prof, a_clock,
            v_cut,
            a_cut,
            frame_rate=frame_rate,
            sample_rate=sample_rate,
            prev_dst=prev_ts,
        )
        tss.append(ts)
        ss.append(s)
        logger.info('stitch %s=%s', pytest.pformat(s))
        prev_ts = ts

    # expected
    assert ss == stitches


@pytest.mark.parametrize(
    'v_mjr,v_pkt_type,frame_rate,'
    'a_mjr,a_pkt_type,sample_rate,'
    'time_range,'
    'time_cuts,'
    'stitches', [
        ('sonic-v.mjr', marm.vp8.VP8RTPPacket, '24',
         'sonic-a.mjr', marm.opus.OpusRTPPacket, '44100',
         (0, 20),
         [5, 6, 7], [
            {'a_cut': ((0, 0), (1, 0)),
             'a_first_pts': None,
             'a_range': (1, 214),
             'a_start_sample': None,
             'v_cut': ((0, 0), (0, 0), (0, 160), 0)},
            {'a_cut': ((1, 0), (2, 0)),
             'a_first_pts': 447216,
             'a_range': (16, 273),
             'a_start_sample': 997,
             'v_cut': ((0, 160), (0, 160), (1, 225), 0)},
            {'a_cut': ((2, 0), (3, 0)),
             'a_first_pts': 986383,
             'a_range': (16, 317),
             'a_start_sample': 553,
             'v_cut': ((0, 160), (1, 225), (2, 360), 166)},
            {'a_cut': ((3, 0), (3, 98)),
             'a_first_pts': 1617501,
             'a_range': (17, 100),
             'a_start_sample': 35,
             'v_cut': ((0, 160), (2, 360), (3, 91), 375)},
         ]),
        ('sonic-v.mjr', marm.vp8.VP8RTPPacket, '30',
         'sonic-a.mjr', marm.opus.OpusRTPPacket, '48k',
         (0, 40),
         [5, 6, 7, 3, 5], [
            {'a_cut': ((0, 0), (1, 0)),
             'a_first_pts': None,
             'a_range': (1, 233),
             'a_start_sample': None,
             'v_cut': ((0, 0), (0, 0), (0, 160), 0)},
            {'a_cut': ((1, 0), (2, 0)),
             'a_first_pts': 447360,
             'a_range': (18, 298),
             'a_start_sample': 384,
             'v_cut': ((0, 160), (0, 160), (1, 225), 0)},
            {'a_cut': ((2, 0), (3, 0)),
             'a_first_pts': 986880,
             'a_range': (18, 345),
             'a_start_sample': 128,
             'v_cut': ((0, 160), (1, 225), (2, 360), 166)},
            {'a_cut': ((3, 0), (4, 0)),
             'a_first_pts': 1616640,
             'a_range': (17, 157),
             'a_start_sample': 1024,
             'v_cut': ((0, 160), (2, 360), (3, 152), 375)},
            {'a_cut': ((4, 0), (5, 0)),
             'a_first_pts': 1887360,
             'a_range': (18, 251),
             'a_start_sample': 384,
             'v_cut': ((3, 55), (3, 152), (4, 289), 57)},
            {'a_cut': ((5, 0), (5, 694)),
             'a_first_pts': 2336640,
             'a_range': (17, 667),
             'a_start_sample': 1024,
             'v_cut': ((3, 55), (4, 289), (5, 851), 206)},
         ]),
    ]
)
def test_mpegts_stitch_many(
        fixtures,
        tmpdir,
        v_mjr, v_pkt_type, frame_rate,
        a_mjr, a_pkt_type, sample_rate,
        time_range,
        time_cuts,
        stitches):
    # slice mjrs
    v_mjr = time_slice(
        tmpdir.join('v.mjr'), fixtures.join(v_mjr), v_pkt_type, time_range,
        sort=True,
    )
    a_mjr = time_slice(
        tmpdir.join('a.mjr'), fixtures.join(a_mjr), a_pkt_type, time_range,
        sort=True,
    )

    # split mjrs
    v_mjrs, a_mjrs = time_split(
        tmpdir, v_mjr, v_pkt_type, a_mjr, a_pkt_type, *time_cuts
    )

    # v
    v_cur = marm.rtp.RTPCursor(
        [v_mjr.strpath for v_mjr in v_mjrs],
        packet_type=v_pkt_type
    )
    with v_cur.restoring():
        v_prof = v_cur.probe()
    v_prof.update({
        'encoder_name': 'libvpx',
        'time_base': (1, 1000),
    })
    with v_cur.restoring():
        v_clock = min(
            pkt.msecs for pkt in marm.rtp.head_packets(v_cur)
        )

    # a
    a_cur = marm.rtp.RTPCursor(
        [a_mjr.strpath for a_mjr in a_mjrs],
        packet_type=a_pkt_type
    )
    with a_cur.restoring():
        a_prof = a_cur.probe()
    a_prof.update({
        'encoder_name': 'libopus',
        'time_base': (1, 1000),
        'initial_padding': 0,
    })
    with a_cur.restoring():
        a_clock = min(
            pkt.msecs for pkt in marm.rtp.head_packets(a_cur)
        )

    # calculate cuts
    v_cuts, a_cuts = time_cut(v_cur, a_cur, *time_cuts)

    # segments
    ss = []
    tss = []
    prev_ts = None
    for i, (v_cut, a_cut) in enumerate(zip(v_cuts, a_cuts)):
        ts, s = xcode_segment(
            tmpdir.join('ts-{0}.ts'.format(i)),
            v_cur, v_prof, v_clock,
            a_cur, a_prof, a_clock,
            v_cut,
            a_cut,
            frame_rate=frame_rate,
            sample_rate=sample_rate,
            prev_dst=prev_ts,
        )
        tss.append(ts)
        ss.append(s)
        prev_ts = ts

    assert ss == stitches


@pytest.mark.parametrize(
    'v_mjr,v_pkt_type,frame_rate,'
    'a_mjr,a_pkt_type,sample_rate,'
    'time_range,time_cuts,window,'
    'stitches', [
        ('sonic-v.mjr', marm.vp8.VP8RTPPacket, '24',
         'sonic-a.mjr', marm.opus.OpusRTPPacket, '44100',
         (10, 70),
         [5] * 10,
         (4, 1, 0), [
            {'a_cut': ((0, 0), (0, 249)),
             'a_first_pts': None,
             'a_range': (1, 213),
             'a_start_sample': None,
             'v_cut': ((0, 0), (0, 0), (0, 272), 0)},
            {'a_cut': ((0, 249), (1, 249)),
             'a_first_pts': 445126,
             'a_range': (16, 230),
             'a_start_sample': 843,
             'v_cut': ((0, 0), (0, 272), (1, 297), 149)},
            {'a_cut': ((1, 249), (2, 249)),
             'a_first_pts': 894434,
             'a_range': (16, 231),
             'a_start_sample': 474,
             'v_cut': ((0, 0), (1, 297), (2, 316), 297)},
            {'a_cut': ((2, 249), (3, 245)),
             'a_first_pts': 1345830,
             'a_range': (17, 228),
             'a_start_sample': 103,
             'v_cut': ((2, 302), (2, 316), (3, 300), 1)},
            {'a_cut': ((3, 245), (4, 249)),
             'a_first_pts': 1796066,
             'a_range': (17, 231),
             'a_start_sample': 229,
             'v_cut': ((2, 302), (3, 300), (4, 321), 150)},
            {'a_cut': ((3, 249), (4, 249)),
             'a_first_pts': 2245370,
             'a_range': (16, 230),
             'a_start_sample': 973,
             'v_cut': ((1, 302), (3, 321), (4, 345), 300)},
            {'a_cut': ((3, 249), (4, 249)),
             'a_first_pts': 2694676,
             'a_range': (16, 231),
             'a_start_sample': 603,
             'v_cut': ((0, 302), (3, 345), (4, 377), 451)},
            {'a_cut': ((3, 249), (4, 249)),
             'a_first_pts': 3146073,
             'a_range': (17, 231),
             'a_start_sample': 233,
             'v_cut': ((3, 3), (3, 377), (4, 375), 147)},
            {'a_cut': ((3, 249), (4, 249)),
             'a_first_pts': 3595379,
             'a_range': (16, 230),
             'a_start_sample': 978,
             'v_cut': ((2, 3), (3, 375), (4, 363), 297)},
            {'a_cut': ((3, 249), (4, 249)),
             'a_first_pts': 4044687,
             'a_range': (16, 231),
             'a_start_sample': 608,
             'v_cut': ((1, 3), (3, 363), (4, 458), 446)},
            {'a_cut': ((3, 249), (4, 498)),
             'a_first_pts': 4496083,
             'a_range': (17, 445),
             'a_start_sample': 238,
             'v_cut': ((3, 4), (3, 458), (4, 75), 147)},
         ]),
        ('sonic-v.mjr', marm.vp8.VP8RTPPacket, None,
         'sonic-a.mjr', marm.opus.OpusRTPPacket, None,
         (10, 70),
         [6.5] * 7,
         (3, 2, 0), [
            {'a_cut': ((0, 0), (1, 324)),
             'a_first_pts': None,
             'a_range': (1, 607),
             'a_start_sample': None,
             'v_cut': ((0, 0), (0, 0), (1, 386), 0)},
            {'a_cut': ((1, 324), (3, 324)),
             'a_first_pts': 1165440,
             'a_range': (18, 623),
             'a_start_sample': 320,
             'v_cut': ((0, 0), (1, 386), (3, 422), 388)},
            {'a_cut': ((2, 324), (4, 324)),
             'a_first_pts': 2336160,
             'a_range': (18, 626),
             'a_start_sample': 704,
             'v_cut': ((1, 121), (2, 422), (4, 492), 330)},
            {'a_cut': ((2, 324), (4, 723)),
             'a_first_pts': 3505440,
             'a_range': (18, 1000),
             'a_start_sample': 320,
             'v_cut': ((1, 283), (2, 492), (4, 491), 266)},
         ]),
    ]
)
def test_mpegts_stitch_window(
        tmpdir,
        fixtures,
        mpegts_full,
        v_mjr, v_pkt_type, frame_rate,
        a_mjr, a_pkt_type, sample_rate,
        time_range,
        time_cuts,
        window,
        stitches):
    # slice mjrs
    v_mjr = time_slice(
        tmpdir.join('v.mjr'),
        fixtures.join(v_mjr), v_pkt_type, time_range,
        sort=True,
    )
    a_mjr = time_slice(
        tmpdir.join('a.mjr'),
        fixtures.join(a_mjr), a_pkt_type, time_range,
        sort=True,
    )

    # split mjrs
    v_mjrs, a_mjrs = time_split(
        tmpdir,
        v_mjr, v_pkt_type,
        a_mjr, a_pkt_type,
        *time_cuts
    )

    # v
    v_cur = marm.rtp.RTPCursor(
        [v_mjr.strpath for v_mjr in v_mjrs],
        packet_type=v_pkt_type
    )
    with v_cur.restoring():
        v_prof = v_cur.probe()
    v_prof.update({
        'encoder_name': 'libvpx',
        'time_base': (1, 1000),
    })
    with v_cur.restoring():
        v_clock = min(
            pkt.msecs for pkt in marm.rtp.head_packets(v_cur)
        )

    # a
    a_cur = marm.rtp.RTPCursor(
        [a_mjr.strpath for a_mjr in a_mjrs],
        packet_type=a_pkt_type
    )
    with a_cur.restoring():
        a_prof = a_cur.probe()
    a_prof.update({
        'encoder_name': 'libopus',
        'time_base': (1, 1000),
        'initial_padding': 0,
    })
    with a_cur.restoring():
        a_clock = min(
            pkt.msecs for pkt in marm.rtp.head_packets(a_cur)
        )

    # full
    if mpegts_full:
        v_cuts, a_cuts = time_cut(v_cur, a_cur)
        ts_full, _ = xcode_full(
            tmpdir.join('f.ts'),
            v_cur, v_prof, v_clock,
            a_cur, a_prof, a_clock,
            (v_cuts[0][0], v_cuts[0][1], v_cuts[-1][2], v_cuts[0][3]),
            (a_cuts[0][0], a_cuts[-1][1]),
            frame_rate=frame_rate,
            sample_rate=sample_rate,
        )
        logger.info('full=%s', ts_full)

    # segments
    tss, ss = [], []
    prev_ts = None
    lead, size, lag = window
    total = len(v_mjrs)
    for j, i in enumerate(range(0, total, size)):
        # window
        l, u = max(0, i - lead), min(total, i + size - 1 + lag)
        v_wnd = [mjr.strpath for mjr in v_mjrs[l:u + 1]]
        a_wnd = [mjr.strpath for mjr in a_mjrs[l:u + 1]]
        b = i - l
        e = min(b + size, len(v_wnd))

        # v
        v_cur = marm.rtp.RTPCursor(v_wnd, packet_type=v_pkt_type)
        v_cur.seek((b, 0))
        with v_cur.restoring():
            v_delta = v_cur.interval((e, 0)) if e != len(v_wnd) else None
        v_start, _, v_stop, _ = v_cur.time_cut(0, v_delta, align='prev')
        v_cur.seek(v_start)
        if v_cur.current().data.is_key_frame:
            v_key = v_start
        else:
            v_cur.prev_key_frame()
            v_key = v_cur.tell()
        v_cur.seek(v_key)
        v_drop = v_cur.count(v_start, lambda pkt: pkt.data.is_start_of_frame)

        # a
        a_cur = marm.rtp.RTPCursor(a_wnd, packet_type=a_pkt_type)
        a_cur.seek((b, 0))
        with a_cur.restoring():
            a_delta = a_cur.interval((e, 0)) if e != len(a_wnd) else None
        a_start, _, a_stop, _ = a_cur.time_cut(0, a_delta, align='prev')

        # xcode
        ts, s = xcode_segment(
            tmpdir.join('c-{0:03}.ts'.format(j)),
            v_cur, v_prof, v_clock,
            a_cur, a_prof, a_clock,
            (v_key, v_start, v_stop, v_drop),
            (a_start, a_stop),
            frame_rate=frame_rate,
            sample_rate=sample_rate,
            prev_dst=prev_ts,
        )
        tss.append(ts)
        ss.append(s)
        logger.info('stitch[%s]=%s', j, s)
        prev_ts = ts

    assert stitches == ss

    # concat
    if mpegts_full:
        ts = concat(tmpdir.join('c.ts'), *tss)
        logger.info('concat=%s', ts_full)


@pytest.mark.parametrize(
    'v_store,v_pkt,v_enc,frame_rate,'
    'a_store,a_pkt,a_enc,sample_rate,'
    'time_range,interval,delta,'
    'ccs', [
        ('sonic-v.mjr', marm.vp8.VP8RTPPacket, 'libvpx', '24',
         'sonic-a.mjr', marm.opus.OpusRTPPacket, 'libopus', '44100',
         (0, 30),
         5,
         1.0,
         {0: 11, 17: 1, 4096: 11, 256: 3, 257: 5}),
    ]
)
def test_mpegts_segment(
        fixtures,
        tmpdir,
        v_store, v_pkt, v_enc, frame_rate,
        a_store, a_pkt, a_enc, sample_rate,
        time_range,
        interval,
        delta,
        ccs):
    # time slice src
    v_src = time_slice(
        tmpdir.join('v.mjr'),
        fixtures.join(v_store), v_pkt,
        time_range,
        sort=True,
    )
    a_src = time_slice(
        tmpdir.join('a.mjr'),
        fixtures.join(a_store), a_pkt,
        time_range,
        sort=True,
    )

    # v
    v_cur = marm.rtp.RTPCursor([v_src.strpath], packet_type=v_pkt)
    with v_cur.restoring():
        v_prof = v_cur.probe()
    v_prof.update({
        'encoder_name': v_enc,
        'time_base': (1, 1000),
    })
    with v_cur.restoring():
        v_clock = min(
            pkt.msecs for pkt in marm.rtp.head_packets(v_cur)
        )

    # a
    a_cur = marm.rtp.RTPCursor([a_src.strpath], packet_type=a_pkt)
    with a_cur.restoring():
        a_prof = a_cur.probe()
    a_prof.update({
        'encoder_name': a_enc,
        'time_base': (1, 1000),
        'initial_padding': 0,
    })
    with a_cur.restoring():
        a_clock = min(
            pkt.msecs for pkt in marm.rtp.head_packets(a_cur)
        )

    # calculate cuts
    v_cuts, a_cuts = time_cut(v_cur, a_cur)

    # full
    full, _ = xcode_full(
        tmpdir.join('f.ts'),
        v_cur, v_prof, v_clock,
        a_cur, a_prof, a_clock,
        v_cuts[0],
        a_cuts[0],
        ccs=ccs,
        frame_rate=frame_rate,
        sample_rate=sample_rate,
    )
    with full.open('rb') as fo:
        full_last_ccs = marm.frame.last_mpegts_ccs(fo)

    # split full -> segments
    with full.open('rb') as sfo:
        marm.frame.segment(
            tmpdir.join('s-%03d.ts').strpath,
            'mpegts',
            sfo,
            time=interval,
            time_delta=1 / (1 * 25.0),
            mpegts_ccs=ccs,
            options=[
                ('copyts', '1'),
                ('mpegts_copyts', '1'),
                ('avoid_negative_ts', '0'),
            ],
        )

    # check segment packets
    for s in sorted(tmpdir.listdir('s-*.ts')):
        s_pkts = marm.FFProbe.for_packets(s, bucket=True)

        # videos start w/ keyframe
        assert all(
            s_pkts[idx][0]['flags'] == 'K_'
            for idx in s_pkts.keys() if s_pkts[idx][0]['codec_type'] == 'video'
        )

        # durations are close to interval
        assert all(
            abs(interval - (
                float(pkts[-1]['pts_time']) - float(pkts[0]['pts_time'])
            )) < delta
            for pkts in s_pkts.values()[:-1]
        )

    # check segment ccs
    with sorted(tmpdir.listdir('s-*.ts'))[-1].open('rb') as fo:
        assert marm.frame.last_mpegts_ccs(fo) == full_last_ccs

    # concat segments
    concat = tmpdir.join('c.ts')
    with concat.open('wb') as dfo:
        for rseg in sorted(tmpdir.listdir('s-*.ts')):
            with rseg.open('rb') as sfo:
                dfo.write(sfo.read())

    # and compare to full
    full_pkts = marm.FFProbe.for_packets(
        full, bucket=True, munge=lambda p: p['pts']
    )
    concat_pkts = marm.FFProbe.for_packets(
        concat, bucket=True, munge=lambda p: p['pts']
    )
    assert full_pkts == concat_pkts


# helpers

def mux(dst, v_cur, v_prof, v_clock, v_cut, a_cur, a_prof, a_clock, a_cut):
    # setup v
    v_key, v_start, v_stop, _ = v_cut
    v_cur.seek(v_start)
    assert v_cur.tell() == v_start
    assert v_cur.current().data.is_start_of_frame
    v_cur.seek(v_key)
    assert v_cur.tell() == v_key
    assert v_cur.current().data.is_key_frame
    v_frames = marm.VideoFrames(v_cur.slice(v_stop), -v_clock)

    # setup a
    a_start, a_stop = a_cut
    a_cur.seek(a_start)
    assert a_cur.tell() == a_start
    a_frames = marm.Frames(a_cur.slice(a_stop), -a_clock)

    with dst.open('wb') as fo:
        marm.frame.mux(
            fo,
            video_profile=v_prof,
            video_packets=v_frames,
            audio_profile=a_prof,
            audio_packets=a_frames,
        )
        assert v_cur.tell() == v_stop
        assert v_cur.current().data.is_start_of_frame
        assert a_cur.tell() == a_stop

    return dst


def time_slice(
        dst_path,
        src_path,
        pkt_type,
        (b_secs, e_secs),
        align=True,
        sort=False):
    cur = marm.rtp.RTPCursor(
        [src_path.strpath],
        marm.rtp.RTPPacketReader.open,
        packet_type=pkt_type,
    )
    _, _, pkts = cur.time_slice(b_secs, e_secs, align=align)
    with dst_path.open('wb') as fo:
        marm.mjr.write_header(fo, {
            pkt_type.AUDIO_TYPE: marm.mjr.AUDIO_TYPE,
            pkt_type.VIDEO_TYPE: marm.mjr.VIDEO_TYPE,
        }[pkt_type.type])
        pkts = list(pkts)
        if sort:
            pkts.sort(key=lambda pkt: pkt.msecs)
        for pkt in pkts:
            marm.mjr.write_packet(fo, pkt)
    return dst_path


def time_split(
        tmpdir,
        v_mjr, v_pkt_type,
        a_mjr, a_pkt_type,
        *deltas):
    v_mjrs, a_mjrs = [], []
    o = 0
    for i, d in enumerate(list(deltas) + [sum(deltas)]):
        v_dst_mjr = tmpdir.join('c-{0}-v.mjr'.format(i))
        time_slice(
            v_dst_mjr, v_mjr, v_pkt_type,
            (o, o + d),
            align=False,
        )
        v_mjrs.append(v_dst_mjr)
        a_dst_mjr = tmpdir.join('c-{0}-a.mjr'.format(i))
        time_slice(
            a_dst_mjr, a_mjr, a_pkt_type,
            (o, o + d),
            align=False,
        )
        a_mjrs.append(a_dst_mjr)
        o += d
    return v_mjrs, a_mjrs


def time_cut(v_cur, a_cur, *deltas):
    v_cuts, a_cuts = [], []

    interval = max(v_cur.interval(), a_cur.interval())
    deltas = list(deltas) + [interval - sum(deltas)]
    off = 0
    for delta in deltas:
        # v
        v_cur.seek((0, 0))
        v_start, _, v_stop, _ = v_cur.time_cut(off, off + delta)
        v_cur.seek(v_start)
        if v_cur.current().data.is_key_frame:
            v_key = v_start
        else:
            v_cur.prev_key_frame()
            v_key = v_cur.tell()
        v_cur.seek(v_key)
        v_drop = v_cur.count(v_start, lambda pkt: pkt.data.is_start_of_frame)
        v_cuts.append((v_key, v_start, v_stop, v_drop))

        # a
        a_cur.seek((0, 0))
        a_start, _, a_stop, _ = a_cur.time_cut(off, off + delta)
        a_cuts.append((a_start, a_stop))

        off += delta

    return v_cuts, a_cuts


def xcode_full(
        dst,
        v_cur, v_prof, v_clock,
        a_cur, a_prof, a_clock,
        (v_key, v_start, v_stop, v_drop),
        (a_start, a_stop),
        key_frame_rate=5.0,
        ccs=None,
        frame_rate=None,
        sample_rate=None):
    # mux to src
    mkv = mux(
        dst.dirpath('{0}.mkv'.format(dst.purebasename)),
        v_cur, v_prof, v_clock, (v_key, v_start, v_stop, v_drop),
        a_cur, a_prof, a_clock, (a_start, a_stop),
    )

    # xcode src to padded dst
    tsp = dst.dirpath('{0}-p{1}'.format(dst.purebasename, dst.ext))
    v_filter = ['select=gte(n\,{0})'.format(v_drop)]
    if frame_rate is not None:
        v_filter.append('fps={0}'.format(frame_rate))
    v_filter = ','.join(v_filter)
    a_filter = []
    if sample_rate:
        a_filter.append('aresample={0}'.format(sample_rate))
    a_filter = ','.join(a_filter)
    xcode = marm.FFMPEG([
        '-y',
        '-i', mkv.strpath,

        '-c:v', 'h264',
        '-crf', '28',
        '-preset', 'veryfast',
        ] + (['-filter:v', v_filter] if v_filter else []) + [
        '-force_key_frames', 'expr:gte(t,n_forced*{0})'.format(key_frame_rate),

        '-c:a', 'aac', '-strict', '-2',
        ] + (['-filter:a', a_filter] if a_filter else []) + [
        '-b:a', '22k',

        '-copyts',
        '-mpegts_copyts', '1',
        '-avoid_negative_ts', '0',
        tsp.strpath,
    ])
    xcode()

    # remux padded dst to dst
    a_range = (
        # drop first audio packet (audio codec priming samples)
        1,
        # drop last *2* audio packets (to be included in *next* "cut")
        marm.FFProbe.for_packet_count(
            '-select_streams', 'a', tsp.strpath
        )[1] - 3
    )
    with tsp.open('rb') as sfo, dst.open('wb') as dfo:
        marm.frame.remux(
            dfo, sfo,
            marm.FrameFilter.range(1, *a_range),
            mpegts_ccs=ccs,
            options=[
                ('copyts', '1'),
                ('mpegts_copyts', '1'),
                ('avoid_negative_ts', '0'),
            ],
        )

    stitch = {
        'v_cut': (v_key, v_start, v_stop, v_drop),
        'a_cut': (a_start, a_stop),
        'a_first_pts': None,
        'a_start_sample': None,
        'a_range': a_range,
    }

    return dst, stitch


def xcode_segment(
        dst,
        v_cur, v_prof, v_clock,
        a_cur, a_prof, a_clock,
        (v_key, v_start, v_stop, v_drop),
        (a_start, a_stop),
        key_frame_rate=5.0,
        frame_rate=None,
        sample_rate=None,
        prev_dst=None):
    mkv = dst.dirpath('{0}.mkv'.format(dst.purebasename))
    dstp = dst.dirpath('{0}-p{1}'.format(dst.purebasename, dst.ext))

    # xcode v filter
    v_filter = ['select=gte(n\,{0})'.format(v_drop)]
    if frame_rate is not None:
        v_filter.append('fps={0}'.format(frame_rate))

    # xcode a filter
    a_filter = []
    if sample_rate:
        a_filter.append('aresample={0}'.format(sample_rate))

    if prev_dst is None:
        # mux to src
        a_cur.seek(a_start)
        a_frames = marm.Frames(a_cur.slice(a_stop), -a_clock)
        v_cur.seek(v_key)
        v_frames = marm.VideoFrames(v_cur.slice(v_stop), -v_clock)
        with mkv.open('wb') as fo:
            marm.frame.mux(
                fo,
                audio_profile=a_prof,
                audio_packets=a_frames,
                video_profile=v_prof,
                video_packets=v_frames,
            )

        # xcode src to padded dest
        v_f = ','.join(v_filter)
        a_f = ','.join(a_filter)
        xcode = marm.FFMPEG([
            '-y',
            '-i', mkv.strpath,

            '-c:v', 'h264',
            '-crf', '28',
            '-preset', 'veryfast',
            ] + (['-filter:v', v_f] if v_f else []) + [
            '-force_key_frames', 'expr:gte(t,n_forced*{0})'.format(
                key_frame_rate
            ),

            '-c:a', 'aac', '-strict', '-2',
            ] + (['-filter:a', a_f] if a_f else []) + [
            '-b:a', '22k',

            '-copyts',
            '-mpegts_copyts', '1',
            '-avoid_negative_ts', '0',
            dstp.strpath,
        ])
        xcode()

        # remux padded dst to dst
        a_range = (
            # drop first a packet (audio codec priming samples)
            1,
            # drop last *2* a packets (included in *next* segment)
            marm.FFProbe.for_packet_count(
                '-select_streams', 'a', dstp.strpath
            )[1] - 3
        )
        with dstp.open('rb') as sfo, dst.open('wb') as dfo:
            marm.frame.remux(
                dfo, sfo,
                marm.FrameFilter.range(1, *a_range),
                options=[
                    ('copyts', '1'),
                    ('mpegts_copyts', '1'),
                    ('avoid_negative_ts', '0'),
                ],
            )

        stitch = {
            'v_cut': (v_key, v_start, v_stop, v_drop),
            'a_cut': (a_start, a_stop),
            'a_first_pts': None,
            'a_start_sample': None,
            'a_range': a_range,
        }
    else:
        # expected first a packet pts
        l = marm.FFProbe.for_last_packet(
            '-select_streams', 'a', prev_dst.strpath
        )[1]
        a_first_pts = l['pts'] + l['duration']

        # compute a start sample so we land ~ there
        a_cur.seek(a_start)
        a_cur.seek(-20)
        a_frames = marm.Frames(a_cur.slice(60), -a_clock)
        with mkv.open('wb') as fo:
            marm.frame.mux(fo, audio_profile=a_prof, audio_packets=a_frames)
        a_f = ','.join(a_filter)
        xcode = marm.FFMPEG([
            '-y',
            '-i', mkv.strpath,

            '-c:a', 'aac', '-strict', '-2',
            ] + (['-filter:a', a_f] if a_f else []) + [
            '-b:a', '22k',

            '-copyts',
            '-mpegts_copyts', '1',
            '-avoid_negative_ts', '0',
            dstp.strpath,
        ])
        xcode()
        with dstp.open('rb') as sfo, dst.open('wb') as dfo:
            marm.frame.remux(
                dfo, sfo,
                # drop first a packet (audio codec priming samples)
                marm.FrameFilter.range(0, 1),
                options=[
                    ('copyts', '1'),
                    ('mpegts_copyts', '1'),
                ],
            )
        pkt = (
            pkt for pkt in marm.FFProbe.for_packets(dst.strpath)[0]
            if pkt['pts'] <= a_first_pts <= pkt['pts'] + pkt['duration']
        ).next()
        a_stream = marm.FFProbe.for_streams(
            '-select_streams', 'a', dst.strpath
        )[0]
        a_tb = map(float, a_stream['time_base'])
        a_stream = marm.FFProbe.for_streams(
            '-select_streams', 'a', mkv.strpath
        )[0]
        a_sr = float(a_stream['sample_rate'])
        a_start_sample = int(math.ceil((
            (a_first_pts - pkt['pts']) / a_tb[1]) * a_sr
        ))

        # mux to src
        a_cur.seek(a_start)
        a_cur.seek(-20)
        a_frames = marm.Frames(a_cur.slice(a_stop), -a_clock)
        v_cur.seek(v_key)
        v_frames = marm.VideoFrames(v_cur.slice(v_stop), -v_clock)
        with mkv.open('wb') as fo:
            marm.frame.mux(
                fo,
                audio_profile=a_prof,
                audio_packets=a_frames,
                video_profile=v_prof,
                video_packets=v_frames,
            )

        # xcode src to padded dst
        a_filter.insert(0, 'atrim=start_sample={0}'.format(a_start_sample))
        v_f = ','.join(v_filter)
        a_f = ','.join(a_filter)
        xcode = marm.FFMPEG([
            '-y',
            '-i', mkv.strpath,

            '-c:v', 'h264',
            '-crf', '23',
            '-preset', 'medium',
            ] + (['-filter:v', v_f] if v_f else []) + [
            '-force_key_frames', 'expr:gte(t,n_forced*{0})'.format(
                key_frame_rate
            ),

            '-c:a', 'aac', '-strict', '-2',
            ] + (['-filter:a', a_f] if a_f else []) + [
            '-b:a', '22k',

            '-copyts',
            '-mpegts_copyts', '1',
            '-avoid_negative_ts', '0',
            dstp.strpath,
        ])
        xcode()

        # remux padded dst to dst
        a_drop = sum(1 for _ in itertools.takewhile(
            lambda pkt: pkt['pts'] < a_first_pts,
            marm.FFProbe.for_packets('-select_streams', 'a', dstp.strpath)[1]
        ))
        with prev_dst.open('rb') as fo:
            ccs = marm.frame.last_mpegts_ccs(fo)
        a_range = (
            # drop all a packets until we reach expected *first*
            a_drop,
            # drop last *2* a packets (to be included in *next*)
            marm.FFProbe.for_packet_count(
                '-select_streams', 'a', dstp.strpath
            )[1] - 3
        )
        with dstp.open('rb') as sfo, dst.open('wb') as dfo:
            marm.frame.remux(
                dfo, sfo,
                marm.FrameFilter.range(1, *a_range),
                # restore mpegts count continuity across "cuts"
                mpegts_ccs=ccs,
                options=[
                    ('copyts', '1'),
                    ('mpegts_copyts', '1'),
                    ('avoid_negative_ts', '0'),
                ],
            )

        stitch = {
            'v_cut': (v_key, v_start, v_stop, v_drop),
            'a_cut': (a_start, a_stop),
            'a_first_pts': a_first_pts,
            'a_start_sample': a_start_sample,
            'a_range': a_range,
        }

    return dst, stitch


def concat(dst, *srcs):
    with dst.open('wb') as dfo:
        for src in srcs:
            with src.open('rb') as sfo:
                dfo.write(sfo.read())
    return dst
