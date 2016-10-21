"""
`libav* <http://www.ffmpeg.org/>`_ front-end used to:

- Read stored/archived media (e.g. `pcap <http://www.tcpdump.org/pcap.html>`_ed `rtp <https://tools.ietf.org/html/rfc3550>`_ packets).
- Reconstruct frames (e.g. depacketize a frame from its rtp packets).
- Synchronize reconstructed streams of frame data (e.g. audio and video).
- Mux frame stream(s) to a container (e.g. `mkv <http://www.matroska.org/>`_ file) using libav*.

Motivating use case was:

- depacketizing rtp payloads from `mjr <https://github.com/meetecho/janus-gateway>`_ files and 
- muxing them to an mkv file

which you can do e.g. like:

.. code:: python

    import marm
    
    v_pkts = marm.mjr.MJRRTPPacketReader(
        'path/to/video.mjr', 'rb',
        packet_type=marm.vp8.VP8RTPPacket,
    )
    v_width, v_height = marm.rtp.probe_video_dimensions(v_pkts)
    v_pkts.reset()
    v_frame_rate = marm.rtp.estimate_video_frame_rate(v_pkts, window=10)
    v_pkts.reset()
    v_frames = marm.VideoFrames(v_pkts)
    
    a_pkts = marm.mjr.MJRRTPPacketReader(
        'path/to/audio.mjr', 'rb',
        packet_type=marm.opus.OpusRTPPacket,
    )
    a_frames = marm.Frames(a_pkts)
    
    with open('path/to/muxed.mkv', 'wb') as mkv_fo:
        marm.frame.mux(
            mkv_fo,
            audio_profile={
                'encoder_name': 'libopus',
                'bit_rate': 96000,
                'sample_rate': 48000,
                'time_base': (1, 1000),
            },
            audio_packets=a_frames,
            video_profile={
                'encoder_name': 'libpvx',
                'pix_fmt': marm.VideoFrame.PIX_FMT_YUV420P,
                'width': v_width,
                'height': v_height,
                'frame_rate': v_frame_rate,
                'bit_rate': 4000000,
                'time_base': (1, 1000),
            },
            video_packets=v_frames,
        )

"""
__version__ = '0.3.0'

__all__ = [
    'Frame',
    'Frames',
    'AudioFrame',
    'VideoFrame',
    'VideoFrames',
    'FrameProxy',
    'FrameFilter',
    'frame',
    'rtp',
    'opus',
    'mjr',
    'pcap',
    'FFProbe',
    'FFMPEG',
]

# frames
from .frame import (
    Frame,
    Frames,
    AudioFrame,
    VideoFrame,
    VideoFrames,
    FrameProxy,
    FrameFilter,
)
from . import frame

# packets
from . import rtp
from . import vp8
from . import opus

# stored packets
from . import mjr
from . import pcap

# helper
from .ffmpeg import FFProbe, FFMPEG
