"""
"""
from __future__ import division

import ctypes

from . import rtp


class VP8RTPPacket(rtp.RTPTimeMixin, rtp.RTPVideoMixin, rtp.RTPPacket):

    def __init__(self,
                header,
                csrcs,
                vp8_descriptor,
                vp8_descriptor_x,
                vp8_descriptor_i,
                vp8_descriptor_l,
                vp8_descriptor_tk,
                payload,
                pad,
            ):
        super(VP8RTPPacket, self).__init__(header, csrcs, payload, pad)
        self.vp8_descriptor = vp8_descriptor
        self.vp8_descriptor_x = vp8_descriptor_x
        self.vp8_descriptor_i = vp8_descriptor_i
        self.vp8_descriptor_l = vp8_descriptor_l
        self.vp8_descriptor_tk = vp8_descriptor_tk

    @property
    def vp8_header(self):
        if not self.is_start_of_frame:
            raise ValueError('Not start of frame.')
        b = self.payload[:ctypes.sizeof(VP8Header)]
        return VP8Header.from_buffer_copy(b)

    @property
    def vp8_key_header(self):
        if not self.is_start_of_frame:
            raise ValueError('Not start of frame.')
        if not self.vp8_header.is_key_frame:
            raise ValueError('Not key frame.')
        b = self.payload[ctypes.sizeof(VP8Header):ctypes.sizeof(VP8Header) + ctypes.sizeof(VP8KeyFrameHeader)]
        return VP8KeyFrameHeader.from_buffer_copy(b)

    # RTPPacket

    @classmethod
    def parse_buffer(cls, b, depad=True):
        header, csrcs, b, pad = super(VP8RTPPacket, cls).parse_buffer(b, depad)

        # descriptor
        desc = VP8RTPPayloadDescriptor.from_buffer_copy(b)
        b = b[ctypes.sizeof(desc):]

        # descriptor x
        if desc.x:
            desc_x = VP8RTPPayloadDescriptorX.from_buffer_copy(b)
            b = b[ctypes.sizeof(desc_x):]
        else:
            desc_x = None

        # descriptor i
        if desc_x and desc_x.i:
            desc_i = VP8RTPPayloadDescriptorI.from_buffer_copy(b)
            b = b[desc_i.size:]
        else:
            desc_i = None

        # descriptor l
        if desc_x and desc_x.l:
            desc_l = VP8RTPPayloadDescriptorL.from_buffer_copy(b)
            b = b[ctypes.sizeof(desc_l):]
        else:
            desc_l = None

        # descriptor tk
        if desc_x and (desc_x.t or desc_x.k):
            desc_tk = VP8RTPPayloadDescriptorTK.from_buffer_copy(b)
            b = b[ctypes.sizeof(desc_tk):]
        else:
            desc_tk = None

        # payload
        payload = b

        return header, csrcs, desc, desc_x, desc_i, desc_l, desc_tk, payload, pad

    def dump_header(self, fo):
        super(VP8RTPPacket, self).dump_header(fo)
        fo.write(buffer(self.vp8_descriptor))
        if self.vp8_descriptor.x:
            fo.write(buffer(self.vp8_descriptor_x))
        if self.vp8_descriptor_x and self.vp8_descriptor_x.i:
            fo.write(buffer(self.vp8_descriptor_i))
        if self.vp8_descriptor_x and self.vp8_descriptor_x.l:
            fo.write(buffer(self.vp8_descriptor_l))
        if self.vp8_descriptor_x and (self.vp8_descriptor_x.t or self.vp8_descriptor_x.k):
            fo.write(buffer(self.vp8_descriptor_tk))

    # RTPTimeMixin

    clock_rate = 90000

    # RTPVideoMixin

    @property
    def is_start_of_frame(self):
        return self.vp8_descriptor.s == 1 and self.vp8_descriptor.pid == 0

    @property
    def is_key_frame(self):
        return self.vp8_header.is_key_frame

    @property
    def width(self):
        return self.vp8_key_header.width

    @property
    def height(self):
        return self.vp8_key_header.height


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
