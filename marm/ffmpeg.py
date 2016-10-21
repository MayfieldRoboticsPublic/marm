"""
Helpers for interacting w/ ffmpeg and friends.
"""
import collections
from datetime import timedelta
import json
import itertools
import logging
import pipes
import re
import subprocess


logger = logging.getLogger(__name__)


class Error(RuntimeError):

    def __init__(self, process, stdout, stderr):
        message = '"{0}" failed w/ return code {1}'.format(
            process.line, process.returncode
        )
        super(Error, self).__init__(message)
        self.line = process.line
        self.returncode = process.returncode
        self.stdout = stdout
        self.stderr = stderr


class Process(subprocess.Popen):

    #: Location of executable.
    bin = None

    #: Log level to use.
    log_level = logging.DEBUG

    #: Error type.
    Error = Error

    @classmethod
    def as_line(cls, args):
        return ' '.join(
            [cls.bin] +
            [pipes.quote(str(arg)) for arg in args if arg]
        )

    def __init__(self, args, **kwargs):
        args = [self.bin] + [str(arg) for arg in args if arg]
        self.line = subprocess.list2cmdline(args)
        super(Process, self).__init__(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            **kwargs
        )

    def __call__(self, error='raise'):
        stdout, stderr = self.communicate()
        log_level = (logging.ERROR if self.returncode != 0 else self.log_level)
        logging.log(
            log_level, '%s = %s - \n%s', self.line, self.returncode, stderr,
        )
        if self.returncode != 0:
            self._rejected(stdout, stderr)
            if error == 'raise':
                raise self.Error(self, stdout, stderr)
        else:
            self._fulfilled(stdout, stderr)
        return self.returncode

    def _fulfilled(self, stdout, stderr):
        pass

    def _rejected(self, stdout, stderr):
        pass


class FFMPEG(Process):
    """
    `subprocess.Popen` for executing `ffmpeg` and interpreting results.
    """

    @classmethod
    def format_interval(cls, d):
        ts = abs(d.total_seconds())
        return (
            '{sign}{seconds}.{millisecond}'
            .format(
                sign='-' if d.total_seconds() < 0 else '',
                seconds=int(ts),
                millisecond=int((ts - int(ts)) * 1000),
            )
        )

    # Process

    bin = 'ffmpeg'


class FFProbeResult(dict):
    """
    `dict` for parsing `FFProbe` results.
    """

    @classmethod
    def loads(cls, raw):

        def _for_mapping(obj):
            for k, v in obj.iteritems():
                if isinstance(v, dict):
                    _for_mapping(v)
                elif isinstance(v, (list, tuple)):
                    _for_sequence(v)
                elif isinstance(v, basestring):
                    obj[k] = cls._parse_string(v)


        def _for_sequence(obj):
            for k, v in enumerate(obj):
                if isinstance(v, dict):
                    _for_mapping(v)
                elif isinstance(v, (list, tuple)):
                    _for_sequence(v)
                elif isinstance(v, basestring):
                    obj[k] = cls._parse_string(v)

        obj = cls(json.loads(raw))
        _for_mapping(obj)
        return obj

    # internals

    @classmethod
    def _parse_string(cls, txt):
        for r, p in cls._VALUE_PARSERS:
            m = r.match(txt)
            if m:
                return p(m, txt)
        return txt

    _VALUE_PARSERS = [
        (re.compile(r'^\d+:\d+$'), lambda m, v: tuple(map(int, v.split(':')))),
        (re.compile(r'^\d+/\d+$'), lambda m, v: tuple(map(int, v.split('/')))),
        (re.compile(r'^\d+$'), lambda m, v: int(v)),
        (re.compile(r'^\d+\.\d+$'), lambda m, v: float(v)),
        (re.compile(r'^N\/A$'), lambda m, v: None),
    ]


