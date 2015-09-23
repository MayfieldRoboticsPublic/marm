import pytest

import marm


@pytest.mark.parametrize(
    ('duration,'
     'v_encoder,v_width,v_height,v_frame_rate,'
     'a_encoder,a_bit_rate,a_sample_rate,'
     'fmt'), [
    (5, 'mpeg4', 320, 240, 25, 'flac', 96000, 48000, 'mkv'),
])
def test_mux_gen(
        tmpdir,
        duration,
        v_encoder, v_width, v_height, v_frame_rate,
        a_encoder, a_bit_rate, a_sample_rate,
        fmt):
    v_path = tmpdir.join('v.{0}'.format(v_encoder))
    a_path = tmpdir.join('a.{0}'.format(a_encoder))
    m_path = tmpdir.join('m.{0}'.format(fmt))

    with v_path.open('wb') as fo:
        marm.gen_video_frames(
                fo,
                duration=duration,
                width=v_width,
                height=v_height,
                frame_rate=v_frame_rate
            )

    with a_path.open('wb') as fo:
        marm.gen_audio_frames(
                fo,
                duration=duration,
                bit_rate=a_bit_rate,
                sample_rate=a_sample_rate,
            )

    with m_path.open('wb') as fo, \
            v_path.open('rb') as v_fo, \
            a_path.open('rb') as a_fo:
        # a
        a_hdr = marm.raw.read_header(a_fo)
        a_frames = marm.raw.read_frames(a_fo)

        # v
        v_hdr = marm.raw.read_header(v_fo)
        v_frames = marm.raw.read_frames(v_fo)

        # mux them
        marm.mux_frames(
            fo,
            audio_profile={
                'encoder_name': a_hdr.encoder_name,
                'bit_rate': a_hdr.bit_rate,
                'sample_rate': a_hdr.sample_rate,
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

    with m_path.open('rb') as fo:
        m_stat = marm.stat_format(fo)
    assert m_stat.nb_streams == 2
    assert fmt in m_stat.iformat.extensions.split(',')
