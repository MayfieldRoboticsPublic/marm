import itertools

import pytest

import marm


@pytest.mark.parametrize(
    'mpegts,ccs', [
        ('sonic.ts', {0: 4, 17: 9, 4096: 4, 256: 2, 257: 8})
    ]
)
def test_mpegts_last_ccs(fixtures, mpegts, ccs):
    with fixtures.join(mpegts).open('rb') as fo:
        assert marm.frame.last_mpegts_ccs(fo) == ccs


@pytest.mark.parametrize(
    'v_mjr,v_pkt_type,a_mjr,a_pkt_type,time_slice,time_cuts', [
        ('sonic-v.mjr', marm.vp8.VP8RTPPacket,
         'sonic-a.mjr', marm.opus.OpusRTPPacket,
         (0, 60),
         [11, 12, 12, 13]),
        ('sonic-v.mjr', marm.vp8.VP8RTPPacket,
         'sonic-a.mjr', marm.opus.OpusRTPPacket,
         (0, 15),
         [7.5]),
    ]
)
def test_mpegts_stitch_one(
        fixtures,
        tmpdir,
        v_mjr, v_pkt_type,
        a_mjr, a_pkt_type,
        time_slice,
        time_cuts):
    # time slice mjr
    v_mjr = pytest.time_slice(
        tmpdir.join('v.mjr'),
        fixtures.join(v_mjr), v_pkt_type, time_slice,
    )
    a_mjr = pytest.time_slice(
        tmpdir.join('a.mjr'),
        fixtures.join(a_mjr), a_pkt_type, time_slice,
    )

    # full
    v_cuts, a_cuts = pytest.time_cut(
        v_mjr, v_pkt_type,
        a_mjr, a_pkt_type, 1024,  # *fixed* @ 1024 for aac
    )
    mkv, v_drop, a_trim, a_range = pytest.mux_time_cuts(
        tmpdir, 'f.mkv',
        v_mjr, v_pkt_type, a_mjr, a_pkt_type,
        zip(v_cuts, a_cuts),
    )[0]
    f_ts_p = tmpdir.join('{0}-p.ts'.format(mkv.purebasename))
    ffmpeg = marm.FFMPEG([
        '-y',
        '-i', mkv.strpath,
        '-c:v', 'h264',
        '-filter:v', 'select=gte(n\,{0})'.format(v_drop),
        '-c:a', 'aac', '-strict', '-2',
        '-b:a', '22k',
        '-r:a', '48k',
        '-filter:a', 'atrim=start_sample={0}'.format(a_trim),
        '-copyts',
        '-mpegts_copyts', '1',
        '-avoid_negative_ts', '0',
        f_ts_p.strpath,
    ])
    ffmpeg()
    f_ts = tmpdir.join('f.ts')
    with f_ts_p.open('rb') as sfo, f_ts.open('wb') as dfo:
        marm.frame.remux(
            dfo, sfo,
            marm.FrameFilter.range(1, *a_range).shift(1),
            options=[
                ('copyts', '1'),
                ('mpegts_copyts', '1'),
                ('avoid_negative_ts', '0'),
            ],
        )

    # calculate mjr "cuts"
    v_cuts, a_cuts = pytest.time_cut(
        v_mjr, v_pkt_type,
        a_mjr, a_pkt_type, 1024,  # *fixed* @ 1024 for aac
        * time_cuts
    )

    # mux each "cut" to mkv
    mkvs = pytest.mux_time_cuts(
        tmpdir, 'c-{i}.mkv',
        v_mjr, v_pkt_type, a_mjr, a_pkt_type,
        zip(v_cuts, a_cuts),
    )

    # xcode "cut" mkv to mpegts
    tss = []
    for mkv, v_drop, a_trim, a_range in mkvs:
        # xcode mkv -> mpegt(v=h264, a=aac)
        ts_p = tmpdir.join('{0}-p.ts'.format(mkv.purebasename))
        ffmpeg = marm.FFMPEG([
            '-y',
            '-i', mkv.strpath,
            '-c:v', 'h264',
            '-filter:v', 'select=gte(n\,{0})'.format(v_drop),
            '-c:a', 'aac', '-strict', '-2',
            '-b:a', '22k',
            '-r:a', '48k',
            '-filter:a', 'atrim=start_sample={0}'.format(a_trim),
            '-copyts',
            '-mpegts_copyts', '1',
            '-avoid_negative_ts', '0',
            ts_p.strpath,
        ])
        ffmpeg()

        # remux mpegts to:
        # - force mpegts continuity counts across "cuts" and
        # - drop aac initial padding (aka audio codec priming samples)
        ts = tmpdir.join('{0}.ts'.format(mkv.purebasename))
        with ts_p.open('rb') as sfo, ts.open('wb') as dfo:
            marm.frame.remux(
                dfo, sfo,
                marm.FrameFilter.range(1, *a_range).shift(1),
                options=[
                    ('copyts', '1'),
                    ('mpegts_copyts', '1'),
                    ('avoid_negative_ts', '0'),
                ],
            )

        tss.append(ts)

    # and concat them
    c_ts = tmpdir.join('c.ts')
    with c_ts.open('wb') as dfo:
        for ts in tss:
            with ts.open('rb') as sfo:
                dfo.write(sfo.read())

    # compare timing
    c_pkts = pytest.packets(c_ts, bucket='stream', parse=lambda p: p['pts'])
    f_pkts = pytest.packets(f_ts, bucket='stream', parse=lambda p: p['pts'])
    assert len(c_pkts) == len(f_pkts)
    for c_p, f_p in itertools.izip(c_pkts.itervalues(), f_pkts.itervalues()):
        assert len(c_p) == len(f_p)
        assert min(c_p) == min(f_p)
        assert max(c_p) == max(f_p)
        assert sum(
            c_pts != f_pts
            for c_pts, f_pts in itertools.izip(sorted(c_p), sorted(f_p))
        ) < 0.01 * len(c_p)


