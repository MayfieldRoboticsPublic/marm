import collections
import logging
import sys

cimport cpython
cimport cpython.exc
cimport cpython.ref
from libc.stdint cimport int64_t
from libc.stdio cimport stderr
from libc.string cimport memcpy

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
    av_packet.flags = pkt.flags
    
    return 0


def marm_error(res):
    if res != libmarm.MARM_RESULT_OK:
        if cpython.exc.PyErr_Occurred() != NULL:
            raise
        raise MARMError(res)


# libmarm functions wrappers

cpdef object generate_audio(
        object file,
        const char* encoder_name,
        int header=1,
        int raw=0,
        int duration=10,
        int bit_rate=96000,
        int sample_rate=48000):
    cdef int res = libmarm.MARM_RESULT_OK
    cdef libmarm.marm_ctx_t ctx
    cdef libmarm.marm_gen_a_t a
    
    try:
        # context
        ctx.log = marm_log_cb
        ctx.write = marm_write_cb
        ctx.seek = marm_seek_cb
        ctx.abort = marm_abort_cb

        # context
        a.ctx = &ctx
        a.file = <void *>file
        a.encoder_name = encoder_name
        a.bit_rate = bit_rate
        a.sample_rate = sample_rate
        res = libmarm.marm_gen_a_open(&a);
        marm_error(res)
        
        # generate
        if header and not raw:
            res = libmarm.marm_gen_a_header(&a)
            marm_error(res)
        res = libmarm.marm_gen_a(&a, duration, raw);
        marm_error(res)
    finally:
        libmarm.marm_gen_a_close(&a)


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
    cdef libmarm.marm_gen_v_t v
    
    try:
        # context
        ctx.log = marm_log_cb
        ctx.write = marm_write_cb
        ctx.seek = marm_seek_cb
        ctx.abort = marm_abort_cb
        
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
        const char *format_name=NULL):
    cdef int res = libmarm.MARM_RESULT_OK
    cdef libmarm.marm_ctx_t ctx
    cdef libmarm.marm_mux_a_t a
    cdef int has_a = a_packets is not None
    cdef libmarm.marm_mux_v_t v
    cdef int has_v = v_packets is not None
    cdef libmarm.marm_mux_t m
    
    try:
        # context
        ctx.log = marm_log_cb
#        ctx.log = NULL
        ctx.next_packet = marm_next_packet_cb
        ctx.write = marm_write_cb
        ctx.seek = marm_seek_cb
        ctx.abort = marm_abort_cb
    
        # audio
        if has_a:
            a.ctx = &ctx
            a.packets = <void *>a_packets
            a.encoder_name = a_profile['encoder_name']
            a.bit_rate = a_profile['bit_rate']
            a.sample_rate = a_profile['sample_rate']
            if 'time_base' in a_profile:
                a.time_base.num = a_profile['time_base'][0]
                a.time_base.den = a_profile['time_base'][1]
            else:
                a.time_base.num = 1
                a.time_base.den = a.sample_rate
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
            v.bit_rate = v_profile['bit_rate']
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
        m.ctx = &ctx
        m.file = <void *>file
        m.flags = libmarm.MARM_MUX_FLAG_MONOTONIC_FILTER
        m.format_name = format_name
        m.format_extension = format_extension
        res = libmarm.marm_mux(
            &m,
            &v if has_v else NULL,
            &a if has_a else NULL
        )
        marm_error(res)
    finally:
        if has_a:
            libmarm.marm_mux_a_close(&a)
        if has_v:
            libmarm.marm_mux_v_close(&v)


cpdef object stat(object file, const char *format_name):
    cdef int res = libmarm.MARM_RESULT_OK
    cdef libmarm.marm_ctx_t ctx
    cdef libmarm.marm_stat_t s

    try:
        # context
        ctx.log = marm_log_cb
        ctx.read = marm_read_cb
        ctx.seek = marm_seek_cb
        ctx.abort = marm_abort_cb
        
        # stat
        s.ctx = &ctx
        s.file = <void *>file
        s.format_name = format_name
        s.format_extension = NULL
        s.format = NULL
        
        res = libmarm.marm_stat(&s)
        marm_error(res)
        s_obj = FormatContext.create(s.format)
        s.format = NULL  # transferred to s_obj 
    finally:
        libmarm.marm_stat_close(&s)
    
    return s_obj


# init

libavformat.av_register_all()
