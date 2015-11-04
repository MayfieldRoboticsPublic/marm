"""
Command line interface to marm. See:

.. code:: bash

    $ marm --help

for usage.
"""
import argparse
import collections
import logging
import os
import re

from . import __version__, rtp, vp8, opus, mjr, frame, Frames, VideoFrame, VideoFrames


logger = logging.getLogger(__name__)


packet_types = {
    'vp8': vp8.VP8RTPPacket,
    'opus': opus.OpusRTPPacket,
}

encoders = {
    vp8.VP8RTPPacket: 'libvpx',
    opus.OpusRTPPacket: 'libopus',
}

log_levels = {
    'd': logging.DEBUG,
    'i': logging.INFO,
    'w': logging.WARN,
    'e': logging.ERROR,
}


class StreamDescription(collections.namedtuple(
        'StreamDescription', ['packet_types', 'order']
    )):

    INTERLEAVE = 'interleave'
    CONCAT = 'concat'
    
    def bucket(self, *archives):
        if len(archives) == 1 and isinstance(archives[0], list):
            archives = archives[0]
        else:
            archives = list(archives)
        if len(archives) % len(self.packet_types) != 0:
            raise ValueError(
                'Archive count must be a factor of {0}'
                .format(len(self.packet_types))
            )
        if self.order == self.INTERLEAVE:
            s = len(self.packet_types)
            buckets = [
                (self.packet_types[i], archives[i::s])
                for i in range(s)
            ]
        else:  # self.order == self.CONCAT
            n = len(archives) / len(self.packet_types)
            buckets = [
                (self.packet_types[i / n], archives[i:i + n])
                for i in range(0, len(archives), n)
            ]
        return buckets


class ParamsAction(argparse.Action):
    
    params = None
    
    def parse(self, value):
        profile = {}
        for k, v in re.findall(r'([^=,\s]*)\s*=\s*([^,]*)', value):
            if k not in self.params:
                raise argparse.ArgumentError(
                    self, '{0}= not a supported param'.format(k),
                )
            try:
                pv = self.params[k](v)
            except (TypeError, ValueError), ex:
                raise argparse.ArgumentError(
                    self, '{0}= value "{1}" invalid ({2})'.format(k, v, ex),
                )
            profile[k] = pv
        return profile


    # argparse.Action

    def __call__(self, parser, namespace, values, option_string=None):
        if isinstance(values, basestring):
            setattr(namespace, self.dest, self.parse(values))
        else:
            setattr(namespace, self.dest, map(self.parse, values))


class PacketFilterAction(ParamsAction):

    # ParamsAction

    params = {
        'pt': int,
        'ssrc': int,
    }


class VideoProfileAction(ParamsAction):
    
    # ParamsAction

    params = {
        'encoder_name': str,
        'pix_fmt': int,
        'width': int,
        'height': int,
        'frame_rate': float,
        'bit_rate': int,
    }


class AudioProfileAction(ParamsAction):

    # ParamsAction

    params = {
        'encoder_name': str,
        'sample_rate': int,
        'bit_rate': int,
    }


class StreamDescriptionAction(argparse.Action):

    def parse(self, value):
        if ',' in value:
            types = value.split(',')
            order = StreamDescription.CONCAT
        elif '!' in value:
            types = value.split('!')
            order = StreamDescription.INTERLEAVE
        else:
            types = [value]
            order = StreamDescription.CONCAT
        for t in types:
            if t not in packet_types:
                raise argparse.ArgumentError(
                    self, '"{0}" not a supported packet type'.format(t),
                )
        return StreamDescription(
            packet_types=[packet_types[t] for t in types],
            order=order
        )
    
    # argparse.Action
    
    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, self.dest, map(self.parse, values))


def split_parser(cmd_parsers, parents):
    """
    Split command parser.
    """
    split_parser = cmd_parsers.add_parser(
        'split',
        help='splits archived media packets into multiple files',
        parents=parents,
    )
    split_parser.add_argument(
        '-d', '--duration', '--dur',
        type=float,
        default=None,
        help='limit duration of each part to this',
        metavar='DURATION',
    )
    split_parser.add_argument(
        '-c', '--count',
        type=int,
        default=None,
        help='limit number of packets in each part to this',
        metavar='COUNT',
    )
    split_parser.add_argument(
        '-f', '--force',
        action='store_true',
        default=False,
        help='overwrite existing splits',
    )
    split_parser.add_argument(
        '--filter',
        action=PacketFilterAction,
        help='packet filter',
    )
    split_parser.add_argument(
        'packet_type',
        choices=packet_types.keys(),
        help='type of media packet in archive',
        metavar='PACKET-TYPE',
    )
    split_parser.add_argument(
        'in_path',
        nargs=1,
        help='path to input archive'
    )
    split_parser.add_argument(
        'out_format',
        nargs='?',
        help='format for path to split archive (e.g. /tmp/out-{part:02}).'
    )
    split_parser.set_defaults(cmd=split_cmd)


