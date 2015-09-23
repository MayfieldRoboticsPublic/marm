"""
"""
import os
import struct

from . import rtp


class MJRRTPPacketReader(rtp.RTPPacketReader):

    def __init__(self, *args, **kwargs):
        super(MJRRTPPacketReader, self).__init__(*args, **kwargs)
        read_header(self.fo)
        self.org = self.fo.tell()
        self.i = read_packets(self.fo)

    # rtp.RTPPacketReader
    
    def index(self, restore=True):
        org = pos = self.fo.tell()
        try:
            while True:
                skip_packet(self.fo)
                yield pos
                pos = self.fo.tell()
        except ValueError, ex:
            if not is_eof(ex):
                raise
        if restore:
            self.fo.seek(org)

    def __iter__(self):
        self.fo.seek(self.org)
        return self

    def next(self):
        while True:
            buf = self.i.next()
            pkt = self.packet_type(buf)
            if self.packet_filter(pkt):
                break
        return pkt


rtp.RTPPacketReader.register('mjr', MJRRTPPacketReader)


def read_header(fo):
    read_marker(fo)
    type_ = read_string(fo)
    if type_ not in ('audio', 'video'):
        raise ValueError('Unsupported type "{0}".'.format(type_))
    return type_


def read_string(fo, length=None):
    if length is None:
        b = fo.read(2)
        if len(b) != 2:
            raise ValueError('Failed to read string length at {0}.'.format(fo.tell()))
        l, = struct.unpack('>H', b)
        return read_string(fo, l)
    b = fo.read(length)
    if len(b) != length:
        raise ValueError('Failed to read {0} length string at {1}.'.format(length, fo.tell()))
    return b


def read_marker(fo):
    b = read_string(fo, len('MEETECHO'))
    if b != 'MEETECHO':
        raise ValueError('Invalid marker "{0}" != "{1}"'.format(b, 'MEETCHO'))
    return b


def read_packet(fo):
    read_marker(fo)
    b = fo.read(2)
    if len(b) != 2:
        raise ValueError('Failed to read string length at {0}.'.format(fo.tell()))
    length, = struct.unpack('>H', b)
    buf = fo.read(length)
    if len(buf) != length:
        raise ValueError('Failed to read {0} length string at {1}.'.format(length, fo.tell()))
    return buf


def read_packets(fo):
    try:
        while True:
            yield read_packet(fo)
    except ValueError, ex:
        if not is_eof(ex):
            raise
        # eof


def skip_packet(fo):
    read_marker(fo)
    b = fo.read(2)
    if len(b) != 2:
        raise ValueError('Failed to read string length at {0}.'.format(fo.tell()))
    length, = struct.unpack('>H', b)
    pos = fo.tell()
    fo.seek(length, os.SEEK_CUR)
    if fo.tell() - pos != length:
        raise ValueError('Failed to seek past {0} length string at {1}.'.format(length, fo.tell()))
    return


def is_eof(ex):
    return (
        'Failed to read' in ex.message or
        'Failed to seek' not in ex.message
    )


def write_marker(fo):
    fo.write('MEETECHO')


def write_string(fo, buf):
    fo.write(struct.pack('>H', len(buf)))
    fo.write(buf)


def write_header(fo, type_):
    write_marker(fo)
    write_string(fo, type_)


def write_packet(fo, pkt):
    write_marker(fo)
    buf = pkt.pack()
    write_string(fo, buf)