@pytest.mark.parametrize(
    'v_mjr,v_pkt_type,a_mjr,a_pkt_type,time_slice,time_cuts', [
        ('sonic-v.mjr', marm.vp8.VP8RTPPacket,
         'sonic-a.mjr', marm.opus.OpusRTPPacket,
         (0, 20),
         [5, 6, 7]),
    ]
)
def test_mpegts_stitch_many(
        fixtures,
        tmpdir,
        v_mjr, v_pkt_type,
        a_mjr, a_pkt_type,
        time_slice,
        time_cuts):
    # slice and split mjr
    v_mjr = pytest.time_slice(
        tmpdir.join('v.mjr'),
        fixtures.join(v_mjr), v_pkt_type, time_slice,
        sort=True,
    )
    a_mjr = pytest.time_slice(
        tmpdir.join('a.mjr'),
        fixtures.join(a_mjr), a_pkt_type, time_slice,
        sort=True,
    )
    v_mjrs, a_mjrs = pytest.time_split(
        tmpdir, v_mjr, v_pkt_type, a_mjr, a_pkt_type, *time_cuts
    )

    # full
    v_cuts, a_cuts = pytest.time_cut(
        v_mjrs, v_pkt_type,
        a_mjrs, a_pkt_type, 1024,  # *fixed* @ 1024 for aac
    )
    mkv, v_drop, a_trim, a_range = pytest.mux_time_cuts(
        tmpdir, 'f.mkv',
        v_mjrs, v_pkt_type, a_mjrs, a_pkt_type,
        zip(v_cuts, a_cuts),
    )[0]
    f_ts_p = tmpdir.join('{0}-p.ts'.format(mkv.purebasename))
    ffmpeg = marm.FFMPEG([
        '-y',
        '-i', mkv.strpath,
        '-c:v', 'h264',
        '-filter:v', 'select=gte(n\,{0})'.format(v_drop),
        '-c:a', 'aac', '-strict', '-2',
        '-b:a', '22k',
        '-r:a', '48k',
        '-filter:a', 'atrim=start_sample={0}'.format(a_trim),
        '-copyts',
        '-mpegts_copyts', '1',
        '-avoid_negative_ts', '0',
        f_ts_p.strpath,
    ])
    ffmpeg()
    f_ts = tmpdir.join('f.ts')
    with f_ts_p.open('rb') as sfo, f_ts.open('wb') as dfo:
        marm.frame.remux(
            dfo, sfo,
            marm.FrameFilter.range(1, a_range[0], a_range[1] + 1),
            options=[
                ('copyts', '1'),
                ('mpegts_copyts', '1'),
                ('avoid_negative_ts', '0'),
            ],
        )

    # calculate cuts
    v_cuts, a_cuts = pytest.time_cut(
        v_mjrs, v_pkt_type,
        a_mjrs, a_pkt_type, 1024,  # *fixed* @ 1024 for aac
        * time_cuts
    )

    # mux each cut to mkv
    mkvs = pytest.mux_time_cuts(
        tmpdir, 'c-{i}.mkv',
        v_mjrs, v_pkt_type,
        a_mjrs, a_pkt_type,
        zip(v_cuts, a_cuts),
    )

    # xcode cut mkv to mpegts
    tss = []
    for i, (mkv, v_drop, a_trim, a_range) in enumerate(mkvs):
        # xcode mkv -> mpegt(v=h264, a=aac)
        ts_p = tmpdir.join('{0}-p.ts'.format(mkv.purebasename))
        ffmpeg = marm.FFMPEG([
            '-y',
            '-i', mkv.strpath,
            '-c:v', 'h264',
            '-filter:v', 'select=gte(n\,{0})'.format(v_drop),
            '-c:a', 'aac', '-strict', '-2',
            '-b:a', '22k',
            '-r:a', '48k',
            '-filter:a', 'atrim=start_sample={0}'.format(a_trim),
            '-copyts',
            '-mpegts_copyts', '1',
            '-avoid_negative_ts', '0',
            ts_p.strpath,
        ])
        ffmpeg()

        # remux mpegts to:
        # - force mpegts continuity counts across "cuts" and
        # - drop aac initial padding (aka audio codec priming samples)
        ts = tmpdir.join('{0}.ts'.format(mkv.purebasename))
        if i == 0:
            a_range = a_range[0], a_range[1] + 1
        else:
            a_range = a_range[0] + 1, a_range[1] + 1
        with ts.open('wb') as dfo, ts_p.open('rb') as sfo:
            marm.frame.remux(
                dfo, sfo,
                marm.FrameFilter.range(1, *a_range),
                options=[
                    ('copyts', '1'),
                    ('mpegts_copyts', '1'),
                    ('avoid_negative_ts', '0'),
                ],
            )

        tss.append(ts)

    # and concat them
    c_ts = tmpdir.join('c.ts')
    with c_ts.open('wb') as dfo:
        for ts in tss:
            with ts.open('rb') as sfo:
                dfo.write(sfo.read())

    # compare counts and timing
    c_pkts = pytest.packets(c_ts, bucket='stream', parse=lambda p: p['pts'])
    f_pkts = pytest.packets(f_ts, bucket='stream', parse=lambda p: p['pts'])
    assert len(c_pkts) == len(f_pkts)
    for c_p, f_p in itertools.izip(c_pkts.itervalues(), f_pkts.itervalues()):
        assert len(c_p) == len(f_p)
        assert min(c_p) == min(f_p)
        assert max(c_p) == max(f_p)
        assert sum(
            c_pts != f_pts
            for c_pts, f_pts in itertools.izip(sorted(c_p), sorted(f_p))
        ) < 0.01 * len(c_p)


