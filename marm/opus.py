"""
https://tools.ietf.org/html/draft-ietf-payload-rtp-opus-11
"""
from . import rtp


class OpusRTPPacket(rtp.RTPTimeMixin, rtp.RTPPacket):

    # RTPTimeMixin

    clock_rate = 48000
