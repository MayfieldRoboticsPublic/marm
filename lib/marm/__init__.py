"""
"""
import itertools
import os

__version__ = '0.0.0'

__all__ = [
    'rtp'
    'vp8',
    'opus',
    'Frame',
    'Frames',
    'VideoFrame',
    'VideoFrames',
    'MARM',
    'MARMWriter',
    'MJR',
    'MJRWriter',
    'head_packets',
    'codecs',
    'generate_audio',
    'generate_video',
    'mux',
    'probe_format'
]

from . import rtp
from . import vp8
from . import opus
from .frame import Frame, Frames, VideoFrame, VideoFrames
from .archive import MARM, MARMWriter, MJR, MJRWriter


def head_packets(packets, count=None, duration=None):
    s = {
        'epoch': None,
        'count': 0
    }

    def _duration(pkt):
        if s['epoch'] is None:
            s['epoch'] = pkt.secs
        return pkt.secs - s['epoch'] < duration
    
    def _count(pkt):
        s['count'] += 1
        return s['count'] < count
    
    ps = []
    if duration is not None:
        ps.append(_duration)
    if count is not None:
        ps.append(_count)
    predicate = lambda pkt: all(p(pkt) for p in ps)

    return itertools.takewhile(predicate, packets)

# extension

from . import ext


#
codecs = ext.codecs


def generate_audio(fo, encoder=None, **kwargs):
    """
    """
    if encoder is None:
        _, extension = os.path.splitext(fo.name)
        if not extension:
            raise ValueError('fo.name "{0}" has no extension.'.format(fo.name))
        encoder = extension[1:]
    ext.generate_audio(
            fo,
            encoder,
            **kwargs
        )


def generate_video(fo, encoder=None, **kwargs):
    """
    """
    if encoder is None:
        _, extension = os.path.splitext(fo.name)
        if not extension:
            raise ValueError('fo.name "{0}" has no extension.'.format(fo.name))
        encoder = extension[1:]
    ext.generate_video(
            fo,
            encoder,
            **kwargs
        )


#
formats = ext.output_formats


def mux(
            fo,
            video_profile=None,
            video_packets=None,
            audio_profile=None,
            audio_packets=None,
            format_extension=None
        ):
    """
    """
    if format_extension is None:
        _, format_extension = os.path.splitext(fo.name)
        if not format_extension:
            raise ValueError('fo.name "{0}" has no extension.'.format(fo.name))
    ext.mux(
            fo,
            format_extension,
            v_profile=video_profile,
            v_packets=video_packets,
            a_profile=audio_profile,
            a_packets=audio_packets
        )

def stat(fo, format_extension=None):
    if format_extension is None:
        _, format_extension = os.path.splitext(fo.name)
        if not format_extension:
            raise ValueError('fo.name "{0}" has no extension.'.format(fo.name))
    return ext.stat(fo, format_extension)