@pytest.mark.parametrize(
    'v_mjr,v_pkt_type,a_mjr,a_pkt_type,time_slice,time_cuts,window', [
        ('sonic-v.mjr', marm.vp8.VP8RTPPacket,
         'sonic-a.mjr', marm.opus.OpusRTPPacket,
         (10, 70),
         [5] * 10,
         (4, 1, 0)),
        ('sonic-v.mjr', marm.vp8.VP8RTPPacket,
         'sonic-a.mjr', marm.opus.OpusRTPPacket,
         (10, 70),
         [6.5] * 7,
         (3, 2, 0)),
    ]
)
def test_mpegts_stitch_window(
        tmpdir,
        fixtures,
        v_mjr, v_pkt_type,
        a_mjr, a_pkt_type,
        time_slice,
        time_cuts,
        window):
    a_idx = 1

    # slice mjrs
    v_mjr = pytest.time_slice(
        tmpdir.join('v.mjr'),
        fixtures.join(v_mjr), v_pkt_type, time_slice,
        sort=True,
    )
    a_mjr = pytest.time_slice(
        tmpdir.join('a.mjr'),
        fixtures.join(a_mjr), a_pkt_type, time_slice,
        sort=True,
    )

    # split mjrs
    v_mjrs, a_mjrs = pytest.time_split(
        tmpdir,
        v_mjr, v_pkt_type,
        a_mjr, a_pkt_type,
        *time_cuts
    )

    # full mpegts (we'll compare stitched to this)
    v_cuts, a_cuts = pytest.time_cut(
        v_mjrs, v_pkt_type,
        a_mjrs, a_pkt_type, 1024,  # *fixed* @ 1024 for aac
    )
    mkv, v_drop, a_trim, a_range = pytest.mux_time_cuts(
        tmpdir, 'f.mkv',
        v_mjrs, v_pkt_type, a_mjrs, a_pkt_type,
        zip(v_cuts, a_cuts),
    )[0]
    f_ts_p = tmpdir.join('{0}-p.ts'.format(mkv.purebasename))
    ffmpeg = marm.FFMPEG([
        '-y',
        '-i', mkv.strpath,
        '-c:v', 'h264',
        '-filter:v', 'select=gte(n\,{0})'.format(v_drop),
        '-c:a', 'aac', '-strict', '-2',
        '-b:a', '22k',
        '-r:a', '48k',
        '-filter:a', 'atrim=start_sample={0}'.format(a_trim),
        '-copyts',
        '-mpegts_copyts', '1',
        '-avoid_negative_ts', '0',
        f_ts_p.strpath,
    ])
    ffmpeg()
    f_ts = tmpdir.join('f.ts')
    with f_ts_p.open('rb') as sfo, f_ts.open('wb') as dfo:
        marm.frame.remux(
            dfo, sfo,
            marm.FrameFilter.range(a_idx, a_range[0], a_range[1] + 1),
            options=[
                ('copyts', '1'),
                ('mpegts_copyts', '1'),
                ('avoid_negative_ts', '0'),
            ],
        )

    # probe
    v_prof = pytest.probe(
        marm.rtp.RTPCursor([v_mjrs[0].strpath], packet_type=v_pkt_type)
    )
    a_prof = pytest.probe(
        marm.rtp.RTPCursor([a_mjrs[0].strpath], packet_type=a_pkt_type)
    )

    # xcode windows
    lead, size, lag = window
    total = len(v_mjrs)
    for j, i in enumerate(range(0, total, size)):
        l, u = max(0, i - lead), min(total, i + size - 1 + lag)

        v_wnd = [mjr.strpath for mjr in v_mjrs[l:u + 1]]
        a_wnd = [mjr.strpath for mjr in a_mjrs[l:u + 1]]
        b = i - l
        e = min(b + size, len(v_wnd))

        # v window
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

        # a window
        a_cur = marm.rtp.RTPCursor(a_wnd, packet_type=a_pkt_type)
        a_cur.seek((b, 0))
        with a_cur.restoring():
            a_delta = a_cur.interval((e, 0)) if e != len(a_wnd) else None
        a_start, _, a_stop, _ = a_cur.time_cut(0, a_delta, align='prev')
        a_cur.seek(a_start)
        a_start, a_stop, a_trim, a_range = a_cur.trim_frames(
            a_stop, 1024, zero=marm.rtp.RTPCursor(
                [mjr.strpath for mjr in a_mjrs[:l]],
                packet_type=marm.opus.OpusRTPPacket,
            ).compute(
                lambda pkt: pkt.data.nb_samples * pkt.data.nb_channels,
                lambda x, y: x + y,
            )
        )

        # frames
        v_cur.seek(v_key)
        assert v_cur.tell() == v_key
        assert v_cur.current().data.is_key_frame
        v_frames = marm.VideoFrames(v_cur.slice(v_stop), -v_prof['msec_org'])
        a_cur.seek(a_start)
        assert a_cur.tell() == a_start
        a_frames = marm.Frames(a_cur.slice(a_stop), -a_prof['msec_org'])

        # mux window
        mkv = tmpdir.join('c-{0:03}.mkv'.format(j))
        with mkv.open('wb') as fo:
            marm.frame.mux(
                fo,
                video_profile={
                    'encoder_name': 'libvpx',
                    'pix_fmt': marm.VideoFrame.PIX_FMT_YUV420P,
                    'width': v_prof['width'],
                    'height': v_prof['height'],
                    'frame_rate': v_prof['frame_rate'],
                    'bit_rate': v_prof['bit_rate'],
                    'time_base': (1, 1000),
                },
                video_packets=v_frames,
                audio_profile={
                    'encoder_name': 'libopus',
                    'bit_rate': a_prof['bit_rate'],
                    'sample_rate': a_prof['sample_rate'],
                    'channel_layout': a_prof['channel_layout'],
                    'time_base': (1, 1000),
                    'initial_padding': 0,
                },
                audio_packets=a_frames,
            )
        assert v_cur.tell() == v_stop
        assert v_cur.current().data.is_start_of_frame
        assert a_cur.tell() == a_stop

        # xcode window
        p_ts = tmpdir.join('p-{0:03}.ts'.format(j))
        ffmpeg = marm.FFMPEG([
            '-y',
            '-i', mkv.strpath,
            '-c:v', 'h264',
            '-filter:v', 'select=gte(n\,{0})'.format(v_drop),
            '-c:a', 'aac', '-strict', '-2',
            '-b:a', '22k',
            '-r:a', '48k',
            '-filter:a', 'atrim=start_sample={0}'.format(a_trim),
            '-copyts',
            '-mpegts_copyts', '1',
            '-avoid_negative_ts', '0',
            p_ts.strpath,
        ])
        ffmpeg()
        ts = tmpdir.join('c-{0:03}.ts'.format(j))
        with ts.open('wb') as dfo, p_ts.open('rb') as sfo:
            if b == 0:
                # keep codec priming packet
                a_range = (a_range[0], a_range[1] + 1)
            else:
                # drop codec priming packet
                a_range = (a_range[0] + 1, a_range[1] + 1)
            marm.frame.remux(
                dfo, sfo,
                marm.FrameFilter.range(a_idx, *a_range),
                options=[
                    ('copyts', '1'),
                    ('mpegts_copyts', '1'),
                    ('avoid_negative_ts', '0'),
                ],
            )

    # concat widows
    c_ts = tmpdir.join('c.ts')
    with c_ts.open('wb') as dfo:
        for ts in sorted(tmpdir.listdir('c-*.ts')):
            with ts.open('rb') as sfo:
                dfo.write(sfo.read())

    # compare to full
    c_pkts = pytest.packets(c_ts, bucket='stream', parse=lambda p: p['pts'])
    f_pkts = pytest.packets(f_ts, bucket='stream', parse=lambda p: p['pts'])
    assert len(c_pkts) == len(f_pkts)
    for c_p, f_p in itertools.izip(c_pkts.itervalues(), f_pkts.itervalues()):
        assert len(c_p) == len(f_p)
        assert min(c_p) == min(f_p)
        assert max(c_p) == max(f_p)


