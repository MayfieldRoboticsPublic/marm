import collections
import logging
import sys

cimport cpython
cimport cpython.exc
cimport cpython.ref
from libc.stdint cimport int64_t
from libc.stdio cimport stderr
from libc.string cimport memcpy, memset

cimport libavcodec
cimport libavformat
cimport libavutil
from libcx cimport va_list, va_start, va_end, va_copy, vsnprintf
cimport libmarm


# exc propagation

cdef struct exc_info:
    
    cpython.ref.PyObject *type
    cpython.ref.PyObject *value
    cpython.ref.PyObject *tb


cdef void save_exc(exc_info *ei):
    ei.type = ei.value = ei.tb = NULL
    if cpython.exc.PyErr_Occurred() == NULL:
        return
    cpython.exc.PyErr_Fetch(&ei.type, &ei.value, &ei.tb)


cdef void restore_exc(exc_info *ei):
    if ei.type == NULL:
        return
    cpython.exc.PyErr_Restore(ei.type, ei.value, ei.tb)
    ei.type = ei.value = ei.tb = NULL


# libav* logging

class LibAVLoggingFilter(logging.Formatter):
    
    def filter(self, record):
        record.msg = record.msg.rstrip()
        return 1


logging.getLogger('libav*').addFilter(LibAVLoggingFilter())

av_log = logging.getLogger('libav*').log


cdef void av_log_cb(void *avcl, int level, const char *fmt, va_list vl) except *:
    cdef char[1024] msg
    cdef int print_prefix = 1
    cdef int log_level = logging.NOTSET
    cdef object ex_type
    cdef object ex_value
    cdef object ex_tb
    cdef exc_info ei
    
    if level == libavutil.AV_LOG_PANIC:
        log_level = logging.FATAL
    elif level == libavutil.AV_LOG_ERROR:
        log_level = logging.ERROR
    elif level == libavutil.AV_LOG_WARNING:
        log_level = logging.WARN
    elif level == libavutil.AV_LOG_INFO:
        log_level = logging.INFO
    elif level == libavutil.AV_LOG_DEBUG:
        log_level = logging.DEBUG
    libavutil.av_log_format_line(avcl, level, fmt, vl, msg, 1023, &print_prefix)
    
    save_exc(&ei)
    try:
        av_log(log_level, msg)
    finally:
        restore_exc(&ei)


libavutil.av_log_set_callback(av_log_cb)


# libav* codecs

Codec = collections.namedtuple('Codec', [
    'name',
    'long_name',
    'type',
])


cdef class codecs(object):

    cdef libavformat.AVCodec *i;

    def __init__(self):
        self.i = NULL;

    def __iter__(self):
        return self

    def __next__(self):
        self.i = libavcodec.av_codec_next(self.i)
        if self.i == NULL:
            raise StopIteration
        return Codec(
            name=self.i.name,
            long_name=self.i.long_name if self.i.long_name != NULL else None,
            type=self.i.type,
        )


# libav* formats

Format = collections.namedtuple('Format', [
    'name',
    'long_name',
    'mime_type',
    'extensions',
])


cdef class output_formats(object):

    cdef libavformat.AVOutputFormat *i;

    def __init__(self):
        self.i = NULL;

    def __iter__(self):
        return self

    def __next__(self):
        self.i = libavformat.av_oformat_next(self.i)
        if self.i == NULL:
            raise StopIteration
        return Format(
            name=self.i.name,
            long_name=self.i.long_name if self.i.long_name != NULL else None,
            mime_type=self.i.mime_type if self.i.mime_type != NULL else None,
            extensions=self.i.extensions if self.i.extensions != NULL else None,
        )


cdef class InputFormat(object):

    cdef libavformat.AVInputFormat *iformat
    
    def __init__(self):
        self.iformat = NULL
        
    @staticmethod
    cdef create(libavformat.AVInputFormat *iformat):
        i = InputFormat()
        i.iformat = iformat
        return i
    
    property name:

        def __get__(self):
            return self.iformat.name
    
    property long_name:

        def __get__(self):
            return self.iformat.long_name
    
    property extensions:

        def __get__(self):
            return self.iformat.extensions


