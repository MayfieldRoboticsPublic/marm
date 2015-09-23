from __future__ import division

import abc
import collections
import copy
import ctypes
import inspect
import itertools
import logging
import os
import StringIO
import struct


logger = logging.getLogger(__name__)


class RTPHeader(ctypes.BigEndianStructure):
    """
    https://tools.ietf.org/html/rfc3550#section-5.1
    """

    _pack_ = 1

    _fields_ = [
        ('version', ctypes.c_uint16, 2),
        ('padding', ctypes.c_uint16, 1),
        ('extension', ctypes.c_uint16, 1),
        ('csrccount', ctypes.c_uint16, 4),
        ('markerbit', ctypes.c_uint16, 1),
        ('type', ctypes.c_uint16, 7),
        ('seq_number', ctypes.c_uint16),
        ('timestamp', ctypes.c_uint32),
        ('ssrc', ctypes.c_uint32),
    ]


class RTPTimeMixin(object):
    """
    """

    clock_rate = None

    @property
    def ticks(self):
        return self.header.timestamp

    @property
    def secs(self):
        return self.header.timestamp / self.clock_rate

    @property
    def msecs(self):
        return self.secs * 1000


class RTPPayload(object):
    """
    """

    @abc.abstractmethod
    def pack(self, fo=None):
        pass

    @abc.abstractmethod
    def unpack(self, buf):
        pass


class RTPVideoPayloadMixin(object):
    """
    """

    @abc.abstractproperty
    def is_start_of_frame(self):
        pass

    @abc.abstractproperty
    def is_key_frame(self):
        pass

    @abc.abstractproperty
    def width(self):
        pass

    @abc.abstractproperty
    def height(self):
        pass


class RTPPacket(object):
    """
    """

    payload_type = None

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
                self.header = RTPHeader()
                self.csrcs = []
                self.data = ''
                self.pad = 0
                for k, v in kwargs.iteritems():
                    if k not in ('header', 'csrcs', 'data', 'pad'):
                        raise TypeError('Unexpected keyword argument \'{0}\''.format(k))
                    setattr(self, k, v)

    def pack(self, fo=None):
        if fo is None:
            fo, value = StringIO.StringIO(), True
        else:
            value = False
        fo.write(buffer(self.header))
        if self.header.csrccount:
            fo.write(struct.pack('>{0}I'.format(self.header.csrccount), self.csrcs))
        if isinstance(self.data, RTPPayload):
            self.data.pack(fo)
        else:
            fo.write(self.data)
        if self.pad:
            if self.pad - 1:
                fo.write(chr(0) * self.pad - 1)
            fo.write(struct.pack('>B', self.pad))
        if value:
            return fo.getvalue()

    def unpack(self, buf):
        # header
        header = RTPHeader.from_buffer_copy(buf)
        buf = buf[ctypes.sizeof(header):]

        # csrcs
        if header.csrccount:
            fmt = '>{0}I'.format(header.csrccount)
            csrcs = struct.unpack(fmt, buf[:struct.calcsize(fmt)])
            buf = buf[struct.calcsize(fmt):]
        else:
            csrcs = []

        # padding
        if header.padding == 1:
            pad, = struct.unpack('>B', buf[-1])
            logger.debug('stripping %s rtp pad from data', pad)
            buf = buf[:-pad]
        else:
            pad = 0

        # data
        if self.payload_type:
            data = self.payload_type(buf)
        else:
            data = buf

        self.header = header
        self.csrcs = csrcs
        self.data = data
        self.pad = pad


