from . import rtp


class OpusRTPPacket(rtp.RTPTimeMixin, rtp.RTPPacket):
    """
    See https://tools.ietf.org/html/draft-ietf-payload-rtp-opus-11
    """

    # rtp.RTPPacket

    type = rtp.RTPPacket.AUDIO_TYPE


    # RTPTimeMixin

    clock_rate = 48000
