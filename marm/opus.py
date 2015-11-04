import StringIO

from . import rtp


clock_rate = 48000


class OpusRTPPayload(rtp.RTPAudioPayloadMixin, rtp.RTPPayload):

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
                self.data = ''
                for k, v in kwargs.iteritems():
                    if k not in ('data',):
                        raise TypeError('Unexpected keyword argument \'{0}\''.format(k))
                    setattr(self, k, v)

    @property
    def nb_frames(self):
        count = ord(self.data[0]) & 0x3;
        if count == 0:
            return 1
        elif count != 3:
            return 2
        elif len(self.data) < 2:
            raise ValueError('Invalid packet')
        return ord(self.data[1]) & 0x3F;

    @property
    def nb_samples_per_frame(self):
        toc = ord(self.data[0])
        size = 0
        if toc & 0x80:
            size = ((toc >> 3) & 0x3);
            size = (clock_rate << size) / 400;
        elif toc & 0x60 == 0x60:
            size = clock_rate / 50 if toc & 0x08 else clock_rate / 100;
        else:
            size = ((toc >> 3) & 0x3)
            if size == 3:
                size = clock_rate * 60 / 1000
            else:
                size = (clock_rate << size) / 100
        return size

    # RTPAudioMixin

    @property
    def nb_samples(self):
        """
        https://github.com/xiph/opus/blob/5dca296833ce4941dceadf956ff0fb6fe59fe4e8/src/opus_decoder.c#L960
        """
        samples = self.nb_frames * self.nb_samples_per_frame
        # NOTE: can't have more than 120 ms
        if samples * 25 > clock_rate * 3:
            raise ValueError('Invalid packet')
        return samples

    @property
    def nb_channels(self):
        """
        https://github.com/xiph/opus/blob/5dca296833ce4941dceadf956ff0fb6fe59fe4e8/src/opus_decoder.c#L939
        """
        return 2 if (ord(self.data[0]) & 0x4) else 1

    # RTPPayload

    def pack(self, fo=None):
        if fo is None:
            fo, value = StringIO.StringIO(), True
        else:
            value = False
        fo.write(self.data)
        if value:
            return fo.getvalue()

    def unpack(self, buf):
        self.data = buf


class OpusRTPPacket(rtp.RTPTimeMixin, rtp.RTPPacket):
    """
    https://tools.ietf.org/html/draft-ietf-payload-rtp-opus-11
    """

    # RTPPacket

    type = rtp.RTPPacket.AUDIO_TYPE

    payload_type = OpusRTPPayload

    # RTPTimeMixin

    clock_rate = clock_rate
