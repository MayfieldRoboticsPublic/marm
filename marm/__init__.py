"""
This is a libav* front-end used to:

- Read stored/archived media (e.g. pcap'd rtp packets).
- Reconstruct frame data (e.g. depacketize a frame from its rtp packets).
- Synchronize reconstructed streams of frame data (e.g. audio and video).
- Mux stream(s) to a container (e.g. mkv file) using libav*.

The motivating use case is depacketizing and synchronizing RTP streams to a mkv
file which you can do e.g. like:

.. code:: python

    import marm
    
    TODO

"""
__version__ = '0.0.0'

__all__ = [
    'Frame',
    'Frames',
    'VideoFrame',
    'VideoFrames',
    'Codec',
    'codecs',
    'Format',
    'formats',
    'gen_audio_frames',
    'gen_video_frames',
    'mux_frames',
    'stat_format',
    'raw',
    'rtp',
    'opus',
    'mjr',
    'pcap',
]

# frames
from .frame import (
    Frame,
    Frames,
    VideoFrame,
    VideoFrames,
    Codec,
    codecs,
    Format,
    formats,
    gen_audio_frames,
    gen_video_frames,
    mux_frames,
    stat_format)
from . import raw

# packets
from . import rtp
from . import vp8
from . import opus

# stored packets
from . import mjr
from . import pcap