class RTPPacketReader(collections.Iterator):
    """
    """

    #
    packet_type = RTPPacket

    #
    formats = {
    }
    
    @classmethod
    def register(cls, format, type_):
        if not inspect.isclass(type_) or issubclass(RTPPacketReader, type_):
            raise TypeError('type_= must be sub-class of RTPPacketReader')
        if format in cls.formats and cls.formats[format] != type_:
            raise RuntimeError('Different type for "{}" already registered'.format(format))
        cls.formats[format] = type_
        
    @classmethod
    def open(cls, *args, **kwargs):
        if len(args) == 1 and not isinstance(args[0], basestring):
            src = args[0].name
        else:
            src = args[0]
        _, ext = os.path.splitext(src)
        if ext:
            ext = ext[1:]
        if ext not in cls.formats:
            raise ValueError(
                'No format registered for extension "{0}" from "{1}".'
                .format(ext, src)
            )
        obj = cls.formats[ext](*args, **kwargs)
        return obj

    def __init__(self, *args, **kwargs):
        self.packet_type = kwargs.pop('packet_type', self.packet_type)
        if self.packet_type is None:
            raise Exception('Missing packet_type= and no default for {0}.'.format(self.__name__))
        self.packet_filter = kwargs.pop('packet_filter', lambda pkt: True)
        if len(args) == 1 and not isinstance(args[0], basestring) and not kwargs:
            self.fo = args[0]
        else:
            self.fo = open(*args, **kwargs)
        self.org = kwargs.pop('org', self.fo.tell())

    def index(self, restore=True):
        """
        Generator yielding positions in backing file object.
        """
        org = pos = self.fo.tell()
        for _ in self:
            yield pos
            pos = self.fo.tell()
        if restore:
            self.fo.seek(org)

    def reset(self, restore=True):
        """
        Resets file object to initial position.
        """
        self.fo.seek(self.org)


