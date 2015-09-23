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
    """

    def __init__(self, *args, **kwargs):
        if args:
            if kwargs:
                raise TypeError('Mixed positional and keyword arguments')
            elif len(args) > 1:
                raise TypeError('Expected single \'buf\' arg')
            unpack = (
                self.unpacks
                if isinstance(args[0], basestring)
                else self.unpack
            )
            unpack(args[0])
        elif kwargs:
            if len(kwargs) == 1 and 'buf' in kwargs:
                unpack = (
                    self.unpack
                    if isinstance(args[0], basestring)
                    else self.unpacks
                )
                unpack(kwargs['buf'])
            else:
                self.pts, self.flags, self.data = 0, 0, ''
                for k, v in kwargs.iteritems():
                    if k not in ('pts', 'flags', 'data'):
                        raise TypeError('Unexpected keyword argument \'{0}\''.format(k))
                    setattr(self, k, v)

    def unpack(self, io):
        fmt = '=qii'
        size = struct.calcsize(fmt)
        b = io.read(size)
        if len(b) != size:
            raise ValueError('Failed to read {0} bytes for "{1}" at {2}.'.format(size, fmt, io.tell()))
        pts, flags, data_size = struct.unpack(fmt, b)
        data = io.read(data_size)
        if len(data) != data_size:
            raise ValueError('Failed to read {0} byte packet data at {1}.'.format(data_size, io.tell()))
        self.pts, self.flags, self.data = pts, flags, data
    
    def unpacks(self, buf):
        io = StringIO.StringIO(buf)
        return self.unpack(io)

    def pack(self, io):
        io.write(struct.pack('=qii', self.pts, self.flags, len(self.data)))
        io.write(self.data)
        
    def packs(self):
        io = StringIO.StringIO()
        self.pack(io)
        return io.getvalue()


class Frames(collections.Iterator):
    """
    """

    def __init__(self, packets, pts_delay=0):
        self.packets = packets
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
    """

    def __init__(self, packets):
        self.packets = packets
        try:
            self.packet = packets.next()
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

        # back
#        if isinstance(self.packets, Packets):
#            i = self.packets.window.last(lambda packet: packet.is_start_of_frame)
#            if i != -1:
#                offset = -(len(self.packets.window) - i) + 1
#                self.packets.prev(i)
#                packet = self.packets.next()
#                logger.debug('found frame-start packet @ %s', packet.location)
#                return packet, offset

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

        # back
#        if isinstance(self.packets, Packets):
#            i = self.packets.window.last(lambda packet: packet.is_start_of_frame and packet.is_key_frame)
#            if i != -1:
#                offset = self.packets.window[i:].count(lambda packet: packet.is_start_of_frame)
#                self.packets.prev(i)
#                packet = self.packets.next()
#                logger.debug('found key-frame-start packet @ %s', packet.location)
#                return packet, offset

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
        io = StringIO.StringIO()
        io.write(first.data.data)
        for self.packet in self.packets:
            if self.packet.data.is_start_of_frame:
                break
            io.write(self.packet.data.data)
        else:
            self.packet = None
        data = io.getvalue()

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


# Iterates `ext.Codec`s registered w/ libav*.
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
