import StringIO

import pytest

import marm


@pytest.mark.parametrize(
    'file_name,packet_type,frames_type,frame_type', [
        ('empty.mjr',
         marm.vp8.VP8RTPPacket,
         marm.VideoFrames,
         marm.VideoFrame),
        ('sonic-a.mjr',
         marm.opus.OpusRTPPacket,
         marm.Frames,
         marm.AudioFrame),
        ('sonic-v.mjr',
         marm.vp8.VP8RTPPacket,
         marm.VideoFrames,
         marm.VideoFrame),
    ]
)
def test_frame_packing(
        tmpdir,
        fixtures,
        file_name,
        packet_type,
        frames_type,
        frame_type):
    pkts = marm.rtp.RTPPacketReader.open(
        fixtures.join(file_name).strpath,
        packet_type=packet_type,
    )
    frames = list(frames_type(pkts))
    frames_file = tmpdir.join('frames')
    with frames_file.open('wb') as fo:
        for frame in frames:
            frame.pack(fo)
    frames2 = []
    with frames_file.open('rb') as fo:
        for _ in range(len(frames)):
            frames2.append(frame_type(fo))


@pytest.mark.parametrize(
    'file_name,packet_type,header_type', [
        ('sonic-a.mjr',
         marm.opus.OpusRTPPacket,
         marm.frame.AudioHeader),
        ('sonic-v.mjr',
         marm.vp8.VP8RTPPacket,
         marm.frame.VideoHeader),
    ]
)
def test_frame_headers(
        tmpdir,
        fixtures,
        file_name,
        packet_type,
        header_type):
    pkts = marm.rtp.RTPCursor(
        [fixtures.join(file_name).strpath],
        packet_type=packet_type,
    )
    prof = dict(
        (k, int(v) if isinstance(v, float) else v)
        for k, v in pkts.probe().iteritems()
    )
    header = header_type(encoder_name='anything', **prof)
    io = StringIO.StringIO()
    io.write(header.pack())
    io.seek(0)
    assert header == header_type.unpack(io)
