from __future__ import division

import ctypes
import StringIO

from . import rtp


class VP8RTPPayload(rtp.RTPVideoPayloadMixin, rtp.RTPPayload):

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
                self.desc = VP8RTPPayloadDescriptor()
                self.desc_x = VP8RTPPayloadDescriptorX()
                self.desc_i = VP8RTPPayloadDescriptorI()
                self.desc_l = VP8RTPPayloadDescriptorL()
                self.desc_tk = VP8RTPPayloadDescriptorTK()
                self.data = ''
                for k, v in kwargs.iteritems():
                    if k not in ('desc', 'desc_x', 'desc_i', 'desc_l', 'desc_tk', 'data',):
                        raise TypeError('Unexpected keyword argument \'{0}\''.format(k))
                    setattr(self, k, v)

    @property
    def header(self):
        # NOTE: part of frame data so we don't unpack
        if not self.is_start_of_frame:
            raise ValueError('Not start of frame.')
        b = self.data[:ctypes.sizeof(VP8Header)]
        return VP8Header.from_buffer_copy(b)

    @property
    def key_header(self):
        # NOTE: part of frame data so we don't unpack
        if not self.is_start_of_frame:
            raise ValueError('Not start of frame.')
        if not self.header.is_key_frame:
            raise ValueError('Not key frame.')
        b = self.data[ctypes.sizeof(VP8Header):ctypes.sizeof(VP8Header) + ctypes.sizeof(VP8KeyFrameHeader)]
        return VP8KeyFrameHeader.from_buffer_copy(b)

    # rtp.RTPPayload

    def pack(self, fo=None):
        if fo is None:
            fo, value = StringIO.StringIO(), True
        else:
            value = False
        fo.write(buffer(self.desc))
        if self.desc.x:
            fo.write(buffer(self.desc_x))
        if self.desc_x and self.desc_x.i:
            fo.write(buffer(self.desc_i))
        if self.desc_x and self.desc_x.l:
            fo.write(buffer(self.desc_l))
        if self.desc_x and (self.desc_x.t or self.desc_x.k):
            fo.write(buffer(self.desc_tk))
        fo.write(self.data)
        if value:
            return fo.getvalue()

    def unpack(self, buf):
        # descriptor
        desc = VP8RTPPayloadDescriptor.from_buffer_copy(buf)
        buf = buf[ctypes.sizeof(desc):]

        # descriptor x
        if desc.x:
            desc_x = VP8RTPPayloadDescriptorX.from_buffer_copy(buf)
            buf = buf[ctypes.sizeof(desc_x):]
        else:
            desc_x = None

        # descriptor i
        if desc_x and desc_x.i:
            desc_i = VP8RTPPayloadDescriptorI.from_buffer_copy(buf)
            buf = buf[desc_i.size:]
        else:
            desc_i = None

        # descriptor l
        if desc_x and desc_x.l:
            desc_l = VP8RTPPayloadDescriptorL.from_buffer_copy(buf)
            buf = buf[ctypes.sizeof(desc_l):]
        else:
            desc_l = None

        # descriptor tk
        if desc_x and (desc_x.t or desc_x.k):
            desc_tk = VP8RTPPayloadDescriptorTK.from_buffer_copy(buf)
            buf = buf[ctypes.sizeof(desc_tk):]
        else:
            desc_tk = None

        # data
        data = buf

        self.desc = desc
        self.desc_x = desc_x
        self.desc_i = desc_i
        self.desc_l = desc_l
        self.desc_tk = desc_tk
        self.data = data

    # RTPVideoMixin

    @property
    def is_start_of_frame(self):
        return self.desc.s == 1 and self.desc.pid == 0

    @property
    def is_key_frame(self):
        return self.header.is_key_frame if self.is_start_of_frame else False

    @property
    def width(self):
        return self.key_header.width

    @property
    def height(self):
        return self.key_header.height


