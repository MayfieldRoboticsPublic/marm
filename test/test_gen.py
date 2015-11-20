import StringIO

import mock
import pytest

import marm


@pytest.mark.parametrize(
    'encoder_name,duration,width,height,frame_rate,frame_count', [
        ('mpeg4', 11, 320, 240, 25, 275),
        ('mpeg4', 5, 640, 480, 30, 150),
    ])
def test_gen_video_frames(
            tmpdir,
            encoder_name,
            duration,
            width,
            height,
            frame_rate,
            frame_count,
        ):
    path = tmpdir.join('v.{0}'.format(encoder_name))
    with path.open('wb') as fo:
        marm.frame.gen_video(
                fo,
                duration=duration,
                width=width,
                height=height,
                frame_rate=frame_rate
            )
    with path.open('rb') as fo:
        header = marm.frame.read_header(fo)
        assert header == marm.frame.VideoHeader(
            encoder_name=encoder_name,
            pix_fmt=0,
            width=width,
            height=height,
            bit_rate=400000,
            frame_rate=frame_rate,
        )
        c = 0
        for _ in marm.frame.read_frames(fo):
            c += 1
        assert c == frame_count


def test_gen_video_frames_write_error(tmpdir):

    class MyException(Exception):

        pass

    encoder, duration, width, height, frame_rate, = 'mpeg4', 5, 640, 480, 30
    io = StringIO.StringIO()
    with mock.patch.object(io, 'write') as p:
        p.side_effect = MyException('bam')
        with pytest.raises(MyException) as ei:
            marm.frame.gen_video(
                io,
                duration=duration,
                encoder_name=encoder,
                pix_fmt=0,
                width=width,
                height=height,
                bit_rate=400000,
                frame_rate=frame_rate,
            )
        assert 'bam' in ei.value


@pytest.mark.parametrize(
    'encoder_name,duration,bit_rate,sample_rate,channel_layout,frame_count', [
        ('flac', 11, 96000, 48000, marm.AudioFrame.CHANNEL_LAYOUT_STEREO, 115),
        ('flac', 5, 128000, 44100, marm.AudioFrame.CHANNEL_LAYOUT_MONO, 48),
    ])
def test_gen_audio_frames(
        tmpdir,
        encoder_name,
        duration,
        bit_rate,
        sample_rate,
        channel_layout,
        frame_count):
    path = tmpdir.join('a.{0}'.format(encoder_name))
    with path.open('wb') as fo:
        marm.frame.gen_audio(
            fo,
            duration=duration,
            bit_rate=bit_rate,
            sample_rate=sample_rate,
            channel_layout=channel_layout
        )

    with path.open('rb') as fo:
        header = marm.frame.read_header(fo)
        assert header == marm.frame.AudioHeader(
            encoder_name=encoder_name,
            bit_rate=bit_rate,
            sample_rate=sample_rate,
            channel_layout=channel_layout,
        )
        c = sum(1 for _ in marm.frame.read_frames(fo))
        assert abs(c - frame_count) < 2


def test_gen_audio_frames_write_error(tmpdir):

    class MyException(Exception):

        pass

    encoder, duration, bit_rate, sample_rate = 'libopus', 10, 96000, 48000
    io = StringIO.StringIO()
    with mock.patch.object(io, 'write') as p:
        p.side_effect = MyException('boom')
        with pytest.raises(MyException) as ei:
            marm.frame.gen_audio(
                io,
                encoder_name=encoder,
                duration=duration,
                bit_rate=bit_rate,
                sample_rate=sample_rate,
            )
        assert 'boom' in ei.value
