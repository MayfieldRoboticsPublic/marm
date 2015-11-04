from __future__ import division

import abc
import collections
import contextlib
import copy
import ctypes
import datetime
import inspect
import itertools
import logging
import math
import os
import StringIO
import struct

from . import ext


logger = logging.getLogger(__name__)


class RTPHeader(ctypes.BigEndianStructure):
    """
    See https://tools.ietf.org/html/rfc3550#section-5.1
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
    `RTPPacket` mixin used to compute timing information. 
    """

    # In Hz (e.g. 48000).
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
    RTP payload interface. It is implemented and associated w/ an `RTPPacket`
    type via `RTPPacket.payload_type`.
    """

    @abc.abstractmethod
    def pack(self, fo=None):
        pass

    @abc.abstractmethod
    def unpack(self, buf):
        pass


class RTPAudioPayloadMixin(object):
    """
    `RTPPayload` mixin used to query audio information.
    """

    @abc.abstractproperty
    def nb_samples(self):
        pass

    @abc.abstractproperty
    def nb_channels(self):
        pass


class RTPVideoPayloadMixin(object):
    """
    `RTPPayload` mixin used to query video information.
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
    Represents an RTP packet. You typically inherit from this an provide a:

    - `type` and
    - `payload_type`

    based on the type of media, e.g. for VP8 video:

    .. code:: python

        class VP8RTPPacket(rtp.RTPTimeMixin, rtp.RTPPacket):

            # rtp.RTPPacket
        
            type = rtp.RTPPacket.VIDEO_TYPE
        
            payload_type = VP8RTPPayload
        
            # RTPTimeMixin
        
            clock_rate = 90000

    """
    
    AUDIO_TYPE = 'audio'
    VIDEO_TYPE = 'video'

    type = None

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


class RTPPacketReader(collections.Iterable):
    """
    Interface for:
    
    - indexing and
    - reading
    
    archived/stored `RTPPacket`s.
    """

    # Default `RTPPacket` type.
    packet_type = RTPPacket

    # Registry for mapping extensions to `RTPPacketReader` implementations.
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
        self.packet_filter = kwargs.pop('packet_filter', None) or (lambda pkt: True)
        if len(args) == 1 and not isinstance(args[0], basestring) and not kwargs:
            self.fo = args[0]
        else:
            self.fo = open(*args, **kwargs)
        self.org = kwargs.pop('org', self.fo.tell())

    def index(self, restore=True):
        """
        Generator yielding positions in file object.
        """
        org = pos = self.fo.tell()
        for _ in self:
            yield pos
            pos = self.fo.tell()
        if restore:
            self.fo.seek(org)

    def reset(self):
        """
        Resets file object to initial packet position.
        """
        self.fo.seek(self.org)

    @contextlib.contextmanager
    def restoring(self):
        pos = self.fo.tell()
        try:
            yield
        finally:
            self.fo.seek(pos)


class RTPCursor(collections.Iterable):
    """
    Cursor used to iterate over a collection or stored `RTPPacket`s.
    """

    def __init__(self, parts, part_type, **part_kwargs):
        self.part_type = part_type
        self.packet_type = part_kwargs.get('packet_type', RTPPacket)
        self.parts = [
            self._Part(part, part_type, part_kwargs) for part in parts
        ]
        self.pos_part, self.pos_pkt = 0, 0
        if self.parts:
            self.part = self.parts[self.pos_part]
        else:
            self.part = None
        self.c = collections.defaultdict(dict)

    def cache(self, tag, key, value=None):
        if value is not None:
            self.c[tag][key] = value
            return value
        return self.c[tag].get(key)

    def spans(self, (b_part, b_pkt), (e_part, e_pkt)):
        for part in range(b_part, e_part + 1):
            b_pkt = b_pkt if part == b_part else 0
            e_pkt = e_pkt if part == e_part else -1
            yield part, b_pkt, e_pkt

    def seek(self, (pos_part, pos_pkt)):
        if self.tell() == (pos_part, pos_pkt):
            return
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

    def each(self, stop, func):
        for pkt in self.slice(stop):
            func(pkt)

    def count(self, stop, match=None):
        s = {'count': 0}

        def func(pkt):
            if match(pkt):
                s['count'] += 1

        if match is None:
            match = lambda pkt: True
        self.each(stop, func)
        return s['count']

    def compute(self, m, r, stop, zero=0, cache=None):
        value = zero
        org = self.tell()
        for part, b_pos, e_pos in self.spans(org, stop):
            if cache:
                if b_pos == 0 and e_pos == -1:
                    v = self.cache(cache, (part, b_pos, e_pos))
                    if v is not None:
                        value = reduce(r, [v], value)
                        continue
            self.seek((part, b_pos))
            v = reduce(
                r,
                (m(pkt) for pkt in self.slice((part, e_pos), inclusive=e_pos == -1)),
                zero,
            )
            if cache and b_pos == 0 and e_pos == -1:
                self.cache(cache, (part, b_pos, e_pos), v)
            value = reduce(r, [v], value)
        return value

    def search(self, match, dir='forward'):

        def fwd():
            _, pkt = self._next()
            return match(pkt), pkt

        def bwd():
            _, pkt = self._prev()
            return match(pkt), pkt

        step = {
            'forward': fwd,
            'backward': bwd,
        }.get(dir)
        if not step:
            raise ValueError('Invalid direction "{0}".'.format(dir))

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

    def prev_start_of_frame(self):
        return self.search(
            lambda pkt: (
                pkt.data.is_start_of_frame and pkt.data.is_start_of_frame
            ),
            'backward'
        )

    def next_start_of_frame(self):
        return self.search(
            lambda pkt: (
                pkt.data.is_start_of_frame and pkt.data.is_start_of_frame
            ),
            'forward'
        )

    def interval(self, pos=None):
        # FIXME: sum inter-packet delta w/ reset detection?
        if not pos:
            pos = (-1, -1)
        start = self.current().secs
        self.seek(pos)
        delta = self.current().secs - start
        return delta

    def fastforward(self, secs):
        # FIXME: sum inter-packet delta w/ reset detection?
        if not secs:
            return 0
        if secs < 0:
            return self.rewind(-secs)
        start = self.current().secs
        match = lambda pkt: pkt.secs - start >= secs
        self.search(match, 'forward')
        return (self.current().secs - start) - secs

    def rewind(self, secs):
        # FIXME: sum inter-packet delta w/ reset detection?
        if not secs:
            return 0
        if secs < 0:
            return self.fastforward(-secs)
        start = self.current().secs
        match = lambda pkt: start - pkt.secs >= secs
        self.search(match, 'backward')
        return (start - self.current().secs) - secs

    def time_cut(self, begin_secs, end_secs):
        """
        """
        org = self.tell()
        
        # head
        begin_dt = self.fastforward(begin_secs)
        base = self.tell()
        if self.packet_type.payload_type and issubclass(self.packet_type.payload_type, RTPVideoPayloadMixin):
            self.prev_start_of_frame()
        start = self.tell()
        self.seek(base)
        start_secs = begin_secs + begin_dt + self.interval(start)

        # tail
        self.seek(org)
        if end_secs is None:
            end_secs, end_dt = self.interval((-1, -1)), 0
        else:
            end_dt = self.fastforward(end_secs)
        base = self.tell()
        if self.packet_type.payload_type and issubclass(self.packet_type.payload_type, RTPVideoPayloadMixin):
            self.prev_start_of_frame()
        stop = self.tell()
        self.seek(base)
        stop_secs = end_secs + end_dt + self.interval(stop)
        
        return start, start_secs, stop, stop_secs

    def time_positions(self, *args):
        """
        """
        pos = []
        org = self.tell()
        for secs in args:
            self.seek(org)
            self.fastforward(secs)
            pos.append(self.tell())
        return pos
    
    def trim_frames(self, stop, samples, scale=7, org=(0, 0)):
        start = self.tell()
        size = self.current().data.nb_channels * samples
        target = int(math.ceil(scale / 2))

        b, b_samples, b_off, b_scale = self.align_frame(
            samples, scale=scale, org=org,
        )
        b_idx = 0 if b == start else max(b_scale - target, 0)

        self.seek(stop)
        _, e_samples, e_off, _ = self.align_frame(
            samples, scale=target, org=org,
        )

        total = (e_samples + e_off) - (b_samples + b_off)
        e_idx = int(total / size) - 1

        logger.info(
            'trim %s, %s -> %s, %s w/ offset @ %s, range %s',
            start, stop, b, stop, b_off, (b_idx, e_idx),
        )
        return b, stop, b_off, (b_idx, e_idx)

    def align_frame(self, samples, scale=1, dir='backward', org=(0, 0)):
        """
        
        :param samples:
        :param scale: 
        :param dir:
        :param trim:
        :param org:
        
        :return:
        """

        def _align(pkt):
            s['count'] += pkt.data.nb_samples * pkt.data.nb_channels
            return s['count'] >= size

        def _scale(pkt):
            s['count'] += pkt.data.nb_samples * pkt.data.nb_channels
            return s['count'] >= scale * size

        start = self.tell()
        pkt = self.current()
        size = pkt.data.nb_channels * samples

        # seek to alignment
        s = {'count': 0}
        pkt = self.search(_align, dir=dir)
        if pkt is None:
            pos, samples, off = start, 0, 0
        else:
            # calculate samples up to alignment
            pos = self.tell()
            self.seek(org)
            samples = self.compute(
                lambda pkt: pkt.data.nb_samples * pkt.data.nb_channels,
                lambda x, y: x + y,
                pos,
                cache='samples',
            )
            off = 0 if samples % size == 0 else (size - (samples % size))

            # scale
            s = {'count': off}
            self.search(_scale, dir=dir)
            scaled_samples = samples - (s['count'] - off)
            scaled_off = 0 if scaled_samples % size == 0 else size - (scaled_samples % size)
            scaled_pos = self.tell()
            scale = int(((samples + off) - (scaled_samples + scaled_off)) / size)
            pos, samples, off = scaled_pos, scaled_samples, scaled_off

        logger.info(
            'aligned %s -> %s @ %s samples w/ trim %s',
            start, pos, samples, off
        )
        return pos, samples, off, scale

    def prev(self):
        _, pkt = self._prev()
        return pkt

    def slice(self, stop, inclusive=False):
        if stop < self.tell():
            yield self.current()
            try:
                while True:
                    pos, pkt = self._prev()
                    if pos <= stop:
                        if inclusive:
                            yield pkt
                        break
                    yield pkt
            except StopIteration:
                pass
        elif stop > self.tell():
            yield self.current()
            try:
                while True:
                    pos, pkt = self._next()
                    if pos >= stop:
                        if inclusive:
                            yield pkt
                        break
                    yield pkt
            except StopIteration:
                pass

    def time_slice(self, begin_secs, end_secs):
        org = self.tell()
        
        # start
        self.fastforward(begin_secs)
        begin = self.tell()
        if self.packet_type.payload_type and issubclass(self.packet_type.payload_type, RTPVideoPayloadMixin):
            self.next_key_frame()
        start = self.tell()
        self.seek(begin)
        start_secs = begin_secs + self.interval(start)
        
        # stop
        if end_secs is None:
            self.seek(org)
            end_secs = self.interval((-1, -1))
        self.seek(org)
        self.fastforward(end_secs)
        end = self.tell()
        if self.packet_type.payload_type and issubclass(self.packet_type.payload_type, RTPVideoPayloadMixin):
            self.prev_start_of_frame()
        stop = self.tell()
        stop_secs = end_secs + self.interval(end)
        
        # iterator
        
        class Slice(collections.Iterator):
            
            def __init__(self, cur, start, stop):
                self.cur, self.start, self.stop = cur, start, stop
                self.i = None

            # collections.Iterator

            def __iter__(self):
                self.cur.seek(self.start)
                self.i = self.cur.slice(self.stop)
                return self

            def next(self):
                return self.i.next()
        
        return start_secs, stop_secs, Slice(self, start, stop)

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

    @contextlib.contextmanager
    def restoring(self):
        pos = self.tell()
        try:
            yield
        finally:
            self.seek(pos)

    # collections.Iterable

    def __iter__(self):
        if self.part is None:
            return
        try:
            yield self.current()
        except IndexError:
            raise StopIteration()
        while True:
            _, pkt = self._next()
            yield pkt

    # internals

    class _Part(collections.Sequence):

        def __init__(self, file, part_type, part_kwargs):
            self.file = file
            self.part_type = part_type
            self.part_kwargs = part_kwargs
            self.pkts = None
            self.i = None
            self.idx = []

        def open(self):
            self.close()
            self.pkts = self.part_type(self.file, **self.part_kwargs)
            for pos in self.pkts.index():
                self.idx.append(pos)
            self.i = iter(self.pkts)

        def close(self):
            self.pkts = None
            self.i = None
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
            return self.pkts is not None

        @property
        def is_closed(self):
            return not self.is_opened

        def packet(self, i):
            if self.is_closed:
                self.open()
            self.pkts.fo.seek(self.idx[i], os.SEEK_SET)
            return self.i.next()

        # collections.Sequence

        def __getitem__(self, index):
            return self.parts[index]

        def __len__(self):
            return len(self.idx)

    def _next(self):
        # next
        (pos_part, pos_pkt) = (self.pos_part, self.pos_pkt)
        try:
            self.pos_pkt += 1
            if not (0 <= self.pos_pkt < len(self.part)):
                if self.pos_part + 1 < len(self.parts):
                    self.pos_part += 1
                    self.pos_pkt = 0
                    self.part = self.parts[self.pos_part]
            if self.part is None:
                raise StopIteration
            if not self.part.is_opened:
                self.part.open()
            if not (0 <= self.pos_part < len(self.parts)):
                raise StopIteration
            if not (0 <= self.pos_pkt < len(self.part)):
                raise StopIteration
        except StopIteration:
            (self.pos_part, self.pos_pkt) = (pos_part, pos_pkt)
            raise

        # read
        pos, pkt = self.tell(), self.part.packet(self.pos_pkt)
        return pos, pkt

    def _prev(self):
        # prev
        (pos_part, pos_pkt) = (self.pos_part, self.pos_pkt)
        try:
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
            if self.part is None:
                raise StopIteration
            if not self.part.is_opened:
                self.part.open()
        except StopIteration:
            (self.pos_part, self.pos_pkt) = (pos_part, pos_pkt)
            raise

        # read
        pos, pkt = self.tell(), self.part.packet(self.pos_pkt)
        return pos, pkt


def head_packets(packets, count=None, duration=None):
    """
    Iterator for first n packets where n is capped by a:
    
    - packet count and/or
    - duration in seconds
    
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
    Finds first start-of-frame packet and extracts video width and height from
    it.
    """
    for pkt in packets:
        if pkt.data.is_start_of_frame and pkt.data.is_key_frame:
            return pkt.data.width, pkt.data.height


def estimate_video_frame_rate(packets, window=10):
    """
    Finds `window` start-of-frame packets and uses their timestamps to estimate
    video frame rate. 
    """
    ts = []
    i = iter(packets)
    while len(ts) < window:
        pkt = i.next()
        if pkt.data.is_start_of_frame:
            ts.append(pkt.secs)
    return (len(ts) - 1) / (ts[-1] - ts[0])


def probe_audio_channel_layout(packets):
    """
    Determines audio channel layout from first packet.
    """
    pkt = iter(packets).next()
    nb_channels = pkt.data.nb_channels
    if nb_channels == 1:
        return ext.AV_CH_LAYOUT_MONO
    elif nb_channels == 2:
        return ext.AV_CH_LAYOUT_STEREO
    raise ValueError('Unsupported number of channel {0}.'.format(nb_channels))


def split_packets(packets, duration=None, count=None):
    """
    Splits packets into n-sized packet chunks where n is capped by a:
    
    - packet count and/or
    - duration in seconds or `datetime.timedelta`
    
    """
    packets = iter(packets)

    # slice

    s = {
        'epoch': None,
        'count': 0,
        'last': None
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
        if isinstance(duration, datetime.timedelta):
            duration = duration.total_seconds()
        ps.append(_duration)
    if count is not None:
        ps.append(_count)
    _predicate = lambda pkt: all(p(pkt) for p in ps)

    def _slice():
        if s['last']:
            pkt, s['last'] = s['last'], None
        else:
            pkt = packets.next()
        if not _predicate(pkt):
            s['last'] = pkt
            return
        yield pkt
        while True:
            pkt = packets.next()
            if not _predicate(pkt):
                s['last'] = pkt
                break
            yield pkt

    # slices

    while True:
        # reset state
        s['epoch'] = None
        s['count'] = 0

        # slice
        pkts = _slice()
        try:
            pkt = pkts.next()
        except StopIteration:
            # nothing so we're done
            break
        yield itertools.chain([pkt], pkts)
