from __future__ import division

import collections
import logging
import StringIO
import struct


logger = logging.getLogger(__name__)


class Frame(object):
    """
    """

    def __init__(self, pts, flags, data):
        self.pts = pts
        self.flags = flags
        self.data = data

    @classmethod
    def load(cls, io):
        fmt = '=qii'
        size = struct.calcsize(fmt)
        b = io.read(size)
        if len(b) != size:
            raise ValueError('Failed to read {0} bytes for "{1}" at {2}.'.format(size, fmt, io.tell()))
        pts, flags, data_size = struct.unpack(fmt, b)
        data = io.read(data_size)
        if len(data) != data_size:
            raise ValueError('Failed to read {0} byte packet data at {1}.'.format(data_size, io.tell()))
        return cls(
            pts=pts,
            flags=flags,
            data=data,
        )

    def dump(self, io):
        io.write(struct.pack('=qii', self.pts, self.flags, len(self.data)))
        io.write(self.data)


class Frames(collections.Iterator):
    """
    """

    def __init__(self, packets):
        self.packets = packets
        self.pts_offset = None

    # collections.Iterator

    def __iter__(self):
        return self

    def next(self):
        packet = self.packets.next()
        if self.pts_offset is None:
            self.pts_offset = -int(packet.msecs)
        return Frame(
                pts=int(packet.msecs) + self.pts_offset,
                flags=0,
                data=packet.payload,
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

    def __init__(self, pts, flags, data, width, height):
        super(VideoFrame, self).__init__(pts, flags, data)
        self.width = width
        self.height = height

    @property
    def dimensions(self):
        return (self.width, self.height)

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
        if packet.is_start_of_frame:
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
            if packet.is_start_of_frame:
                return packet, offset
            offset += 1
            logger.debug('dropping non-frame-start packet @ %s', packet.location)

        # nothing
        return None, offset

    def _seek_key_frame(self):
        packet = self.packet

        # already there
        if packet.is_key_frame:
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
            if packet.is_start_of_frame and packet.is_key_frame:
                return packet, offset
            if not packet.is_start_of_frame:
                offset += 1
                logger.debug('dropping non-key-frame-start packet @ %s', packet.location)

        return None, offset

    def _read_frame(self):
        first = self.packet

        # meta
        pts, flags, width, height = int(first.msecs) + self.pts_offset, 0, None, None
        if first.vp8_header.is_key_frame:
            flags |= VideoFrame.FLAG_KEY_FRAME
            width = first.width
            height = first.height

        # data
        data = StringIO.StringIO()
        data.write(first.payload)
        for self.packet in self.packets:
            if self.packet.is_start_of_frame:
                break
            data.write(self.packet.payload)
        else:
            self.packet = None
        data = data.getvalue()

        return VideoFrame(
            pts=pts,
            flags=flags,
            width=width,
            height=height,
            data=data,
        )

    # collections.Iterator

    def __iter__(self):
        return self

    def next(self):
        if self.packet is None:
            raise StopIteration()
        if not self.packet.is_start_of_frame:
            logger.debug('dropping non-frame-start packet @ %s', self.packet.location)
            for self.packet in self.packet:
                if self.packet.is_start_of_frame:
                    break
                logger.debug('dropping non-frame-start packet @ %s', self.packet.location)
            else:
                raise StopIteration()
        return self._read_frame()
