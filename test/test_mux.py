import pytest

import marm


@pytest.mark.parametrize(
        ('duration,'
         'v_encoder,v_width,v_height,v_frame_rate,'
         'a_encoder,a_bit_rate,a_sample_rate,'
         'fmt'), [
        (3, 'mpeg4', 320, 240, 25, 'flac', 96000, 48000, 'mkv'),
    ])
def test_mux_gen(
            tmpdir,
            duration,
            v_encoder, v_width, v_height, v_frame_rate,
            a_encoder, a_bit_rate, a_sample_rate,
            fmt
        ):
    v_path = tmpdir.join('v.{0}'.format(v_encoder))
    with v_path.open('wb') as fo:
        marm.generate_video(
                fo,
                duration=duration,
                width=v_width,
                height=v_height,
                frame_rate=v_frame_rate
            )

    a_path = tmpdir.join('a.{0}'.format(a_encoder))
    with a_path.open('wb') as fo:
        marm.generate_audio(
                fo,
                duration=duration,
                bit_rate=a_bit_rate,
                sample_rate=a_sample_rate,
            )

    a_arch = marm.MARM(str(a_path), 'rb')
    a_hdr = a_arch.header()
    a_pkts = a_arch.packets()

    v_arch = marm.MARM(str(v_path), 'rb')
    v_hdr = v_arch.header()
    v_pkts = v_arch.packets()

    m_path = tmpdir.join('m.{0}'.format(fmt))
    with m_path.open('wb') as fo:
        marm.mux(
            fo,
            audio_profile={
                'encoder_name': a_hdr.encoder_name,
                'bit_rate': a_hdr.bit_rate,
                'sample_rate': a_hdr.sample_rate,
            },
            audio_packets=a_pkts,
            video_profile={
                'encoder_name': v_hdr.encoder_name,
                'pix_fmt': v_hdr.pix_fmt,
                'width': v_hdr.width,
                'height': v_hdr.height,
                'frame_rate': v_hdr.frame_rate,
                'bit_rate': v_hdr.bit_rate,
    
            },
            video_packets=v_pkts,
        )

    with m_path.open('rb') as fo:
        m_stat = marm.stat(fo)
    assert m_stat.nb_streams == 2
    assert fmt in m_stat.iformat.extensions.split(',')
