import collections
import logging
import multiprocessing.dummy
import os
import pprint
import sys

import py
import pytest

import marm


def pytest_namespace():
    return {
        'pprint': pprint.pprint,
        'probe_video': probe_video,
        'probe_audio': probe_audio,
        'mux': mux,
        'time_slice': time_slice,
        'time_cut': time_cut,
        'mux_time_cuts': mux_time_cuts,
        'packets': packets,
    }


def pytest_addoption(parser):
    parser.addoption('--log-level', choices=['d', 'i', 'w', 'e'], default='w')
    parser.addoption('--log-file')


@pytest.fixture(scope='session')
def log_level(pytestconfig):
    return {
        'd': logging.DEBUG,
        'i': logging.INFO,
        'w': logging.WARN,
        'e': logging.ERROR,
    }[pytestconfig.getoption('log_level')]


@pytest.fixture(scope='session')
def log_file(pytestconfig):
    return pytestconfig.getoption('log_file')


@pytest.fixture(scope='session', autouse=True)
def config_logging(pytestconfig, log_level, log_file):
    logging.basicConfig(
        format='%(levelname)s : %(name)s : %(message)s',
        level=log_level,
        filename=log_file,  # trumps stream=
        stream=sys.stderr,
    )


@pytest.fixture(scope='session')
def fixtures():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures')
    return py.path.local(path)


@pytest.fixture(scope='session')
def ffmpeg():
    return 'ffmpeg'


@pytest.fixture()
def pool():
    return multiprocessing.dummy.Pool(multiprocessing.cpu_count())


def probe_video(cur):
    with cur.restoring():
        frame_rate = marm.rtp.estimate_video_frame_rate(cur, window=300)
    with cur.restoring():
        (width, height) = marm.rtp.probe_video_dimensions(cur)
    with cur.restoring():
        msec_org = min(
            pkt.msecs for pkt in marm.rtp.head_packets(cur, count=100)
        )
    bit_rate = 4000000
    return {
        'frame_rate': frame_rate,
        'bit_rate': bit_rate,
        'width': width,
        'height': height,
        'msec_org': msec_org,
    }


def probe_audio(cur):
    with cur.restoring():
        msec_org = min(
            pkt.msecs for pkt in marm.rtp.head_packets(cur, count=100)
        )
    bit_rate = 96000
    sample_rate = 48000
    with cur.restoring():
        channel_layout = marm.rtp.probe_audio_channel_layout(cur)
    return {
        'sample_rate': sample_rate,
        'bit_rate': bit_rate,
        'msec_org': msec_org,
        'channel_layout': channel_layout,
    }


def mux(out_path, v_path, v_pkt, v_enc, a_path, a_pkt, a_enc):
    v_cur = marm.rtp.RTPCursor(
        [v_path.strpath],
        marm.rtp.RTPPacketReader.open,
        packet_type=v_pkt,
    )
    v_prof = probe_video(v_cur)

    a_cur = marm.rtp.RTPCursor(
        [a_path.strpath],
        marm.rtp.RTPPacketReader.open,
        packet_type=a_pkt,
    )
    a_prof = probe_audio(a_cur)

    with out_path.open('wb') as fo:
        marm.frame.mux(
            fo,
            video_profile={
                'encoder_name': v_enc,
                'pix_fmt': marm.VideoFrame.PIX_FMT_YUV420P,
                'width': v_prof['width'],
                'height': v_prof['height'],
                'frame_rate': v_prof['frame_rate'],
                'bit_rate': 4000000,
                'time_base': (1, 1000),
            },
            video_packets=marm.VideoFrames(v_cur, -v_prof['msec_org']),
            audio_profile={
                'encoder_name': a_enc,
                'bit_rate': a_prof['bit_rate'],
                'sample_rate': a_prof['sample_rate'],
                'channel_layout': a_prof['channel_layout'],
                'time_base': (1, 1000),
                'initial_padding': 0,
            },
            audio_packets=marm.Frames(a_cur, -a_prof['msec_org']),
        )


def time_slice(dst_path, src_path, pkt_type, (b_secs, e_secs), align=True):
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
        for pkt in pkts:
            marm.mjr.write_packet(fo, pkt)
    return dst_path


def time_cut(v_mjr, v_pkt_type, a_mjr, a_pkt_type, a_size, *deltas):
    v_cur = marm.rtp.RTPCursor(
        map(lambda x: x.strpath, (
            [v_mjr]
            if not isinstance(v_mjr, collections.Sequence)
            else v_mjr
        )),
        marm.mjr.MJRRTPPacketReader,
        packet_type=v_pkt_type,
    )
    a_cur = marm.rtp.RTPCursor(
        map(lambda x: x.strpath, (
            [a_mjr]
            if not isinstance(a_mjr, collections.Sequence)
            else a_mjr
        )),
        marm.mjr.MJRRTPPacketReader,
        packet_type=a_pkt_type,
    )
    interval = max(v_cur.interval(), a_cur.interval())
    deltas = list(deltas) + [interval - sum(deltas)]

    v_cuts, a_cuts, off = [], [], 0
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
        a_cur.seek(a_start)
        a_start, a_stop, a_trim, a_range = a_cur.trim_frames(a_stop, a_size)
        a_cuts.append((a_start, a_stop, a_trim, a_range))

        off += delta

    return v_cuts, a_cuts


def mux_time_cuts(dir, format, v_mjr, v_pkt_type, a_mjr, a_pkt_type, cuts):
    v_cur = marm.rtp.RTPCursor(
        map(lambda x: x.strpath, (
            [v_mjr]
            if not isinstance(v_mjr, collections.Sequence)
            else v_mjr
        )),
        marm.mjr.MJRRTPPacketReader,
        packet_type=v_pkt_type,
    )
    v_prof = probe_video(v_cur)

    a_cur = marm.rtp.RTPCursor(
        map(lambda x: x.strpath, (
            [a_mjr]
            if not isinstance(a_mjr, collections.Sequence)
            else a_mjr
        )),
        marm.mjr.MJRRTPPacketReader,
        packet_type=a_pkt_type,
    )
    a_prof = probe_audio(a_cur)

    muxed = []

    for i, (v_cut, a_cut) in enumerate(cuts):
        mkv = dir.join(format.format(i=i))

        v_key, v_start, v_stop, v_drop = v_cut
        v_cur.seek(v_start)
        assert v_cur.tell() == v_start
        assert v_cur.current().data.is_start_of_frame
        v_cur.seek(v_key)
        assert v_cur.tell() == v_key
        assert v_cur.current().data.is_key_frame
        v_frames = marm.VideoFrames(v_cur.slice(v_stop), -v_prof['msec_org'])

        a_start, a_stop, a_trim, a_range = a_cut
        a_cur.seek(a_start)
        assert a_cur.tell() == a_start
        a_frames = marm.Frames(a_cur.slice(a_stop), -a_prof['msec_org'])

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

        muxed.append((mkv, v_drop, a_trim, a_range))

    return muxed


def packets(path, bucket=None, parse=lambda pkt: pkt):
    probe = marm.FFProbe([
        '-show_packets',
        path
    ])
    probe()
    pkts = [(p, parse(p)) for p in probe.result['packets']]
    if bucket == 'stream':
        t = collections.defaultdict(list)
        for pkt, parsed in pkts:
            t[pkt['stream_index']].append(parsed)
        pkts = t
    else:
        pkts = zip(*pkts)[0]
    return pkts
