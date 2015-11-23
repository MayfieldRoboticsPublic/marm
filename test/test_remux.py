import collections

import pytest

import marm


class frame_filter(marm.FrameFilter):

    def __init__(self):
        super(frame_filter, self).__init__()
        self.c = collections.Counter()


class keep_all(frame_filter):

    def __call__(self, frame):
        return self.KEEP_ALL


class keep_n(frame_filter):

    def __init__(self, n):
        super(keep_n, self).__init__()
        self.n = n

    def __call__(self, frame):
        self.c[frame.stream_index] += 1
        return (
            self.KEEP
            if self.c[frame.stream_index] <= self.n
            else self.DROP
        )


class drop_n(frame_filter):

    def __init__(self, n):
        super(drop_n, self).__init__()
        self.n = n

    def __call__(self, frame):
        self.c[frame.stream_index] += 1
        return (
            self.DROP
            if self.c[frame.stream_index] <= self.n
            else self.KEEP
        )


@pytest.mark.parametrize(
    'v_store,v_pkt,v_enc,a_store,a_pkt,a_enc,fmt,filter,counts', [
        ('sonic-v.mjr', marm.vp8.VP8RTPPacket, 'libvpx',
         'sonic-a.mjr', marm.opus.OpusRTPPacket, 'libopus',
         'mkv',
         keep_all(),
         {0: {'packets': 3555, 'frames': 3555},
          1: {'packets': 5996, 'frames': 5996}}),
        ('sonic-v.mjr', marm.vp8.VP8RTPPacket, 'libvpx',
         'sonic-a.mjr', marm.opus.OpusRTPPacket, 'libopus',
         'mkv',
         keep_n(10),
         {0: {'packets': 10, 'frames': 10},
          1: {'packets': 10, 'frames': 10}}),
        ('sonic-v.mjr', marm.vp8.VP8RTPPacket, 'libvpx',
         'sonic-a.mjr', marm.opus.OpusRTPPacket, 'libopus',
         'mkv',
         drop_n(10),
         {0: {'packets': 3545, 'frames': 3523},
          1: {'packets': 5986, 'frames': 5986}}),
    ]
)
def test_remux_filter(
        fixtures,
        tmpdir,
        v_store, v_pkt, v_enc,
        a_store, a_pkt, a_enc,
        fmt,
        filter,
        counts):
    # mux
    m1 = tmpdir.join('1.{0}'.format(fmt))
    pytest.mux(
        m1,
        fixtures.join(v_store), v_pkt, v_enc,
        fixtures.join(a_store), a_pkt, a_enc,
    )

    # remux it w/ filter
    m2 = tmpdir.join('2.{0}'.format(fmt))
    with m1.open('rb') as i, m2.open('wb') as o:
        marm.frame.remux(o, i, filter)

    # counts
    p = marm.FFProbe([
        '-count_packets',
        '-count_frames',
        '-show_streams',
        m2.strpath,
    ])
    p()
    assert counts == dict([(s['index'], {
        'packets': s['nb_read_packets'],
        'frames': s['nb_read_frames'],
    }) for s in p.result['streams']])
