"""
"""
import dpkt

from . import rtp


def is_rtp_packet(pkt):
    if (not isinstance(pkt.data, dpkt.ip.IP) or
        not isinstance(pkt.data.data, dpkt.udp.UDP)):
        return False
    rtp = dpkt.rtp.RTP(pkt.data.data.data)
    return rtp.version == 2 and (rtp.pt < 64 or 96 <= rtp.pt)


class PCapRTPPacketReader(rtp.RTPPacketReader):
    """
    Iterates and indexes `RTPPacket`s from a PCAP formatted file.
    """
    
    def __init__(self, *args, **kwargs):
        super(PCapRTPPacketReader, self).__init__(*args, **kwargs)
        self.org = self.fo.tell() + dpkt.pcap.FileHdr.__hdr_len__
        self.i = iter(dpkt.pcap.Reader(self.fo))
        try:
            self.i.next()
        except StopIteration:
            pass
        self.reset()

    # rtp.RTPPacketReader

    def __iter__(self):

        def pkts():
            while True:
                _, buf = self.i.next()
                eth = dpkt.ethernet.Ethernet(buf)
                if not is_rtp_packet(eth):
                    continue
                pkt = self.packet_type(eth.data.data.data)
                if not self.packet_filter(pkt):
                    continue
                yield pkt

        self.fo.seek(self.org)
        return pkts()


rtp.RTPPacketReader.register('pcap', PCapRTPPacketReader)