cdef class FormatContext(object):

    cdef libavformat.AVFormatContext *ctx

    def __init__(self):
        self.ctx = NULL
        
    def __dealloc__(self):
        cdef libavformat.AVIOContext *io_ctx = NULL;
        if self.ctx != NULL:
            io_ctx = self.ctx.pb
            libavformat.avformat_close_input(&self.ctx)
        if io_ctx != NULL:
            libavutil.av_freep(&io_ctx.buffer);
            libavutil.av_freep(&io_ctx)
        
    @staticmethod
    cdef create(libavformat.AVFormatContext *ctx):
        i = FormatContext()
        i.ctx = ctx
        return i

    property nb_streams:

        def __get__(self):
            return self.ctx.nb_streams
        
    property iformat:

        def __get__(self):
            return None if self.ctx.iformat == NULL else InputFormat.create(self.ctx.iformat)


cdef class Packet(object):

    cdef libavcodec.AVPacket *pkt
    
    property pts:

        def __get__(self):
            return self.pkt.pts

    property dts:

        def __get__(self):
            return self.pkt.dts
        
    property flags:

        def __get__(self):
            return self.pkt.flags

    property stream_index:

        def __get__(self):
            return self.pkt.stream_index
        
    property duration:

        def __get__(self):
            return self.pkt.duration

# libmarm platform

class MARMError(Exception):
    """
    Exception wrapper for libmarm.marm_result_t.
    """
    
    def __init__(self, errno):
        super(MARMError, self).__init__(self.errstr(errno))
        self.errno = errno

    
    OK = <int>libmarm.MARM_RESULT_OK
    ABORTED = <int>libmarm.MARM_RESULT_ABORTED
    WRITE_FAILED = <int>libmarm.MARM_RESULT_WRITE_FAILED
    
    errstrs = {
        OK: 'Ok.',
        ABORTED: 'Operation aborted',
        WRITE_FAILED: 'Write to file failed',
    }
    
    @classmethod
    def errstr(cls, errno):
        return cls.errstrs.get(errno, 'Unknown')


marm_log = logging.getLogger('marm.ext').log


cdef void marm_log_cb(libmarm.marm_ctx_t *ctx, int level, const char *fmt, ...) except *:
    cdef va_list vl
    cdef char[1024] msg
    cdef int log_level = logging.NOTSET
    cdef exc_info ei
    
    if level == libmarm.MARM_LOG_LEVEL_DEBUG:
        log_level = logging.DEBUG
    elif level == libmarm.MARM_LOG_LEVEL_INFO:
        log_level = logging.INFO
    elif level == libmarm.MARM_LOG_LEVEL_WARN:
        log_level = logging.WARN
    elif level == libmarm.MARM_LOG_LEVEL_ERROR:
        log_level = logging.ERROR
    
    va_start(vl, fmt)
    vsnprintf(msg, 1023, fmt, vl)
    va_end(vl)
    
    save_exc(&ei)
    try:
        marm_log(log_level, msg)
    finally:
        restore_exc(&ei)


cdef long marm_read_cb(libmarm.marm_ctx_t *ctx, void* file, void *data, size_t size) except? -1:
    buf = (<object>file).read(size)
    cdef size_t buf_size = cpython.PyString_Size(buf)
    memcpy(data, cpython.PyString_AsString(buf), buf_size)
    return buf_size


cdef int marm_write_cb(libmarm.marm_ctx_t *ctx, void* file, const void *data, size_t size) except? -1:
    cdef object buf = cpython.PyString_FromStringAndSize(<const char *>data, size)
    (<object>file).write(buf)
    return size


cdef long marm_seek_cb(libmarm.marm_ctx_t *ctx, void *file, long offset, int whence) except? -1:
    (<object>file).seek(offset, whence)
    return (<object>file).tell()


cdef int marm_abort_cb(libmarm.marm_ctx_t *ctx) except *:
    return 1 if cpython.exc.PyErr_Occurred() != NULL else 0


cdef int marm_next_packet_cb(libmarm.marm_ctx_t *ctx, void *packets, libavcodec.AVPacket *av_packet) except? -1:
    cdef int64_t pts
    cdef int flags
    cdef object data
    cdef int size
    cdef object ex_type, ex_value, ex_tb
    
    try:
        pkt = (<object>packets).next()
    except StopIteration:
        return -1
    
    # data
    size = len(pkt.data)
    if av_packet.size < size:
        libavcodec.av_grow_packet(av_packet, size - av_packet.size)
    else:
        libavcodec.av_shrink_packet(av_packet, size);
    memcpy(av_packet.data, <const char *>pkt.data, size)
    
    # meta
    av_packet.pts = pkt.pts
    if pkt.pts == 0:
        av_packet.dts = 0
    av_packet.flags = pkt.flags
    
    return 0


