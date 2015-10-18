import collections
import re

import pytest

import marm


def cut(tmpdir,
        v_mjr, v_packet_type,
        a_mjr, a_packet_type,
        b_secs, e_secs,
        cuts):
        # slice v
    cur = marm.rtp.RTPCursor(
        [v_mjr.strpath],
        marm.mjr.MJRRTPPacketReader,
        packet_type=v_packet_type,
    )
    b_secs, e_secs, pkts = cur.time_slice(b_secs, e_secs)
    v_mjr = tmpdir.join(v_mjr.basename)
    with v_mjr.open('wb') as fo:
        marm.mjr.write_header(fo, marm.mjr.VIDEO_TYPE)
        for pkt in pkts:
            marm.mjr.write_packet(fo, pkt)

    # slice a to sync w/ v
    cur = marm.rtp.RTPCursor(
        [a_mjr.strpath],
        marm.mjr.MJRRTPPacketReader,
        packet_type=a_packet_type,
    )
    _, _, pkts = cur.time_slice(b_secs, e_secs)
    a_mjr = tmpdir.join(a_mjr.basename)
    with a_mjr.open('wb') as fo:
        marm.mjr.write_header(fo, marm.mjr.AUDIO_TYPE)
        for pkt in pkts:
            marm.mjr.write_packet(fo, pkt)

    # probe v
    v_cur = marm.rtp.RTPCursor(
        [v_mjr.strpath],
        marm.mjr.MJRRTPPacketReader,
        packet_type=v_packet_type,
    )
    v_frame_rate = marm.rtp.estimate_video_frame_rate(v_cur, window=300)
    v_cur.seek((0, 0))
    (v_width, v_height) = marm.rtp.probe_video_dimensions(v_cur)
    v_cur.seek((0, 0))
    v_msec_org = min(
        pkt.msecs for pkt in marm.rtp.head_packets(v_cur, count=100)
    )
    v_cur.seek((0, 0))
    v_bit_rate = 4000000

    # probe a
    a_cur = marm.rtp.RTPCursor(
        [a_mjr.strpath],
        marm.mjr.MJRRTPPacketReader,
        packet_type=a_packet_type,
    )
    a_msec_org = min(
        pkt.msecs for pkt in marm.rtp.head_packets(a_cur, count=100)
    )
    a_cur.seek((0, 0))
    a_bit_rate = 96000
    a_sample_rate = 48000

    # cuts
    v_cuts, a_cuts, off = [], [], 0
    for cut in cuts:
        v_cur.seek((0, 0))
        r = v_cur.time_cut(off, off + cut)
        (v_key, v_start, v_stop), (key_off, start_off, stop_off) = r

        a_cur.seek((0, 0))
        r = a_cur.time_positions(key_off, start_off, stop_off)
        (a_key, a_start, a_stop) = r

        off += cut
        v_cuts.append((v_key, v_start, v_stop))
        a_cuts.append((a_key, a_start, a_stop))

    # mux cuts to mkvs
    mkvs = []
    for i, (v_cut, a_cut) in enumerate(zip(v_cuts, a_cuts)):
        mkv = tmpdir.join('{0}-{1}.mkv'.format('cut', i))
        v_key, v_start, v_stop = v_cut
        a_key, a_start, a_stop = a_cut

        v_cur.seek(v_key)
        v_drop = v_cur.count(v_start, lambda pkt: pkt.data.is_start_of_frame)
        assert v_cur.tell() == v_start
        assert v_cur.current().data.is_start_of_frame
        v_cur.seek(v_key)
        assert v_cur.tell() == v_key
        assert v_cur.current().data.is_key_frame
        v_frames = marm.VideoFrames(v_cur.slice(v_stop), -v_msec_org)

        a_cur.seek(a_key)
        a_drop = a_cur.count(a_start)
        assert a_cur.tell() == a_start
        a_cur.seek(a_key)
        assert a_cur.tell() == a_key
        a_frames = marm.Frames(a_cur.slice(a_stop), -a_msec_org)

        with mkv.open('wb') as fo:
            marm.mux_frames(
                fo,
                video_profile={
                    'encoder_name': 'libvpx',
                    'pix_fmt': marm.VideoFrame.PIX_FMT_YUV420P,
                    'width': v_width,
                    'height': v_height,
                    'frame_rate': v_frame_rate,
                    'bit_rate': v_bit_rate,
                    'time_base': (1, 1000),
                },
                video_packets=v_frames,
                audio_profile={
                    'encoder_name': 'libopus',
                    'bit_rate': a_bit_rate,
                    'sample_rate': a_sample_rate,
                    'time_base': (1, 1000),
                },
                audio_packets=a_frames,
            )
        assert v_cur.tell() == v_stop
        assert v_cur.current().data.is_start_of_frame
        assert a_cur.tell() == a_stop
        mkvs.append((mkv, v_drop, a_drop))

    return mkvs


