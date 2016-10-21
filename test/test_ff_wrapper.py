from datetime import timedelta

import pytest

import marm


@pytest.mark.parametrize(
    'file_name,args,as_fo,expected', [
        ('sonic.ts', ['-select_streams', 'a'], False, {
            1: {'codec_type': u'audio',
                'dts': 10931520,
                'dts_time': 121.461333,
                'duration': 1920,
                'duration_time': 0.021333,
                'flags': u'K_',
                'pts': 10931520,
                'pts_time': 121.461333,
                'size': 14,
                'stream_index': 1}
         }),
        ('sonic.ts', ['-select_streams', 'a'], True, {
            1: {'codec_type': u'audio',
                'dts': 10931520,
                'dts_time': 121.461333,
                'duration': 1920,
                'duration_time': 0.021333,
                'flags': u'K_',
                'pts': 10931520,
                'pts_time': 121.461333,
                'size': 14,
                'stream_index': 1}
         }),
    ]
)
def test_ffprobe_last_packet(fixtures, file_name, args, as_fo, expected):
    p = fixtures.join(file_name)
    if as_fo:
        with p.open('rb') as fo:
            r = marm.FFProbe.for_last_packet(*(args + ['-']), stdin=fo)
    else:
        r = marm.FFProbe.for_last_packet(*(args + [p.strpath]))
    assert r == expected


@pytest.mark.parametrize(
    'file_name,expected_stream,expected_format', [
        ('sonic.ts',
         timedelta(seconds=120.033333),
         timedelta(seconds=120.054667)),
    ]
)
def test_ffprobe_duration(
        fixtures,
        file_name,
        expected_stream,
        expected_format):
    p = fixtures.join(file_name)
    assert marm.FFProbe.for_stream_duration(p.strpath) == expected_stream
    assert marm.FFProbe.for_format_duration(p.strpath) == expected_format
