import itertools

import pytest

import marm


@pytest.mark.parametrize(
    'mpegts,ccs', [
        ('sonic.ts', {0: 4, 17: 9, 4096: 4, 256: 2, 257: 8})
    ]
)
def test_mpegts_last_ccs(fixtures, mpegts, ccs):
    mpegts = fixtures.join(mpegts)
    with mpegts.open('rb') as fo:
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
    v_src_mjr = fixtures.join(v_mjr)
    a_src_mjr = fixtures.join(a_mjr)
    v_dst_mjr = tmpdir.join(v_src_mjr.basename)
    a_dst_mjr = tmpdir.join(a_src_mjr.basename)
    pytest.time_slice(v_dst_mjr, v_src_mjr, v_pkt_type, time_slice,)
    pytest.time_slice(a_dst_mjr, a_src_mjr, a_pkt_type, time_slice)
    v_mjr = v_dst_mjr
    a_mjr = a_dst_mjr

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
    # slice mjr
    v_mjrs = []
    a_mjrs = []
    v_src_mjr = fixtures.join(v_mjr)
    a_src_mjr = fixtures.join(a_mjr)
    o, e = time_slice
    for i, d in enumerate(list(time_cuts) + [e - sum(time_cuts)]):
        v_dst_mjr = tmpdir.join('c-{0}-v.mjr'.format(i))
        pytest.time_slice(
            v_dst_mjr, v_src_mjr, v_pkt_type,
            (o, o + d),
            align=False,
        )
        v_mjrs.append(v_dst_mjr)
        a_dst_mjr = tmpdir.join('c-{0}-a.mjr'.format(i))
        pytest.time_slice(
            a_dst_mjr, a_src_mjr, a_pkt_type,
            (o, o + d),
            align=False,
        )
        a_mjrs.append(a_dst_mjr)
        o += d

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