def split_cmd(args):
    """
    Split command.
    """
    in_path = args.in_path[0]
    out_format = args.out_format
    if out_format is None or os.path.isdir(out_format):
        p = os.path.abspath(in_path)
        _, ext = os.path.splitext(p)
        name = os.path.basename(in_path)[:-len(ext)]
        if ext == '.pcap':
            ext = '.mjr'
        d = out_format if out_format else os.path.dirname(p)
        out_format = os.path.join(d, '{0}-{1}{2}'.format(name, '{part:02}', ext))
        logger.info('generated format "%s"', out_format)
    _, ext = os.path.splitext(out_format)
    if ext:
        ext = ext[1:]
    if ext != 'mjr':
        raise ValueError('Only {0} output archives supported.'.format('mjr'))

    logger.info(
        'splitting "%s" w/ duration=%s, count=%s',
        in_path, args.duration, args.count,
    )
    if args.filter:
        pt = args.filter.get('pt')
        ssrc = args.filter.get('ssrc')
        packet_filter = lambda pkt: (
            (pt is None or pkt.header.type == pt) and
            (ssrc is None or pkt.header.ssrc == ssrc)
        )
    else:
        packet_filter = None
    pkts = rtp.RTPPacketReader.open(
        in_path,
        packet_type=packet_types[args.packet_type],
        packet_filter=packet_filter,
    )
    splits = rtp.split_packets(pkts, duration=args.duration, count=args.count)
    split_count = 0
    pkt_total = 0
    for i, split in enumerate(splits):
        out_path = out_format.format(part=i + 1)
        if not args.force and os.path.exists(out_path):
            pkt_count = sum(1 for _ in split)
            logger.warn(
                'not overwriting existing split %s @ "%s", skipping %s packets',
                i + 1, out_path, pkt_count,
            )
        else:
            logger.info('writing split %s to "%s"', i + 1, out_path)
            pkt_count = 0
            with open(out_path, 'wb') as fo:
                mjr.write_header(fo, pkts.packet_type.type)
                for pkt in split:
                    mjr.write_packet(fo, pkt)
                    pkt_count += 1
            logger.info('wrote %s packets to split "%s"', pkt_count, out_path)
            pkt_total += pkt_count
            split_count += 1
    logger.info(
        'wrote %s packets to %s splits w/ format "%s"',
        pkt_total, split_count, out_format,
    )


def mux_parser(cmd_parsers, parents):
    """
    Mux command parser.
    """
    mux_parser = cmd_parsers.add_parser(
        'mux',
        help='multiplexes archived media packets to a container file',
        parents=parents,
    )
    mux_parser.add_argument(
        '-o', '--offset',
        type=int,
        default=0,
        help='offset to stream',
        metavar='OFFSET',
    )
    mux_parser.add_argument(
        '-v', '--video-profile',
        action=VideoProfileAction,
        default=[],
        help='video profile to use when muxing',
    )
    mux_parser.add_argument(
        '-a', '--audio-profile',
        action=AudioProfileAction,
        default=[],
        help='audio profile to use when muxing',
    )
    mux_parser.add_argument(
        '-f', '--force',
        action='store_true',
        default=False,
        help='overwrite existing container',
    )
    mux_parser.add_argument(
        '-d', '--dry',
        action='store_true',
        default=False,
        help='abort just before muxing',
    )
    mux_parser.add_argument(
        '--video-frame-rate-window',
        type=int,
        default=10,
        help='number of video frames over which estimate frame rate',
    )
    mux_parser.add_argument(
        'container',
        nargs=1,
        help='mux input archives to this container file',
    )
    mux_parser.add_argument(
        'description',
        action=StreamDescriptionAction,
        nargs=1,
        help=(
            'packet-type(s) ({0}) separated by , (interleaved) or | (grouped) '
            'describing input archives to follow'
            .format(', '.join(packet_types.keys()))
        ),
        metavar='DESCRIPTION',
    )
    mux_parser.add_argument(
        'archives',
        nargs='*',
        help=(
            'input archive w/ packet type and bucketing controlled by '
            'DESCRIPTION'
        ),
    )
    mux_parser.set_defaults(cmd=mux_cmd)


