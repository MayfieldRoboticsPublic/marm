import subprocess

import pytest

import marm


@pytest.mark.parametrize(
    ('duration,'
     'v_encoder,v_width,v_height,v_frame_rate,'
     'a_encoder,a_bit_rate,a_sample_rate,a_channel_layout,'
     'fmt,fmt_name'), [
        (5,
         'mpeg4', 320, 240, 25,
         'flac', 96000, 48000, marm.frame.AudioFrame.CHANNEL_LAYOUT_STEREO,
         'mkv', 'matroska'),
    ]
)
def test_mux_gen(
        tmpdir,
        duration,
        v_encoder, v_width, v_height, v_frame_rate,
        a_encoder, a_bit_rate, a_sample_rate, a_channel_layout,
        fmt, fmt_name):
    v_path = tmpdir.join('v.{0}'.format(v_encoder))
    a_path = tmpdir.join('a.{0}'.format(a_encoder))
    m_path = tmpdir.join('m.{0}'.format(fmt))

    with v_path.open('wb') as fo:
        marm.frame.gen_video(
            fo,
            duration=duration,
            width=v_width,
            height=v_height,
            frame_rate=v_frame_rate
        )

    with a_path.open('wb') as fo:
        marm.frame.gen_audio(
            fo,
            duration=duration,
            bit_rate=a_bit_rate,
            sample_rate=a_sample_rate,
            channel_layout=a_channel_layout,
        )

    with m_path.open('wb') as fo, \
            v_path.open('rb') as v_fo, \
            a_path.open('rb') as a_fo:
        # a
        a_hdr = marm.frame.read_header(a_fo)
        a_frames = marm.frame.read_frames(a_fo)

        # v
        v_hdr = marm.frame.read_header(v_fo)
        v_frames = marm.frame.read_frames(v_fo)

        # mux them
        marm.frame.mux(
            fo,
            audio_profile={
                'encoder_name': a_hdr.encoder_name,
                'bit_rate': a_hdr.bit_rate,
                'sample_rate': a_hdr.sample_rate,
                'channel_layout': a_hdr.channel_layout,
            },
            audio_packets=a_frames,
            video_profile={
                'encoder_name': v_hdr.encoder_name,
                'pix_fmt': v_hdr.pix_fmt,
                'width': v_hdr.width,
                'height': v_hdr.height,
                'frame_rate': v_hdr.frame_rate,
                'bit_rate': v_hdr.bit_rate,
            },
            video_packets=v_frames,
        )

    probe = marm.FFProbe([
        '-show_format',
        '-show_streams',
        m_path.strpath,
    ])
    probe()
    assert len(probe.result['streams']) == 2
    assert fmt_name in probe.result['format']['format_name'].split(',')


def check_output(cmd):
    try:
        return subprocess.check_output(cmd, shell=True), None
    except Exception, ex:
        return None, ex