cdef int marm_filter_packet_cb(libmarm.marm_ctx_t *ctx, void *filter, libavcodec.AVPacket *av_packet) except? -1:
    cdef tuple packet_filter = <tuple>filter
    cdef Packet packet = packet_filter[0]
    cdef object cb = packet_filter[1]
    packet.pkt = av_packet
    return cb(packet)


def marm_error(res):
    if res != libmarm.MARM_RESULT_OK:
        if cpython.exc.PyErr_Occurred() != NULL:
            raise
        raise MARMError(res)


cdef marm_ctx(libmarm.marm_ctx_t *ctx):
    ctx.log = marm_log_cb
    ctx.next_packet = marm_next_packet_cb
    ctx.filter_packet = marm_filter_packet_cb
    ctx.read = marm_read_cb
    ctx.write = marm_write_cb
    ctx.seek = marm_seek_cb
    ctx.abort = marm_abort_cb


# libav* wrappers

AV_CH_LAYOUT_MONO = libavcodec.AV_CH_LAYOUT_MONO
AV_CH_LAYOUT_STEREO = libavcodec.AV_CH_LAYOUT_STEREO

# libmarm wrappers

FILTER_KEEP = libmarm.MARM_PACKET_FILTER_KEEP
FILTER_DROP = libmarm.MARM_PACKET_FILTER_DROP
FILTER_KEEP_ALL = libmarm.MARM_PACKET_FILTER_KEEP_ALL
FILTER_DROP_ALL = libmarm.MARM_PACKET_FILTER_DROP_ALL

cpdef object generate_audio(
        object file,
        const char* encoder_name,
        int header=1,
        int raw=0,
        const char *type='sin',
        int duration=10,
        int samples=-1,
        int bit_rate=96000,
        int sample_rate=48000,
        int channel_layout=libavcodec.AV_CH_LAYOUT_STEREO,
        object time_base=(0, 0),
        int offset_ts=0):
    cdef int res = libmarm.MARM_RESULT_OK
    cdef libmarm.marm_ctx_t ctx
    cdef libmarm.marm_gen_a_t p
    cdef int nb_samples;
    cdef int nb_frames;
    
    try:
        # context
        marm_ctx(&ctx)

        # profile
        p.encoder_name = encoder_name
        p.bit_rate = bit_rate
        p.sample_rate = sample_rate
        p.channel_layout = channel_layout
        p.time_base.num, p.time_base.den = time_base
        res = libmarm.marm_gen_a_open(&ctx, &p);
        marm_error(res)
        
        # generate
        if header and not raw:
            res = libmarm.marm_gen_a_header(&ctx, <void *>file, &p)
            marm_error(res)
        res = libmarm.marm_gen_a(
            &ctx,
            <void *>file,
            &nb_samples,
            &nb_frames,
            &p,
            type,
            duration,
            samples,
            offset_ts,
            raw
        );
        marm_error(res)
    finally:
        libmarm.marm_gen_a_close(&p)
    return nb_samples, nb_frames


cpdef object generate_video(
        object file,
        const char* encoder_name,
        int header=1,
        int raw=0,
        int duration=10,
        int pix_fmt=libavutil.AV_PIX_FMT_YUV420P,
        int width=320,
        int height=240,
        int bit_rate=400000,
        int frame_rate=25):
    cdef int res = libmarm.MARM_RESULT_OK
    
    cdef libmarm.marm_ctx_t ctx
    memset(&ctx, 0, sizeof(ctx))
    
    cdef libmarm.marm_gen_v_t v
    memset(&v, 0, sizeof(v))
    
    try:
        # context
        marm_ctx(&ctx)
        
        # video
        v.ctx = &ctx
        v.file = <void *>file
        v.encoder_name = encoder_name
        v.pix_fmt = <libavutil.AVPixelFormat>pix_fmt
        v.width = width
        v.height = height
        v.bit_rate = bit_rate
        v.frame_rate = frame_rate
        res = libmarm.marm_gen_v_open(&v);
        marm_error(res)
        
        # generate
        if header and not raw:
            res = libmarm.marm_gen_v_header(&v)
            marm_error(res)
        res = libmarm.marm_gen_v(&v, duration, raw);
        marm_error(res)
    finally:
        libmarm.marm_gen_v_close(&v)