def mux_cmd(args):
    """
    Mux command.
    """
    description = args.description[0]
    logger.info(
        'bucketing archives to cursors using description %s', description
    )
    buckets = description.bucket(args.archives)
    for i, (_, parts) in enumerate(buckets):
        logger.info(
            'stream %s (%s) - \n%s',
            i,
            description.packet_types    [i],
            '\n'.join('  {0}'.format(part) for part in parts),
        )
    curs = [
        rtp.RTPCursor(
            archives,
            rtp.RTPPacketReader.open,
            packet_type=packet_type,
        )
        for packet_type, archives in buckets
    ]

    if args.offset:
        logger.info('offsetting cursors to %s', args.offset)
        for cur in curs:
            cur.seek((args.offset, 0))

    logger.info('resolving video')
    v_curs = [
        (i, packet_type, curs[i])
        for i, (packet_type, _) in enumerate(buckets)
        if packet_type.type == rtp.RTPPacket.VIDEO_TYPE
    ]
    if len(v_curs) > 1:
        raise NotImplementedError('Only one video stream for now')
    if v_curs:
        i, packet_type, v_cur = v_curs[0]
        v_prof = (
            args.video_profile[i].copy()
            if i < len(args.video_profile)
            else {}
        )
        if 'encoder_name' not in v_prof:
            v_prof['encoder_name'] = encoders[packet_type]
        if 'pix_fmt' not in v_prof:
            v_prof['pix_fmt'] = VideoFrame.PIX_FMT_YUV420P
        if 'width' not in v_prof:
            with v_cur.restoring():
                width, _ = rtp.probe_video_dimensions(v_cur)
            v_prof['width'] = width
        if 'height' not in v_prof:
            with v_cur.restoring():
                _, height = rtp.probe_video_dimensions(v_cur)
            v_prof['height'] = height
        if 'frame_rate' not in v_prof:
            with v_cur.restoring():
                frame_rate = rtp.estimate_video_frame_rate(
                    v_cur, window=args.video_frame_rate_window
                )
            v_prof['frame_rate'] = frame_rate
        if 'bit_rate' not in v_prof:
            v_prof['bit_rate'] = 1000000
        v_prof['time_base'] = (1, 1000)
        logger.info(
            'using video profile -\n%s',
            '\n'.join('  {0}={1}'.format(k, v) for k, v in v_prof.items())
        )
        v_frames = VideoFrames(v_cur)
    else:
        logger.info('no video')
        v_frames = None
        v_prof = None

    logger.info('resolving audio')
    a_curs = [
        (i, packet_type, curs[i])
        for i, (packet_type, _) in enumerate(buckets)
        if packet_type.type == rtp.RTPPacket.AUDIO_TYPE
    ]
    if len(a_curs) > 1:
        raise NotImplementedError('Only one audio stream for now')
    if a_curs:
        i, packet_type, a_cur = a_curs[0]
        a_prof = (
            args.audio_profile[i].copy()
            if i < len(args.audio_profile)
            else {}
        )
        if 'encoder_name' not in a_prof:
            a_prof['encoder_name'] = encoders[packet_type]
        if 'sample_rate' not in a_prof:
            a_prof['sample_rate'] = 48000
        if 'bit_rate' not in a_prof:
            a_prof['bit_rate'] = 96000
        if 'channel_layout' not in a_prof:
            with v_cur.restoring():
                a_prof['channel_layout'] = rtp.probe_audio_channel_layout(a_cur)
        a_prof['time_base'] = (1, 1000)
        logger.info(
            'using audio profile -\n%s',
            '\n'.join('  {0}={1}'.format(k, v) for k, v in a_prof.items())
        )
        a_frames = Frames(a_cur)
    else:
        logger.info('no audio')
        a_frames = None
        a_prof = None

    container = args.container[0]
    logger.info('muxing frames to "%s"', container)
    if args.dry:
        logger.info('dry run, skipping ... ')
    else:
        if not args.force and os.path.exists(container):
            raise Exception(
                'Not overwriting existing container "{0}"'.format(container)
            )
        with open(args.container[0], 'wb') as fo:
            frame.mux(
                fo,
                audio_profile=a_prof,
                audio_packets=a_frames,
                video_profile=v_prof,
                video_packets=v_frames,
            )


def parser():
    arg_parser = argparse.ArgumentParser(
        description="""\
libav* front-end extract recorded a/v packets from archives and mux them to
containers.
""",
        version=__version__,
    )
    cmn_parser = argparse.ArgumentParser(add_help=False)
    cmn_parser.add_argument(
        '-l', '--log-level',
        choices=log_levels.keys(),
        default='w',
        help='log level',
    )
    cmd_parsers = arg_parser.add_subparsers(title='commands')
    split_parser(cmd_parsers, [cmn_parser])
    mux_parser(cmd_parsers, [cmn_parser])
    return arg_parser


# Command line parser.
arg_parser = parser()