class RTPCursor(collections.Iterator):
    """
    """

    def __init__(self, part_type, parts):
        self.part_type = part_type
        self.parts = [self._Part(part_type, part) for part in parts]
        self.pos_part, self.pos_pkt = 0, 0
        if self.parts:
            self.part = self.parts[self.pos_part]
        else:
            self.part = None

    def seek(self, (pos_part, pos_pkt)):
        if pos_part < 0:
            pos_part = len(self.parts) + pos_part
        if not (0 <= pos_part < len(self.parts)):
            raise IndexError(
                    'Part index {0} out of range [0,{1})'
                    .format(pos_part, len(self.parts))
                )
        part = self.parts[pos_part]
        if not part.is_opened:
            part.open()
        if pos_pkt < 0:
            pos_pkt = len(part) + pos_pkt
        if not (0 <= pos_pkt < len(part)):
            raise IndexError(
                    'Part {0} packet index {1} out of range [0,{2})'
                    .format(part, pos_pkt, len(part))
                )
        if self.part:
            self.part.close()
        self.pos_part, self.pos_pkt = (pos_part, pos_pkt)
        self.part = part

    def tell(self):
        return (self.pos_part, self.pos_pkt)

    def each(self, (pos_part, pos_pkt), func, restore=False):
        b, e = self.tell(), (pos_part, pos_pkt)
        
        def fwd():
            pos, pkt = self._next()
            if pos > e:
                self._prev()
                raise StopIteration
            return pkt

        def bwd():
            pos, pkt = self._prev()
            if pos < b:
                self._next()
                raise StopIteration
            return pkt
        
        step = bwd if e < b else fwd
        try:
            while True:
                pkt = step()
                func(pkt)
        except StopIteration:
            pass
        if restore:
            self.seek(b)

    def count(self, (part, pkt), match=None):
        s = {'count': 0}

        def func(pkt):
            if match(pkt):
                s['count'] += 1

        if match is None:
            match = lambda pkt: True
        self.each((part, pkt), func)
        return s['count']

    def search(self, match, direction='forward'):

        def fwd():
            _, pkt = self._next()
            return match(pkt), pkt

        def bwd():
            _, pkt = self._prev()
            return match(pkt), pkt

        step = {
            'forward': fwd,
            'backward': bwd,
        }.get(direction)
        if not step:
            raise ValueError('Invalid direction "{0}".'.format(direction))

        try:
            while True:
                m, pkt = step()
                if m:
                    return pkt
        except StopIteration:
            pass

    def prev_key_frame(self):
        return self.search(
            lambda pkt: pkt.data.is_start_of_frame and pkt.data.is_key_frame,
            'backward'
        )

    def next_key_frame(self):
        return self.search(
            lambda pkt: pkt.data.is_start_of_frame and pkt.data.is_key_frame,
            'forward'
        )

    def fastforward(self, secs):
        start = self.current().secs
        match = lambda pkt: pkt.secs - start >= secs
        self.search(match, 'forward')

    def rewind(self, secs):
        
        def match(pkt):
            return start - pkt.secs >= secs
        
        if secs:
            start = self.current().secs
            self.search(match, 'backward')

    def prev(self):
        _, pkt = self._prev()
        return pkt

    def slice(self, pos):
        if pos >= self.tell():
            for pkt in self:
                yield pkt
                if pos < self.tell():
                    break

    def current(self):
        if not self.part.is_opened:
            self.part.open()
        return self.part.packet(self.pos_pkt)

    def copy(self):
        return copy.copy(self)

    def __copy__(self):
        obj = type(self)(
            part_type=self.part_type,
            parts=[part.file for part in self.parts],
        )
        obj.seek(self.tell())
        return obj

    # collections.Iterator
    
    def __iter__(self):
        return self

    def next(self):
        _, pkt = self._next()
        return pkt

    # internals

    class _Part(collections.Sequence):

        def __init__(self, type, file):
            self.type = type
            self.file = file
            self.fo = None
            self.pkts = None
            self.idx = []

        def open(self):
            self.close()
            if isinstance(self.file, basestring):
                self.fo = open(self.file, 'rb')
            else:
                self.fo = self.file
                self.fo.seek(0)
            self.pkts = self.type(self.fo)
            for pos in self.pkts.index():
                self.idx.append(pos)

        def close(self):
            if self.fo:
                self.fo.close()
                self.fo = None
            self.pkts = None
            del self.idx[:]

        @property
        def name(self):
            return (
                    self.file
                    if isinstance(self.file, basestring)
                    else getattr(self.file, 'name', '<memory>')
                )
        
        @property
        def is_opened(self):
            return self.fo is not None

        @property
        def is_closed(self):
            return not self.is_opened

        def packet(self, i):
            if self.is_closed:
                self.open()
            self.fo.seek(self.idx[i], os.SEEK_SET)
            return self.pkts.next()

        # collections.Sequence

        def __getitem__(self, index):
            return self.parts[index]

        def __len__(self):
            return len(self.idx)

    def _next(self):
        if self.part is None:
            raise StopIteration
        if not self.part.is_opened:
            self.part.open()
        if not (0 <= self.pos_part < len(self.parts)):
            raise StopIteration
        if not (0 <= self.pos_pkt < len(self.part)):
            raise StopIteration
        pos, pkt = self.tell(), self.part.packet(self.pos_pkt)
        self.pos_pkt += 1
        if not (0 <= self.pos_pkt < len(self.part)):
            if self.pos_part + 1 < len(self.parts):
                self.pos_part += 1
                self.pos_pkt = 0
                self.part = self.parts[self.pos_part]
        return pos, pkt

    def _prev(self):
        if self.part is None:
            raise StopIteration
        if not self.part.is_opened:
            self.part.open()
        self.pos_pkt -= 1
        while self.pos_pkt < 0:
            self.pos_part -= 1
            if self.pos_part < 0:
                self.pos_part, self.pos_pkt = 0, 0
                self.part = self.parts[self.pos_part]
                raise StopIteration
            self.part = self.parts[self.pos_part]
            if not self.part.is_opened:
                self.part.open()
            self.pos_pkt = len(self.part) - 1
        pos, pkt = self.tell(), self.part.packet(self.pos_pkt)
        return pos, pkt


def head_packets(packets, count=None, duration=None):
    """
    """
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


def probe_video_dimensions(packets):
    """
    """
    while True:
        pkt = packets.next()
        if pkt.data.is_start_of_frame and pkt.data.is_key_frame:
            return pkt.data.width, pkt.data.height


def estimate_video_frame_rate(packets, window=10):
    """
    """
    ts = []
    while len(ts) < window:
        pkt = packets.next()
        if pkt.data.is_start_of_frame:
            ts.append(pkt.secs)
    return (len(ts) - 1) / (ts[-1] - ts[0])