@pytest.mark.parametrize(
    'v_mjr,v_packet_type,a_mjr,a_packet_type,b_secs,e_secs,cuts,tally', [
        ('sonic-v.mjr', marm.vp8.VP8RTPPacket,
         'sonic-a.mjr', marm.opus.OpusRTPPacket,
         10, 60,
         [11, 12, 12, 13, 14, 15],
         [{'nb_read_frames': 1222, 'nb_read_packets': 1222},
          {'nb_read_frames': 1913, 'nb_read_packets': 1917}]),
    ]
)
def test_stitch_mjrs_2_mp4(
        fixtures,
        tmpdir,
        v_mjr, v_packet_type,
        a_mjr, a_packet_type,
        b_secs, e_secs,
        cuts,
        tally):
    # split mjrs into mkvs @ cuts
    mkvs = cut(
        tmpdir,
        fixtures.join(v_mjr), v_packet_type,
        fixtures.join(a_mjr), a_packet_type,
        b_secs, e_secs,
        cuts)

    # xcode mkvs to mp4s
    mp4s = []
    for mkv, v_drop, a_drop in mkvs:
        mp4 = tmpdir.join('{0}.mp4'.format(mkv.purebasename))
        ffmpeg = marm.FFMPEG([
            '-y',
            '-i', mkv.basename,
            '-codec:v', 'h264',
            '-filter:v',
            'select=gte(n\,{0}), setpts=PTS-STARTPTS'.format(v_drop),
            '-codec:a', 'libfaac',
            '-filter:a',
            'aselect=gte(n\,{0}), asetpts=PTS-STARTPTS'.format(a_drop),
            mp4.basename
        ], cwd=tmpdir.strpath)
        ffmpeg()
        mp4s.append(mp4)

    # concat mp4s
    tmpdir.join('concat.txt').write_text(u'\n'.join(
            u"file '{0}'".format(path.basename)
            for path in mp4s
        ), 'utf-8')
    ffmpeg = marm.FFMPEG([
        '-y',
        '-f', 'concat',
        '-i', 'concat.txt',
        '-c', 'copy',
        'stitched.mp4',
    ], cwd=tmpdir.strpath)
    ffmpeg()

    # verify
    ffprobe = marm.FFProbe([
        '-show_streams',
        '-show_format',
        '-count_frames',
        '-count_packets',
        'stitched.mp4',
    ], cwd=tmpdir.strpath)
    ffprobe()
    r = ffprobe.result
    assert r['format']['format_name'] == 'mov,mp4,m4a,3gp,3g2,mj2'
    assert r['format']['nb_streams'] == 2
    stitched_tally = [
        {
         'nb_read_frames': stream['nb_read_frames'],
         'nb_read_packets': stream['nb_read_packets'],
        }
        for stream in r['streams']
    ]
    assert stitched_tally == tally


@pytest.mark.parametrize(
    'v_mjr,v_packet_type,a_mjr,a_packet_type,b_secs,e_secs,cuts,dt,tally', [
        ('sonic-v.mjr', marm.vp8.VP8RTPPacket,
         'sonic-a.mjr', marm.opus.OpusRTPPacket,
         10, 110,
         [11, 12, 12, 13, 14, 15],
         5,
         [{'nb_read_frames': 2308, 'nb_read_packets': 2308},
          {'nb_read_frames': 3609, 'nb_read_packets': 3615}]),
    ]
)
def test_stitch_mjrs_2_mpegts(
        fixtures,
        tmpdir,
        v_mjr, v_packet_type,
        a_mjr, a_packet_type,
        b_secs, e_secs,
        cuts,
        dt,
        tally):
    # split mjrs into mkvs @ cuts
    mkvs = cut(
        tmpdir,
        fixtures.join(v_mjr), v_packet_type,
        fixtures.join(a_mjr), a_packet_type,
        b_secs, e_secs,
        cuts)

    # xcode mkvs to mpegts
    mpegtss = []
    for mkv, v_drop, a_drop in mkvs:
        name = mkv.purebasename
        m3u8 = '{0}.m3u8'.format(name)
        ffmpeg = marm.FFMPEG([
            '-y',
            '-i', mkv.basename,
            '-codec:v', 'h264',
            '-filter:v',
            'select=gte(n\,{0}), setpts=PTS-STARTPTS'.format(v_drop),
            '-codec:a', 'libfaac',
            '-filter:a',
            'aselect=gte(n\,{0}), asetpts=PTS-STARTPTS'.format(a_drop),
            '-f', 'stream_segment',
            '-segment_list', m3u8,
            '-segment_format', 'mpegts',
            '-segment_time', str(dt),
            '{0}-%02d.ts'.format(name)
        ], cwd=tmpdir.strpath)
        ffmpeg()
        mpegtss.append(tmpdir.join(m3u8))

    # concat m3u8
    stitched = tmpdir.join('stitched.m3u8')
    with stitched.open('w') as fo:
        ps = [p.readlines() for p in mpegtss]
        for l in ps[0][:4]:
            fo.write(l)
        fo.write('#EXT-X-TARGETDURATION:{0}\n'.format(sum(
            int(re.match(r'\#EXT\-X\-TARGETDURATION\:(\d+)', p[4]).group(1))
            for p in ps
        )))
        for p in ps:
            fo.write('#EXT-X-DISCONTINUITY\n')
            for l in p[5:-1]:
                fo.write(l)
        fo.write('#EXT-X-ENDLIST\n')

    # verify
    stitched_tally = [collections.Counter(), collections.Counter()]
    for ts in tmpdir.visit('*.ts'):
        ffprobe = marm.FFProbe([
            '-show_streams',
            '-show_format',
            '-count_frames',
            '-count_packets',
            ts.strpath,
        ])
        ffprobe()
        r = ffprobe.result
        assert r['format']['format_name'] == 'mpegts'
        assert r['format']['nb_streams'] == 2
        for stream in r['streams']:
            stitched_tally[stream['index']].update({
             'nb_read_frames': stream['nb_read_frames'],
             'nb_read_packets': stream['nb_read_packets'],
            })
    assert map(dict, stitched_tally) == tally
    print tmpdir
