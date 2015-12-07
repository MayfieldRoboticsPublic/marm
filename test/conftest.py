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
        'probe': probe,
        'mux': mux,
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


def probe(cur):
    if isinstance(cur, marm.rtp.RTPPacketReader):
        with cur.restoring():
            return probe(
                marm.rtp.RTPCursor([cur], packet_type=cur.packet_type)
            )
    with cur.restoring():
        prof = cur.probe()
    with cur.restoring():
        prof['msec_org'] = min(
            pkt.msecs for pkt in marm.rtp.head_packets(cur, count=100)
        )
    return prof


def mux(out_path, v_path, v_pkt, v_enc, a_path, a_pkt, a_enc):
    v_cur = marm.rtp.RTPCursor(
        [v_path.strpath],
        marm.rtp.RTPPacketReader.open,
        packet_type=v_pkt,
    )
    v_prof = probe(v_cur)

    a_cur = marm.rtp.RTPCursor(
        [a_path.strpath],
        marm.rtp.RTPPacketReader.open,
        packet_type=a_pkt,
    )
    a_prof = probe(a_cur)

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
