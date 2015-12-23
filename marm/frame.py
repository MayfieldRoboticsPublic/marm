from __future__ import division

import abc
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

    FLAG_KEY_FRAME = 1 << 0  # AV_PKT_FLAG_KEY
    FLAG_CORRUPT = 1 << 1  # AV_PKT_FLAG_CORRUPT

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

    @property
    def is_key_frame(self):
        return self.flags & self.FLAG_KEY_FRAME != 0

    @property
    def is_corrupt(self):
        return self.flags & self.FLAG_CORRUPT != 0

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
        fo, value = (StringIO.StringIO(), True) if fo is None else (fo, False)
        fo.write(struct.pack('=qii', self.pts, self.flags, len(self.data)))
        fo.write(self.data)
        if value:
            return fo.getvalue()


class Frames(collections.Iterator):
    """
    Depacketizes `Frame`s assuming each packet is a frame.
    """

    def __init__(self, packets, pts_offset=0, pts='msecs', flags=0, frame_type=Frame):
        self.packets = iter(packets)
        self.pts = pts
        self.pts_offset = pts_offset
        self.flags = flags
        self.frame_type = frame_type

    # collections.Iterator

    def __iter__(self):
        return self

    def next(self):
        packet = self.packets.next()
        pts = int(getattr(packet, self.pts) + self.pts_offset)
        return self.frame_type(
            pts=pts,
            flags=self.flags,
            data=packet.data.data
        )

class VideoFrame(Frame):
    """
    Convenience specialization of `Frame` for video.
    """

    PIX_FMT_NONE = -1  # AV_PIX_FMT_NONE
    PIX_FMT_YUV420P = 0  # AV_PIX_FMT_YUV420P
    PIX_FMT_YUYV422 = 1  # AV_PIX_FMT_YUYV422
    PIX_FMT_RGB24 = 2  # AV_PIX_FMT_RGB24


class AudioFrame(Frame):
    """
    Convenience specialization of `Frame` for audio.
    """

    CHANNEL_LAYOUT_MONO = ext.AV_CH_LAYOUT_MONO
    CHANNEL_LAYOUT_STEREO = ext.AV_CH_LAYOUT_STEREO

    def __init__(self, *args, **kwargs):
        if not(len(args) == 1 and not kwargs):
            kwargs['flags'] = kwargs.pop('flags', 0) | Frame.FLAG_KEY_FRAME
        super(AudioFrame, self).__init__(*args, **kwargs)


class VideoFrames(collections.Iterator):
    """
    Depacketizes `VideoFrame`s. There may be more than one packet/frame and to
    group them into a single `VideoFrame` the packet data should support:
    
    - `RTPVideoPayloadMixin`.
    
    """

    def __init__(self, packets, pts_offset=0, pts='msecs'):
        self.packets = iter(packets)
        self.pts = pts
        try:
            self.packet = self.packets.next()
        except StopIteration:
            self.packet = None
        if self.packet:
            self.packet, self.start_frame_offset = self._seek_start_frame()
        if self.packet:
            self.packet, self.key_frame_offset = self._seek_key_frame()
        self.pts_offset = pts_offset

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
        pts, flags = int(getattr(first, self.pts) + self.pts_offset), 0
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
        packet = self._read_frame()
        if packet is None:
            raise StopIteration()
        return packet


# libav* codec.
Codec = ext.Codec


# Iterates `ext.Codec`s registered with libav*.
codecs = ext.codecs


def gen_audio(fo=None, encoder_name=None, **kwargs):
    """
    Generates encoded audio frames which is useful for testing.
    """
    encoder_name = encoder_name or format_ext(fo, 'fo')[1:]
    if fo is None:
        fo = StringIO.StringIO()
        ext.generate_audio(
            fo,
            encoder_name,
            header=False,
            **kwargs)
        fo.seek(0)
        return read_frames(fo)
    return ext.generate_audio(fo, encoder_name, **kwargs)


def gen_video(fo, encoder_name=None, **kwargs):
    """
    Generates encoded video frames which is useful for testing.
    """
    encoder_name = encoder_name or format_ext(fo, 'fo')[1:]
    return ext.generate_video(fo, encoder_name, **kwargs)


# libav* format.
Format = ext.Format


# Iterates Formats registered with libav*.
formats = ext.output_formats


def mux(fo,
        video_profile=None,
        video_packets=None,
        audio_profile=None,
        audio_packets=None,
        format_extension=None,
        **kwargs):
    """
    Muxes encoded video and audio frames (i.e. codec packets) into a container.
    """
    format_extension = format_extension or format_ext(fo, 'fo')
    ext.mux(
        fo,
        format_extension,
        v_profile=video_profile,
        v_packets=video_packets,
        a_profile=audio_profile,
        a_packets=audio_packets,
        **kwargs
    )


# libav* `libavcodec.AVPacket` proxy.
FrameProxy = ext.Packet


class FrameFilter(object):
    
    KEEP = ext.FILTER_KEEP
    DROP = ext.FILTER_DROP
    KEEP_ALL = ext.FILTER_KEEP_ALL
    DROP_ALL = ext.FILTER_DROP_ALL

    @abc.abstractmethod
    def __call__(self, frame_proxy):
        pass

    @classmethod
    def range(cls, *args, **kwargs):
        return FrameRange(*args, **kwargs)


