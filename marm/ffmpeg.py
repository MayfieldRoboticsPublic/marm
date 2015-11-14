"""
Helpers for interacting w/ ffmpeg and friends.
"""
from datetime import timedelta
import json
import logging
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

    def __init__(self, args, **kwargs):
        args = [self.bin] + map(str, args)
        self.line = subprocess.list2cmdline(args)
        super(Process, self).__init__(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            **kwargs
        )

    def __call__(self, error='raise'):
        logger.debug('%s ...', self.line)
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
    def for_duration(cls, path):
        probe = cls(['-show_format', path])
        probe()
        return timedelta(seconds=probe.result['format']['duration'])

    # Process

    bin = 'ffprobe'

    def _fulfilled(self, stdout, stderr):
        self.result = FFProbeResult.loads(stdout)