class FFProbe(Process):
    """
    `subprocess.Popen` for executing `ffprobe` and interpreting results, e.g.:

    .. code:: python

        # run it
        ffprobe = FFProbe([
            '-show_format',
            '-show_streams',
            '-count_frames',
            '-count_packets',
            'mpegts_v1-1443977277-1443977282-00000.ts'
        ])
        ffprobe()

        # succeeded
        assert ffprobe.returncode == 0

        # and here are the results
        assert isinstance(ffprobe.result, FFProbe.Result)
        assert isinstance(ffprobe.result['format'], dict)
        assert isinstance(ffprobe.result['streams'], list)
        assert isinstance(ffprobe.result['stream'][0], dict)

    """

    Result = FFProbeResult

    #: Parsed stdout as `FFProbeResult`.
    result = None

    def __init__(self, *args, **kwars):
        args[0].extend([
            '-print_format', 'json',
        ])
        super(FFProbe, self).__init__(*args, **kwars)

    @classmethod
    def for_packets(cls, *args, **kwargs):
        munge = kwargs.pop('munge', None)
        bucket = kwargs.pop('bucket', True)
        probe = cls(['-show_packets'] + list(args), **kwargs)
        probe()
        if not bucket and not munge:
            return probe.result['packets']
        pkts = {} if bucket else []
        munge = munge if munge else lambda pkt: pkt
        for pkt in probe.result['packets']:
            if pkt['stream_index'] not in pkts:
                pkts[pkt['stream_index']] = []
            pkts[pkt['stream_index']].append(munge(pkt))
        return pkts

    @classmethod
    def for_packet_count(cls, *args, **kwargs):
        probe = cls(['-show_streams', '-count_packets'] + list(args), **kwargs)
        probe()
        c = collections.Counter(dict(
            (s['index'], s['nb_read_packets'])
            for s in probe.result['streams']
        ))
        return c

    @classmethod
    def for_first_packet(cls, *args, **kwargs):
        window = kwargs.pop('window', 10)
        probe = cls(['-show_format', '-show_packets'] + list(args), **kwargs)
        probe()
        n = {}
        for idx in range(probe.result['format']['nb_streams']):
            w = sorted(itertools.islice((
                p for p in probe.result['packets'] if p['stream_index'] == idx
            ), window), key=lambda p: p['pts'])
            n[idx] = w[0] if w else None
        return n

    @classmethod
    def for_last_packet(cls, *args, **kwargs):
        window = kwargs.pop('window', 10)
        probe = cls(['-show_format', '-show_packets'] + list(args), **kwargs)
        probe()
        n = {}
        for idx in range(probe.result['format']['nb_streams']):
            w = sorted(itertools.islice((
                p for p in reversed(probe.result['packets']) if p['stream_index'] == idx
            ), window), key=lambda p: p['pts'])
            if w:
                n[idx] = w[-1]
        return n

    @classmethod
    def for_first_frame(cls, *args, **kwargs):
        window = kwargs.pop('window', 10)
        probe = cls(['-show_format', '-show_frames'] + list(args), **kwargs)
        probe()
        n = {}
        for idx in range(probe.result['format']['nb_streams']):
            w = sorted(itertools.islice((
                p
                for p in reversed(probe.result['frames'])
                if p['stream_index'] == idx
            ), window), key=lambda p: p['pkt_pts_time'])
            n[idx] = w[-1] if w else None
        return n

    @classmethod
    def for_format_duration(cls, *args, **kwargs):
        probe = cls(['-show_format'] + list(args), **kwargs)
        probe()
        return timedelta(seconds=probe.result['format']['duration'])

    @classmethod
    def for_stream_durations(cls, *args, **kwargs):
        probe = cls(['-show_streams'] + list(args), **kwargs)
        probe()
        return [
            timedelta(seconds=s['duration'])
            for s in probe.result['streams']
            if 'duration' in s
        ]

    @classmethod
    def for_stream_duration(cls, *args, **kwargs):
        return max(cls.for_stream_durations(*args, **kwargs) + [timedelta()])

    @classmethod
    def for_streams(cls, *args, **kwargs):
        probe = cls(['-show_streams'] + list(args), **kwargs)
        probe()
        return dict((s['index'], s) for s in probe.result['streams'])

    @classmethod
    def for_frame_rate(cls, *args, **kwargs):
        probe = cls(
            ['-show_streams', '-select_streams', 'v'] + list(args),
            **kwargs
        )
        probe()
        return probe.result['streams'][0]['avg_frame_rate']

    # Process

    bin = 'ffprobe'

    def _fulfilled(self, stdout, stderr):
        self.result = FFProbeResult.loads(stdout)