cpdef object mux(
        object file,
        const char *format_extension,
        object a_profile,
        object a_packets,
        object v_profile,
        object v_packets,
        const char *format_name=NULL,
        object options=None):
    cdef int res = libmarm.MARM_RESULT_OK
    cdef libmarm.marm_ctx_t ctx
    cdef libmarm.marm_mux_a_t a
    cdef int has_a = a_packets is not None
    cdef libmarm.marm_mux_v_t v
    cdef int has_v = v_packets is not None
    cdef libavutil.AVDictionary *av_opts = NULL
    
    try:
        # context
        marm_ctx(&ctx)
        
        # options
        if options:
            for i, (key, value) in enumerate(options):
                libavutil.av_dict_set(&av_opts, <bytes>key, <bytes>value, 0)
        
        # audio
        if has_a:
            a.ctx = &ctx
            a.packets = <void *>a_packets
            a.encoder_name = a_profile['encoder_name']
            a.channel_layout = a_profile['channel_layout']
            a.bit_rate = a_profile.get('bit_rate', 0)
            a.sample_rate = a_profile['sample_rate']
            if 'time_base' in a_profile:
                a.time_base.num = a_profile['time_base'][0]
                a.time_base.den = a_profile['time_base'][1]
            else:
                a.time_base.num = 1
                a.time_base.den = a.sample_rate
            a.initial_padding = a_profile.get('initial_padding', -1)
            res = libmarm.marm_mux_a_open(&a)
            marm_error(res)
        
        # video
        if has_v:
            v.ctx = &ctx
            v.packets = <void *>v_packets
            v.encoder_name = v_profile['encoder_name']
            v.pix_fmt = <libavutil.AVPixelFormat>v_profile['pix_fmt']
            v.width = v_profile['width']
            v.height = v_profile['height']
            v.bit_rate = v_profile.get('bit_rate', 0)
            v.frame_rate = v_profile['frame_rate']
            if 'time_base' in v_profile:
                v.time_base.num = v_profile['time_base'][0]
                v.time_base.den = v_profile['time_base'][1]
            else:
                v.time_base.num = 1
                v.time_base.den = v.frame_rate
            res = libmarm.marm_mux_v_open(&v)
            marm_error(res)
        
        # mux them
        res = libmarm.marm_mux(
            &ctx,
            <void *>file,
            libmarm.MARM_MUX_FLAG_MONOTONIC_FILTER,
            format_name,
            format_extension,
            &v if has_v else NULL,
            &a if has_a else NULL,
            av_opts
        )
        marm_error(res)
    finally:
        if av_opts != NULL:
            libavutil.av_dict_free(&av_opts)
        if has_a:
            libmarm.marm_mux_a_close(&a)
        if has_v:
            libmarm.marm_mux_v_close(&v)


