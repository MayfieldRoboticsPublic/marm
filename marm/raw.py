"""
Helpers for reading/writing encoded packets media packets (i.e. frames). To
e.g. to count the number of video frames in a raw file:

.. code:: python

    with path.open('rb') as fo:
        header = marm.raw.read_header(fo)
        frames = marm.raw.read_frames(fo, frame_type=marm.VideoFrame)
        count = sum(1 for frame in frames)

"""
import collections
import struct

from . import Frame


class VideoHeader(collections.namedtuple('VideoHeader', [
        'encoder_name',
        'pix_fmt',
        'width',
        'height',
        'bit_rate',
        'frame_rate',
    ])):

    def pack(self):
        fmt = '=B{0}sB{1}siiiii'.format(len('video'), len(self.encoder_name))
        buf = struct.pack(fmt,
            len('video'), b'video',
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
        return cls(*((read_string(fo),) + read_struct(fo, 'iiiii')))


class AudioHeader(collections.namedtuple('AudioHeader', [
        'encoder_name',
        'bit_rate',
        'sample_rate',
    ])):
    
    def pack(self):
        fmt = '=B{0}sB{1}sii'.format(len('audio'), len(self.encoder_name))
        buf = struct.pack(fmt,
            len('audio'), 'audio',
            len(self.encoder_name), self.encoder_name,
            self.bit_rate,
            self.sample_rate,
        )
        return buf
    
    @classmethod
    def unpack(cls, fo):
        return cls(*((read_string(fo),) + read_struct(fo, 'ii')))


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