class VP8RTPPayloadDescriptor(ctypes.BigEndianStructure):
    """
    https://tools.ietf.org/html/draft-ietf-payload-vp8-16#section-4.2
    """

    _fields_ = [
        ('x', ctypes.c_uint8, 1),
        ('r', ctypes.c_uint8, 1),
        ('n', ctypes.c_uint8, 1),
        ('s', ctypes.c_uint8, 1),
        ('pid', ctypes.c_uint8, 4),
    ]


class VP8RTPPayloadDescriptorX(ctypes.BigEndianStructure):
    """
    https://tools.ietf.org/html/draft-ietf-payload-vp8-16#section-4.2
    """

    _fields_ = [
        ('i', ctypes.c_uint8, 1),
        ('l', ctypes.c_uint8, 1),
        ('t', ctypes.c_uint8, 1),
        ('k', ctypes.c_uint8, 1),
        ('rsv', ctypes.c_uint8, 4),
    ]


class VP8RTPPayloadDescriptorI(ctypes.BigEndianStructure):
    """
    https://tools.ietf.org/html/draft-ietf-payload-vp8-16#section-4.2
    """

    _fields_ = [
        ('m', ctypes.c_uint8, 1),
        ('pictureid0', ctypes.c_uint8, 7),
        ('pictureid1', ctypes.c_uint8, 8),
    ]

    @property
    def size(self):
        return ctypes.sizeof(self) - (0 if self.m else 1)


class VP8RTPPayloadDescriptorL(ctypes.BigEndianStructure):
    """
    https://tools.ietf.org/html/draft-ietf-payload-vp8-16#section-4.2
    """

    _fields_ = [
        ('tl0picidx', ctypes.c_uint8, 8),
    ]


class VP8RTPPayloadDescriptorTK(ctypes.BigEndianStructure):
    """
    https://tools.ietf.org/html/draft-ietf-payload-vp8-16#section-4.2
    """

    _fields_ = [
        ('tid', ctypes.c_uint8, 3),
        ('y', ctypes.c_uint8, 1),
        ('keyidx', ctypes.c_uint8, 4),
    ]


class VP8Header(ctypes.LittleEndianStructure):
    """
    https://tools.ietf.org/html/rfc6386#section-9.1
    """

    _fields_ = [
        ('p', ctypes.c_uint8, 1),
        ('ver', ctypes.c_uint8, 3),
        ('show', ctypes.c_uint8, 1),
        ('size0', ctypes.c_uint8, 3),
        ('size1', ctypes.c_uint8),
        ('size2', ctypes.c_uint8),
    ]

    @property
    def is_key_frame(self):
        return self.p == 0

    @property
    def size(self):
        return self.size0 + (self.size1 << 3) + (self.size2 << 11)


class VP8KeyFrameHeader(ctypes.LittleEndianStructure):
    """
    https://tools.ietf.org/html/rfc6386#section-9.1
    """

    _pack_ = 1

    _fields_ = [
        ('start_code0', ctypes.c_uint8),
        ('start_code1', ctypes.c_uint8),
        ('start_code2', ctypes.c_uint8),
        ('horz', ctypes.c_uint16),
        ('vert', ctypes.c_uint16),
    ]

    sync_code = (0x9d, 0x01, 0x2a)

    @property
    def is_synced(self):
        return (
            self.start_code0 == self.sync_code[0] and
            self.start_code1 == self.sync_code[1] and
            self.start_code2 == self.sync_code[2]
        )

    @property
    def width(self):
        return self.horz & 0x3fff

    @property
    def width_scaling(self):
        return self.horz >> 14

    @property
    def height(self):
        return self.vert & 0x3fff

    @property
    def height_scaling(self):
        return self.vert >> 14


class VP8RTPPacket(rtp.RTPTimeMixin, rtp.RTPPacket):
    """
    https://tools.ietf.org/html/draft-ietf-payload-vp8-16
    """

    # RTPPacket

    type = rtp.RTPPacket.VIDEO_TYPE

    payload_type = VP8RTPPayload

    # RTPTimeMixin

    clock_rate = 90000