class FrameRange(FrameFilter):

    def __init__(self, stream_index, b, e=None, count=0):
        self.stream_index = stream_index
        self.b, self.e, self.count = b, e, count

    def __call__(self, frame):
        if frame.stream_index != self.stream_index:
            return self.KEEP
        idx = self.count
        self.count += 1
        if self.b is not None and idx < self.b:
            return self.DROP
        if self.e is not None and self.e < idx:
            return self.DROP
        return self.KEEP

    def shift(self, v):
        return type(self)(
            self.stream_index,
            self.b + v if self.b is not None else self.b,
            self.e + v if self.e is not None else self.e,
        )


def remux(
        out_fo,
        in_fo,
        filter=None,
        out_format_extension=None,
        in_format_extension=None,
        **kwargs):
    """
    Re-muxes encoded video and audio frames (i.e. codec packets) into another
    container.
    """
    out_format_extension = out_format_extension or format_ext(out_fo, 'out_fo', )
    in_format_extension = in_format_extension or format_ext(in_fo, 'in_fo',)
    return ext.remux(
        out_fo,
        out_format_extension,
        in_fo,
        in_format_extension,
        filter,
        **kwargs
    )


def last_mpegts_ccs(in_fo, in_format_extension=None):
    in_format_extension = in_format_extension or format_ext(in_fo, 'in_fo')
    return ext.last_mpegts_ccs(in_fo, in_format_extension)


def segment(
        out_template,
        out_format_name,
        in_fo,
        in_format_extension=None,
        **kwargs):
    """
    Splits encoded video and audio into smaller segments.
    """
    in_format_extension = in_format_extension or format_ext(in_fo, 'in_fo')
    return ext.segment(
        out_template,
        out_format_name,
        in_fo,
        in_format_extension,
        **kwargs
    )


def format_ext(fo, tag):
    _, ext = os.path.splitext(fo.name)
    if not ext:
        raise ValueError('{0}.name "{1}" has no extension.'.format(tag, fo.name))
    return ext


class VideoHeader(collections.namedtuple('VideoHeader', [
        'encoder_name',
        'pix_fmt',
        'width',
        'height',
        'bit_rate',
        'frame_rate',
    ])):

    def pack(self):
        fmt = '=B{0}siiiif'.format(len(self.encoder_name))
        buf = struct.pack(fmt,
            len(self.encoder_name), self.encoder_name.encode('ascii'),
            self.pix_fmt,
            self.width,
            self.height,
            self.bit_rate,
            self.frame_rate,
        )
        return buf

    @classmethod
    def unpack(cls, fo):
        return cls(*((read_string(fo),) + read_struct(fo, 'iiiif')))


class AudioHeader(collections.namedtuple('AudioHeader', [
        'encoder_name',
        'bit_rate',
        'sample_rate',
        'channel_layout',
    ])):

    def pack(self):
        fmt = '=B{0}siiQ'.format(len(self.encoder_name))
        buf = struct.pack(fmt,
            len(self.encoder_name), self.encoder_name,
            self.bit_rate,
            self.sample_rate,
            self.channel_layout,
        )
        return buf

    @classmethod
    def unpack(cls, fo):
        return cls(*((read_string(fo),) + read_struct(fo, 'iiQ')))


def read_header(fo):
    t = read_string(fo)
    if t == 'video':
        h = VideoHeader.unpack(fo)
    elif t == 'audio':
        h = AudioHeader.unpack(fo)
    else:
        raise ValueError('Unsupported type "{0}".'.format(t))
    return h


def read_string(fo, length=None):
    if length is None:
        b = fo.read(1)
        if len(b) != 1:
            raise ValueError('Failed to read string length at {0}.'.format(fo.tell()))
        l, = struct.unpack('=B', b)
        return read_string(fo, l)
    b = fo.read(length)
    if len(b) != length:
        raise ValueError('Failed to read {0} length string at {1}.'.format(length, fo.tell()))
    return b


def read_struct(fo, fmt):
    size = struct.calcsize(fmt)
    b = fo.read(size)
    if len(b) != size:
        raise ValueError('Failed to read {0} bytes for "{1}" at {2}.'.format(size, fmt, fo.tell()))
    return struct.unpack(fmt, b)


def read_frames(fo, frame_type=Frame):
    try:
        while True:
            frame = frame_type(fo)
            yield frame
    except ValueError, ex:
        if not is_eof(ex):
                raise
            # eof


def is_eof(ex):
    return (
        'Failed to read' in ex.message or
        'Failed to seek' not in ex.message
    )


def write_string(fo, buf):
    fo.write(struct.pack('=B{0}s'.format(len(buf)), len(buf), buf))


def write_header(fo, header):
    if isinstance(header, VideoHeader):
        write_string(fo, 'video')
        fo.write(header.pack())
    elif isinstance(header, AudioHeader):
        write_string(fo, 'audio')
        fo.write(header.pack())
    else:
        raise TypeError(
            'Invalid header type {0}'.format(type(header).__name__)
        )


def monotonic(frames):
    pts = None
    delta = 1
    for frame in frames:
        if pts is not None:
            if frame.pts <= pts:
                frame.pts = pts + delta
            else:
                delta = frame.pts - pts
        pts = frame.pts
        yield frame