@pytest.mark.parametrize(
    ('v_store,v_enc,a_store,a_enc,dur,fmt'), [
        ('sonic-v.mjr', 'libvpx', 'sonic-a.mjr', 'libopus', 10.0, 'mkv'),
    ]
)
def test_concat_muxed(
        tmpdir,
        fixtures,
        pool,
        ffmpeg,
        v_store, v_enc,
        a_store, a_enc,
        dur,
        fmt):
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

    # cursor for split parts
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

    # probe
    v_prof = pytest.probe(v_cur)
    a_prof = pytest.probe(a_cur)

    # calculate mux points
    mux_points = []
    assert v_parts == a_parts
    for i in range(v_parts):
        # begin
        v_cur.seek((i, 0))
        v_b_drop = 0
        a_cur.seek((i, 0))
        a_b_drop = 0
        a_b_delay = 0
        a_b = a_cur.tell()
        v_pkt = v_cur.current()
        if v_cur.prev_key_frame():
            v_cur.prev()
            v_b = v_cur.tell()
            a_b_delay = int((v_pkt.msecs - v_cur.current().msecs))
            v_b_drop = (
                v_cur.count((i, 0), lambda pkt: pkt.data.is_start_of_frame) - 1
            )
        elif v_pkt.data.is_key_frame:
            v_b = v_cur.tell()
        elif v_cur.next_key_frame():
            v_cur.prev()
            v_b = v_cur.tell()
            a_cur.fastforward(v_pkt.msecs - v_cur.current().msecs)
            a_b = a_cur.tell()
        else:
            assert not (
                'Could not find key-frame in "{0}" part "{1}"'
                .format(v_path, i + 1)
            )

        # end
        v_cur.seek((i, -1))
        v_pkt = v_cur.current()
        if not v_pkt.data.is_start_of_frame:
            if v_cur.prev_start_of_frame() is None:
                assert not (
                    'Could not find prev start-of-frame in "{0}" part "{1}"'
                    .format(v_path, i + 1)
                )
            v_cur.prev()
        v_e = v_cur.tell()
        a_e = (i + 1, 0)

        mux_points.append((v_b, v_b_drop, v_e, a_b, a_b_drop, a_b_delay, a_e))

    # mux parts
    for i, (v_b, _, v_e, a_b, _, a_b_delay, a_e) in enumerate(mux_points):
        # packets
        v_cur.seek(v_b)
        v_pkts = v_cur.slice(v_e)
        a_cur.seek(a_b)
        a_pkts = a_cur.slice(a_e)

        # mux
        p_path = tmpdir.join('mux-{0}.{1}'.format(i + 1, fmt))
        with p_path.open('wb') as fo:
            marm.frame.mux(
                fo,
                video_profile={
                    'encoder_name': v_enc,
                    'pix_fmt': marm.VideoFrame.PIX_FMT_YUV420P,
                    'width': v_prof['width'],
                    'height': v_prof['height'],
                    'frame_rate': v_prof['frame_rate'],
                    'bit_rate': v_prof['bit_rate'],
                    'time_base': (1, 1000),
                },
                video_packets=marm.VideoFrames(v_pkts),
                audio_profile={
                    'encoder_name': a_enc,
                    'bit_rate': a_prof['bit_rate'],
                    'sample_rate': a_prof['sample_rate'],
                    'channel_layout': a_prof['channel_layout'],
                    'time_base': (1, 1000),
                },
                audio_packets=marm.Frames(a_pkts, a_b_delay),
            )

    # xcode parts
    xcodes = []
    for i, point in enumerate(mux_points):
        v_b, v_b_drop, v_e, a_b, a_b_drop, _, a_e = point
        p_path = tmpdir.join('mux-{0}.{1}'.format(i + 1, fmt))
        x_path = tmpdir.join('xcode-{0}.{1}'.format(i + 1, fmt))
        cmd = [
            ffmpeg,
            '-i', p_path,
            '-codec:v', v_enc,
            '-filter:v',
            '"select=gte(n\\, {0}), setpts=PTS-STARTPTS"'.format(v_b_drop),
            '-codec:a', a_enc,
            '-filter:a',
            '"aselect=gte(n\\, {0}), asetpts=PTS-STARTPTS"'.format(a_b_drop),
            x_path,
        ]
        xcodes.append(' '.join(map(str, cmd)))
    for _, ex in pool.imap(check_output, xcodes):
        assert ex is None

    # concat xcoded parts
    c_txt_path = tmpdir.join('concat.txt')
    c_txt_path.write('\n'.join([
        'file {0}'.format(tmpdir.join('xcode-{0}.{1}'.format(i + 1, fmt)))
        for i in range(len(mux_points))
    ]))
    c_path = tmpdir.join('concat.{0}'.format(fmt))
    cmd = [
        ffmpeg,
        '-f', 'concat',
        '-safe', '0',
        '-i', str(c_txt_path),
        '-c', 'copy',
        str(c_path),
    ]
    subprocess.check_call(args=' '.join(cmd), shell=True)


@pytest.mark.parametrize(
    ('v_store,v_pt,v_enc,a_store,a_pt,a_enc,fmt,count'), [
        ('sonic-v.mjr', marm.vp8.VP8RTPPacket, 'libvpx',
         'sonic-a.mjr', marm.opus.OpusRTPPacket, 'libopus',
         'mkv',
         100),
    ]
)
def test_mux_next_packet_error(
        tmpdir,
        fixtures,
        v_store, v_pt, v_enc,
        a_store, a_pt, a_enc,
        fmt,
        count):
    # v
    v_src = fixtures.join(v_store)
    v_pkts = marm.rtp.RTPCursor([v_src.strpath], packet_type=v_pt)
    v_prof = pytest.probe(v_pkts)

    # a
    a_src = fixtures.join(a_store)
    a_pkts = marm.rtp.RTPCursor([a_src.strpath], packet_type=a_pt)
    a_prof = pytest.probe(a_pkts)

    # mux

    class MyException(Exception):

        pass

    local = {'call_count': 0}

    def v_pkts_wrapper():
        for i, v_pkt in enumerate(v_pkts):
            local['call_count'] += 1
            if i > count:
                raise MyException('poop')
            yield v_pkt

    m_path = tmpdir.join('mux.{0}'.format(fmt))
    with pytest.raises(MyException) as ei:
        with m_path.open('wb') as fo:
            marm.frame.mux(
                fo,
                video_profile={
                    'encoder_name': v_enc,
                    'pix_fmt': marm.VideoFrame.PIX_FMT_YUV420P,
                    'width': v_prof['width'],
                    'height': v_prof['height'],
                    'frame_rate': v_prof['frame_rate'],
                    'bit_rate': v_prof['bit_rate'],
                    'time_base': (1, 1000),
                },
                video_packets=marm.VideoFrames(v_pkts_wrapper()),
                audio_profile={
                    'encoder_name': a_enc,
                    'bit_rate': a_prof['bit_rate'],
                    'sample_rate': a_prof['sample_rate'],
                    'channel_layout': a_prof['channel_layout'],
                    'time_base': (1, 1000),
                },
                audio_packets=marm.Frames(a_pkts)
            )
    assert 'poop' in ei.value
    assert local == {'call_count': count + 2}