cpdef object remux(
        object out_file,
        const char *out_format_extension,
        object in_file,
        const char *in_format_extension,
        object filter=None,
        const char *out_format_name=NULL,
        const char *in_format_name=NULL,
        object mpegts_ccs=None,
        object offset_pts=None,
        object options=None):

    cdef int res = libmarm.MARM_RESULT_OK
    cdef libmarm.marm_ctx_t ctx
    cdef tuple packet_filter
    cdef void *filter_p = NULL
    cdef libmarm.marm_mpegts_cc_t mpegts_ccs_a[32]
    cdef libmarm.marm_mpegts_cc_t *mpegts_ccs_p = NULL
    cdef int64_t offset_pts_a[32]
    cdef int64_t *offset_pts_p = NULL
    cdef libavutil.AVDictionary *av_opts = NULL
    
    if options:
        for i, (key, value) in enumerate(options):
            libavutil.av_dict_set(&av_opts, <bytes>key, <bytes>value, 0)
    
    try:
        # packet filter
        if filter:
            packet_filter = Packet(), filter
            filter_p = <void *>(packet_filter)
    
        # mpegts continuity counters
        if mpegts_ccs:
            memset(&mpegts_ccs_a, 0, sizeof(mpegts_ccs_a))
            if len(mpegts_ccs) > 32:
                raise ValueError('len(mpegts_ccs) > {0}'.format(32))
            if isinstance(mpegts_ccs, dict):
                mpegts_ccs = mpegts_ccs.items()
            for i, (pid, cc) in enumerate(mpegts_ccs):
                mpegts_ccs_a[i].pid = <int>pid
                mpegts_ccs_a[i].cc = <int>cc
            mpegts_ccs_p = mpegts_ccs_a

        # pts offsets
        if offset_pts:
            memset(&offset_pts_a, 0, sizeof(offset_pts_a))
            if len(offset_pts) > 32:
                raise ValueError('len(offset_pts) > {0}'.format(32))
            if isinstance(offset_pts, dict):
                offset_pts = zip(*sorted(offset_pts.items()))[1]
            for i, offset in enumerate(offset_pts):
                offset_pts_a[i] = <int>offset
            offset_pts_p = offset_pts_a

        # context
        marm_ctx(&ctx)
    
        # remux it
        res = libmarm.marm_remux(
            &ctx,
            <void *>out_file,
            out_format_name,
            out_format_extension,
            <void *>in_file,
            in_format_name,
            in_format_extension,
            filter_p,
            mpegts_ccs_p, <int>(len(mpegts_ccs) if mpegts_ccs else 0),
            offset_pts_p, 32,
            av_opts
        )
        marm_error(res)
    finally:
        if av_opts != NULL:
            libavutil.av_dict_free(&av_opts)


cpdef object last_mpegts_ccs(
        object in_file,
        const char *in_format_extension,
        const char *in_format_name=NULL):

    cdef int res = libmarm.MARM_RESULT_OK
    cdef libmarm.marm_ctx_t ctx
    cdef libmarm.marm_mpegts_cc_t ccs[32]
    cdef int nb_cc = 0;
    
    # context
    marm_ctx(&ctx)
    
    # scan it
    res = libmarm.marm_scan(
        &ctx,
        <void *>in_file, in_format_name, in_format_extension,
        ccs, &nb_cc, 32,
    )
    marm_error(res)
    
    # results
    r = dict([
        (ccs[i].pid, ccs[i].cc)
        for i in range(nb_cc)
    ])
    return r


cpdef object segment(
        object out_file_template,
        const char *out_format_name,
        object in_file,
        const char *in_format_extension,
        const char *in_format_name=NULL,
        float time=2.0,
        float time_delta=0.0,
        object mpegts_ccs=None,
        object options=None):

    cdef int res = libmarm.MARM_RESULT_OK
    cdef libmarm.marm_ctx_t ctx
    cdef libavutil.AVDictionary *av_opts = NULL
    cdef libmarm.marm_mpegts_cc_t mpegts_ccs_a[32]
    cdef libmarm.marm_mpegts_cc_t *mpegts_ccs_p = NULL
    
    # libav* options
    if options:
        for i, (key, value) in enumerate(options):
            libavutil.av_dict_set(&av_opts, <bytes>key, <bytes>value, 0)
    
    try:
        # mpegts continuity counters
        if mpegts_ccs:
            memset(&mpegts_ccs_a, 0, sizeof(mpegts_ccs_a))
            if len(mpegts_ccs) > 32:
                raise ValueError('len(mpegts_ccs) > {0}'.format(32))
            if isinstance(mpegts_ccs, dict):
                mpegts_ccs = mpegts_ccs.items()
            for i, (pid, cc) in enumerate(mpegts_ccs):
                mpegts_ccs_a[i].pid = <int>pid
                mpegts_ccs_a[i].cc = <int>cc
            mpegts_ccs_p = mpegts_ccs_a
        
        # context
        marm_ctx(&ctx)
    
        # segment it
        res = libmarm.marm_segment(
            &ctx,
            out_file_template, out_format_name,
            <void *>in_file, in_format_name, in_format_extension,
            time, time_delta,
            mpegts_ccs_p, <int>(len(mpegts_ccs) if mpegts_ccs else 0),
            av_opts
        )
        marm_error(res)
    finally:
        if av_opts != NULL:
            libavutil.av_dict_free(&av_opts)

# init

libavformat.av_register_all()