@pytest.mark.parametrize(
    'v_store,v_pkt,v_enc,a_store,a_pkt,a_enc,time_slice,interval,delta', [
        ('sonic-v.mjr', marm.vp8.VP8RTPPacket, 'libvpx',
         'sonic-a.mjr', marm.opus.OpusRTPPacket, 'libopus',
         (0, 30),
         5,
         1.0),
    ]
)
def test_mpegts_segment(
        fixtures,
        tmpdir,
        v_store, v_pkt, v_enc,
        a_store, a_pkt, a_enc,
        time_slice,
        interval,
        delta):
    # time slice src
    v_src = pytest.time_slice(
        tmpdir.join('v.mjr'),
        fixtures.join(v_store), v_pkt, time_slice,
    )
    a_src = pytest.time_slice(
        tmpdir.join('a.mjr'),
        fixtures.join(a_store), a_pkt, time_slice,
    )

    # mux src
    src = tmpdir.join('c.mkv')
    pytest.mux(
        src,
        v_src, v_pkt, v_enc,
        a_src, a_pkt, a_enc,
    )

    # xcode src -> full
    full = tmpdir.join('f.ts')
    ffmpeg = marm.FFMPEG([
        '-y',
        '-i', src.strpath,
        '-c:v', 'h264',
        '-r', '25',
        '-force_key_frames', 'expr:gte(t,n_forced*{0})'.format(5),
        '-c:a', 'aac', '-strict', '-2',
        '-b:a', '22k',
        '-r:a', '48k',
        '-copyts',
        '-mpegts_copyts', '1',
        '-avoid_negative_ts', '0',
        full.strpath,
    ])
    ffmpeg()

    # split full -> segments
    seg_fmt = tmpdir.join('s-%03d.ts')
    ccs = {}
    with full.open('rb') as sfo:
        marm.frame.segment(
            seg_fmt.strpath,
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
        s_pkts = pytest.packets(s, bucket='stream')

        # videos start w/ keyframe
        assert all(
            s_pkts[idx][0]['flags'] == 'K'
            for idx in s_pkts.keys() if s_pkts[idx][0]['codec_type'] == 'video'
        )

        # durations are close to interval
        assert all(
            abs(interval - (
                float(pkts[-1]['pts_time']) - float(pkts[0]['pts_time'])
            )) < delta
            for pkts in s_pkts.values()[:-1]
        )

    # concat segments
    concat = tmpdir.join('c.ts')
    with concat.open('wb') as dfo:
        for rseg in sorted(tmpdir.listdir('s-*.ts')):
            with rseg.open('rb') as sfo:
                dfo.write(sfo.read())

    # and compare to full
    full_pkts = pytest.packets(
        full, bucket='stream', parse=lambda p: p['pts']
    )
    concat_pkts = pytest.packets(
        concat, bucket='stream', parse=lambda p: p['pts']
    )
    assert full_pkts == concat_pkts
