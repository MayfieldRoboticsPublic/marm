from __future__ import division

import collections
import logging
import os
import StringIO
import struct

from . import ext


logger = logging.getLogger(__name__)


class Frame(object):
    """
    Represents a frame as a tuple of:
    
    - pts
    - flags
    - data
    
    corresponding to `libavcodec.AVPacket`.
    """

    def __init__(self, *args, **kwargs):
        if args:
            if kwargs:
                raise TypeError('Mixed positional and keyword arguments')
            elif len(args) > 1:
                raise TypeError('Expected single \'buf\' arg')
            self.unpack(args[0])
        elif kwargs:
            if len(kwargs) == 1 and 'buf' in kwargs:
                self.unpack(kwargs['buf'])
            else:
                self.pts, self.flags, self.data = 0, 0, ''
                for k, v in kwargs.iteritems():
                    if k not in ('pts', 'flags', 'data'):
                        raise TypeError('Unexpected keyword argument \'{0}\''.format(k))
                    setattr(self, k, v)

    def unpack(self, buf):
        fo = StringIO.StringIO(buf) if isinstance(buf, basestring) else buf
        fmt = '=qii'
        size = struct.calcsize(fmt)
        b = fo.read(size)
        if len(b) != size:
            raise ValueError('Failed to read {0} bytes for "{1}" at {2}.'.format(size, fmt, fo.tell()))
        pts, flags, data_size = struct.unpack(fmt, b)
        data = fo.read(data_size)
        if len(data) != data_size:
            raise ValueError('Failed to read {0} byte packet data at {1}.'.format(data_size, fo.tell()))
        self.pts, self.flags, self.data = pts, flags, data

    def pack(self, fo=None):
        fo, value = StringIO.StringIO(), True if fo is None else fo, False
        fo.write(struct.pack('=qii', self.pts, self.flags, len(self.data)))
        fo.write(self.data)
        if value:
            return fo.getvalue()


class Frames(collections.Iterator):
    """
    Depacketizes of `Frame`s assumes one packet/frame.
    """

    def __init__(self, packets, pts_delay=0):
        self.packets = iter(packets)
        self.pts_delay = pts_delay
        self.pts_offset = None

    # collections.Iterator

    def __iter__(self):
        return self

    def next(self):
        packet = self.packets.next()
        if self.pts_offset is None:
            self.pts_offset = -int(packet.msecs) + self.pts_delay
        return Frame(
            pts=int(packet.msecs) + self.pts_offset,
            flags=0,
            data=packet.data,
        )


class VideoFrame(Frame):
    """
    Convenience specialization of `Frame` for video.
    """

    FLAG_KEY_FRAME = 1 << 0  # AV_PKT_FLAG_KEY
    FLAG_CORRUPT = 1 << 1  # AV_PKT_FLAG_CORRUPT

    PIX_FMT_NONE = -1  # AV_PIX_FMT_NONE
    PIX_FMT_YUV420P = 0  # AV_PIX_FMT_YUV420P
    PIX_FMT_YUYV422 = 1  # AV_PIX_FMT_YUYV422
    PIX_FMT_RGB24 = 2  # AV_PIX_FMT_RGB24

    @property
    def is_key_frame(self):
        return self.flags & self.FLAG_KEY_FRAME != 0

    @property
    def is_corrupt(self):
        return self.flags & self.FLAG_CORRUPT != 0


class VideoFrames(collections.Iterator):
    """
    Depacketizes `VideoFrame`s. There may be more than one packet/frame and to
    group them inot a single `VideoFrame` the packet data should support:
    
    - `RTPVideoPayloadMixin`.
    
    """

    def __init__(self, packets):
        self.packets = iter(packets)
        try:
            self.packet = self.packets.next()
        except StopIteration:
            self.packet = None
        if self.packet:
            self.packet, self.start_frame_offset = self._seek_start_frame()
        if self.packet:
            self.packet, self.key_frame_offset = self._seek_key_frame()
        self.pts_offset = -int(self.packet.msecs) if self.packet else 0

    def _seek_start_frame(self):
        packet = self.packet

        # already there
        if packet.data.is_start_of_frame:
            return packet, 0

        # forward
        offset = 0
        for packet in self.packets:
            if packet.data.is_start_of_frame:
                return packet, offset
            offset += 1
            logger.debug('dropping non-frame-start packet')

        # nothing
        return None, offset

    def _seek_key_frame(self):
        packet = self.packet

        # already there
        if packet.data.is_key_frame:
            return packet, 0

        # forward
        offset = 0
        for packet in self.packets:
            if packet.data.is_start_of_frame and packet.data.is_key_frame:
                return packet, offset
            if not packet.data.is_start_of_frame:
                offset += 1
                logger.debug('dropping non-key-frame-start packet')

        return None, offset

    def _read_frame(self):
        first = self.packet

        # meta
        pts, flags = int(first.msecs) + self.pts_offset, 0
        if first.data.header.is_key_frame:
            flags |= VideoFrame.FLAG_KEY_FRAME

        # data
        fo = StringIO.StringIO()
        fo.write(first.data.data)
        count = 1
        for self.packet in self.packets:
            if self.packet.data.is_start_of_frame:
                break
            fo.write(self.packet.data.data)
            count += 1
        else:
            self.packet = None
        data = fo.getvalue()

        return VideoFrame(pts=pts, flags=flags, data=data)

    # collections.Iterator

    def __iter__(self):
        return self

    def next(self):
        if self.packet is None:
            raise StopIteration()
        if not self.packet.data.is_start_of_frame:
            logger.debug('dropping non-frame-start packet')
            for self.packet in self.packet:
                if self.packet.data.is_start_of_frame:
                    break
                logger.debug('dropping non-frame-start packet')
            else:
                raise StopIteration()
        return self._read_frame()


# libav* codec.
Codec = ext.Codec


# Iterates `ext.Codec`s registered with libav*.
codecs = ext.codecs


def gen_audio_frames(fo, encoder=None, **kwargs):
    """
    Generates encoded audio frames which is useful for testing.
    """
    if encoder is None:
        _, extension = os.path.splitext(fo.name)
        if not extension:
            raise ValueError('fo.name "{0}" has no extension.'.format(fo.name))
        encoder = extension[1:]
    ext.generate_audio(fo, encoder, **kwargs)


def gen_video_frames(fo, encoder=None, **kwargs):
    """
    Generates encoded video frames which is useful for testing.
    """
    if encoder is None:
        _, extension = os.path.splitext(fo.name)
        if not extension:
            raise ValueError('fo.name "{0}" has no extension.'.format(fo.name))
        encoder = extension[1:]
    ext.generate_video(fo, encoder, **kwargs)


# libav* format.
Format = ext.Format


# Iterates Formats registered with libav*.
formats = ext.output_formats


def mux_frames(fo,
        video_profile=None,
        video_packets=None,
        audio_profile=None,
        audio_packets=None,
        format_extension=None):
    """
    Muxes encoded video and audio frames (i.e. codec packets) into a container.
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


def stat_format(fo, format_extension=None):
    """
    Probes format information.
    """
    if format_extension is None:
        _, format_extension = os.path.splitext(fo.name)
        if not format_extension:
            raise ValueError('fo.name "{0}" has no extension.'.format(fo.name))
    return ext.stat(fo, format_extension)
