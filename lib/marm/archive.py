"""
"""
from __future__ import division

import abc
import collections
import os
import struct

from . import rtp, frame

__all__ = [
    'MARM',
    'MJR',
    'PCAP',
]

class Archive(object):
    """
    """

    packet_type = None

    def __init__(self, *args, **kwargs):
        if 'packet_type' in kwargs:
            self.packet_type = kwargs.pop('packet_type')
        if self.packet_type is None:
            raise Exception('Missing packet_type= and no default for {0}.'.format(self.__name__))
        if len(args) == 1 and not isinstance(args[0], basestring) and not kwargs:
            self.fo = args[0]
        else:
            self.fo = open(*args, **kwargs)

    @abc.abstractmethod
    def packet(self, skip=False):
        """
        """
        pass

    @abc.abstractmethod
    def packets(self, index=False):
        """
        """
        pass


class MARM(Archive):
    """
    """

    packet_type = frame.Frame

    def header(self, skip=False):
        t = self._string()
        if t == 'video':
            h = self.VideoHeader(*((self._string(),) + self._struct('iiiii')))
        elif t == 'audio':
            h = self.AudioHeader(*((self._string(),) + self._struct('ii')))
        else:
            raise ValueError('Unsupported type "{0}".'.format(t))
        return self if skip else h

    VideoHeader = collections.namedtuple('VideoHeader', [
        'encoder_name',
        'pix_fmt',
        'width',
        'height',
        'bit_rate',
        'frame_rate',
    ])

    AudioHeader = collections.namedtuple('AudioHeader', [
        'encoder_name',
        'bit_rate',
        'sample_rate',
    ])
    
    def _string(self, length=None):
        if length is None:
            b = self.fo.read(1)
            if len(b) != 1:
                raise ValueError('Failed to read string length at {0}.'.format(self.fo.tell()))
            l, = struct.unpack('=B', b)
            return self._string(l)
        b = self.fo.read(length)
        if len(b) != length:
            raise ValueError('Failed to read {0} length string at {1}.'.format(length, self.fo.tell()))
        return b

    def _struct(self, fmt):
        size = struct.calcsize(fmt)
        b = self.fo.read(size)
        if len(b) != size:
            raise ValueError('Failed to read {0} bytes for "{1}" at {2}.'.format(size, fmt, self.fo.tell()))
        return struct.unpack(fmt, b)

    # Archive

    def packet(self, skip=False):
        if skip:
            self.packet_type.skip(self.fo)
            return
        return self.packet_type.load(self.fo)

    def packets(self, index=False):
        try:
            if index:
                while True:
                    pos = self.fo.tell()
                    self.packet(skip=True)
                    yield pos
            else:
                while True:
                    yield self.packet()
        except ValueError, ex:
            if ('Failed to read' not in ex.message and
                'Failed to seek' not in ex.message):
                raise
            # eof


class MARMWriter(object):

    def __init__(self, *args, **kwargs):
        if len(args) == 1 and not isinstance(args[0], basestring) and not kwargs:
            self.fo = args[0]
        else:
            self.fo = open(*args, **kwargs)

    def video(self,
                encoder_name,
                pix_fmt,
                width,
                height,
                bit_rate,
                frame_rate,
            ):
        fmt = '=B{0}sB{1}siiiii'.format(len('video'), len(encoder_name)),
        self.fo.write(struct.pack(fmt,
                len('video'), b'video',
                len(encoder_name), encoder_name.encode('ascii'),
                pix_fmt,
                width,
                height,
                bit_rate,
                frame_rate,
            ))

    def audio(self,
                encoder_name,
                bit_rate,
                sample_rate,
            ):
        fmt = '=B{0}sB{1}sii'.format(len('audio'), len(encoder_name))
        self.fo.write(struct.pack(fmt,
            len('audio'), 'audio',
            len(encoder_name), encoder_name,
            bit_rate,
            sample_rate
        ))

    def packet(self, frame):
        frame.dump(self.fo)


class MJR(Archive):
    """
    """

    packet_type = rtp.RTPPacket

    def header(self, skip=False):
        self._marker()
        t = self._string()
        if t not in ('audio', 'video'):
            raise ValueError('Unsupported type "{0}".'.format(t))
        return self if skip else t

    def _marker(self):
        b = self._string(len('MEETECHO'))
        if b != 'MEETECHO':
            raise ValueError('Invalid marker "{0}" != "{1}"'.format(b, 'MEETCHO'))

    def _string(self, length=None):
        if length is None:
            b = self.fo.read(2)
            if len(b) != 2:
                raise ValueError('Failed to read string length at {0}.'.format(self.fo.tell()))
            l, = struct.unpack('>H', b)
            return self._string(l)
        b = self.fo.read(length)
        if len(b) != length:
            raise ValueError('Failed to read {0} length string at {1}.'.format(length, self.fo.tell()))
        return b

    # Archive

    def packet(self, skip=False):
        self._marker()
        b = self.fo.read(2)
        if len(b) != 2:
            raise ValueError('Failed to read string length at {0}.'.format(self.fo.tell()))
        length, = struct.unpack('>H', b)
        if skip:
            pos = self.fo.tell()
            self.fo.seek(length, os.SEEK_CUR)
            if self.fo.tell() - pos != length:
                raise ValueError('Failed to seek past {0} length string at {1}.'.format(length, self.fo.tell()))
            return
        b = self.fo.read(length)
        if len(b) != length:
            raise ValueError('Failed to read {0} length string at {1}.'.format(length, self.fo.tell()))
        pkt = self.packet_type.from_buffer(b)
        return pkt

    def packets(self, index=False):
        try:
            if index:
                while True:
                    pos = self.fo.tell()
                    self.packet(skip=True)
                    yield pos
            else:
                while True:
                    yield self.packet()
        except ValueError, ex:
            if ('Failed to read' not in ex.message and
                'Failed to seek' not in ex.message):
                raise
            # eof


class MJRWriter(object):

    def __init__(self, *args, **kwargs):
        if len(args) == 1 and not isinstance(args[0], basestring) and not kwargs:
            self.fo = args[0]
        else:
            self.fo = open(*args, **kwargs)

    def header(self, type_):
        self._marker()
        self._string(type_)

    def audio(self):
        self._header('audio')

    def video(self):
        self._header('video')

    def packet(self, packet):
        self._marker()
        b = packet.dumps()
        self._string(b)

    def _marker(self):
        self.fo.write('MEETECHO')

    def _string(self, b):
        self.fo.write(struct.pack('>H', len(b)))
        self.fo.write(b)
