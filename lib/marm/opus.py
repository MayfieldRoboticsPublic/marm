from __future__ import division

from . import rtp


class OpusRTPPacket(rtp.RTPTimeMixin, rtp.RTPPacket):

    # RTPTimeMixin

    clock_rate = 48000
