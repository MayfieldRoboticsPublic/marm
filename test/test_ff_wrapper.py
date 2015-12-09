import pytest

import marm


@pytest.mark.parametrize(
    'file_name,args,as_fo,expected', [
        ('sonic.ts', ['-select_streams', 'a'], False, {
            0: None,
            1: {'codec_type': u'audio',
                'dts': 10931520,
                'dts_time': 121.461333,
                'duration': 1920,
                'duration_time': 0.021333,
                'flags': u'K',
                'pts': 10931520,
                'pts_time': 121.461333,
                'size': 14,
                'stream_index': 1}
         }),
        ('sonic.ts', ['-select_streams', 'a'], True, {
            0: None,
            1: {'codec_type': u'audio',
                'dts': 10931520,
                'dts_time': 121.461333,
                'duration': 1920,
                'duration_time': 0.021333,
                'flags': u'K',
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
