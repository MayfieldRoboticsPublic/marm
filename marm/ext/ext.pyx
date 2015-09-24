import collections
import logging

cimport cpython
cimport libavcodec
cimport libavformat
cimport libavutil
from libc.stdint cimport int64_t
from libc.stdio cimport stderr
from libc.string cimport memcpy
from libcx cimport va_list, va_start, va_end, va_copy, vsnprintf
cimport libmarm


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


class Error(Exception):
    
    messages = {
    }
    
    def __init__(self, errno):
        super(Error, self).__init__(self.messages[errno])
        self.errno = errno


log = logging.getLogger('marm.ext').log


cdef void log_callback(void *obj, int level, const char *fmt, ...):
    cdef va_list vl
    cdef char[1024] msg
    cdef int log_level = logging.NOTSET
    
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
    
    log(log_level, msg)

cdef size_t read_callback(void *obj, void *data, size_t size):
    buf = (<object>obj).read(size)
    cdef size_t buf_size = cpython.PyString_Size(buf)
    memcpy(data, cpython.PyString_AsString(buf), buf_size)
    return buf_size

cdef void write_callback(void *obj, const void *data, size_t size):
    cdef buf = cpython.PyString_FromStringAndSize(<const char *>data, size)
    (<object>obj).write(buf)


cdef long seek_callback(void *obj, long offset, int whence):
    (<object>obj).seek(offset, whence)
    return (<object>obj).tell()


cpdef void generate_audio(
            object file,
            const char* encoder_name,
            int header=1,
            int raw=0,
            int duration=10,
            int bit_rate=96000,
            int sample_rate=48000
        ):
    cdef int res = libmarm.MARM_RESULT_OK
    cdef libmarm.marm_gen_a_s ctx
    
    try:
        # context
        ctx.log = log_callback
        ctx.io.p = <void *>file
        ctx.io.write = write_callback
        ctx.io.seek = seek_callback
        ctx.encoder_name = encoder_name
        ctx.bit_rate = bit_rate
        ctx.sample_rate = sample_rate
        
        # gen
        res = libmarm.marm_gen_a_open(&ctx);
        if res != libmarm.MARM_RESULT_OK:
            raise Error(res)
        if header and not raw:
            libmarm.marm_gen_a_header(&ctx)
        res = libmarm.marm_gen_a(&ctx, duration, raw);
        if res != libmarm.MARM_RESULT_OK:
            raise Error(res)
    finally:
        libmarm.marm_gen_a_close(&ctx)


cpdef void generate_video(
            object file,
            const char* encoder_name,
            int header=1,
            int raw=0,
            int duration=10,
            int pix_fmt=libavutil.AV_PIX_FMT_YUV420P,
            int width=320,
            int height=240,
            int bit_rate=400000,
            int frame_rate=25
        ):
    cdef int res = libmarm.MARM_RESULT_OK
    cdef libmarm.marm_gen_v_s ctx
    
    try:
        # context
        ctx.log = log_callback
        ctx.io.p = <void *>file
        ctx.io.write = write_callback
        ctx.io.seek = seek_callback
        ctx.encoder_name = encoder_name
        ctx.pix_fmt = <libavutil.AVPixelFormat>pix_fmt
        ctx.width = width
        ctx.height = height
        ctx.bit_rate = bit_rate
        ctx.frame_rate = frame_rate
        
        # gen
        res = libmarm.marm_gen_v_open(&ctx);
        if res != libmarm.MARM_RESULT_OK:
            raise Error(res)
        if header and not raw:
            libmarm.marm_gen_v_header(&ctx)
        res = libmarm.marm_gen_v(&ctx, duration, raw);
        if res != libmarm.MARM_RESULT_OK:
            raise Error(res)
    finally:
        libmarm.marm_gen_v_close(&ctx)


cdef int read_packet(void *obj, libavcodec.AVPacket *av_packet):
    cdef int64_t pts
    cdef int flags
    cdef object data
    cdef int size

    try:
        packet = (<object>obj).next()
    except StopIteration:
        return -1
    
    # data
    size = len(packet.data)
    if av_packet.size < size:
        libavcodec.av_grow_packet(av_packet, size - av_packet.size)
    else:
        libavcodec.av_shrink_packet(av_packet, size);
    memcpy(av_packet.data, <const char *>packet.data, size)
    
    # pts
    av_packet.pts = packet.pts
    
    # flags
    av_packet.flags = packet.flags
    
    return 0


cpdef void mux(
            object file,
            const char *format_extension,
            object a_profile,
            object a_packets,
            object v_profile,
            object v_packets,
            const char *format_name=NULL
        ):
    cdef int res = libmarm.MARM_RESULT_OK
    cdef libmarm.marm_mux_a_s a
    cdef int has_a = a_packets is not None
    cdef libmarm.marm_mux_v_s v
    cdef int has_v = v_packets is not None
    cdef libmarm.marm_mux_s ctx
    
    try:
        # audio
        if has_a:
            a.log = log_callback
            a.read_packet_p = <void *>a_packets
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
            if res != libmarm.MARM_RESULT_OK:
                raise Error(res)
        
        # video
        if has_v:
            v.log = log_callback
            v.read_packet_p = <void *>v_packets
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
            if res != libmarm.MARM_RESULT_OK:
                raise Error(res)
        
        # mux them
        ctx.log = log_callback
        ctx.read_packet = read_packet
        ctx.io.p = <void *>file
        ctx.io.write = write_callback
        ctx.io.seek = seek_callback
        ctx.format_name = format_name
        ctx.format_extension = format_extension
        res = libmarm.marm_mux(
                &ctx,
                &v if has_v else NULL,
                &a if has_a else NULL
            )
        if res != libmarm.MARM_RESULT_OK:
            raise Error(res)
    finally:
        pass
        if has_a:
            libmarm.marm_mux_a_close(&a)
        if has_v:
            libmarm.marm_mux_v_close(&v)


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
        if self.ctx != NULL:
            libavformat.avformat_close_input(&self.ctx)
        
    @staticmethod
    cdef create(libavformat.AVFormatContext *ctx    ):
        i = FormatContext()
        i.ctx = ctx
        return i

    property nb_streams:

        def __get__(self):
            return self.ctx.nb_streams
        
    property iformat:

        def __get__(self):
            return None if self.ctx.iformat == NULL else InputFormat.create(self.ctx.iformat)


cpdef object stat(object file, const char *format_name):
    cdef int res = libmarm.MARM_RESULT_OK
    cdef libmarm.marm_stat_s ctx

    ctx.log = log_callback
    ctx.io.p = <void *>file
    ctx.io.read = read_callback
    ctx.io.seek = seek_callback
    try:
        res = libmarm.marm_stat(&ctx)
        if res != libmarm.MARM_RESULT_OK:
            raise Error(res)
        s_obj = FormatContext.create(ctx.format)
        ctx.format = NULL  # transferred to s_obj 
    finally:
        libmarm.marm_stat_close(&ctx)
    return s_obj


class LibAVLoggingFilter(logging.Formatter):
    
    def filter(self, record):
        record.msg = record.msg.rstrip()
        return 1


logging.getLogger('libav*').addFilter(LibAVLoggingFilter())

av_log = logging.getLogger('libav*').log


cdef void av_log_callback(void *avcl, int level, const char *fmt, va_list vl):
    cdef char[1024] msg
    cdef int print_prefix = 1
    cdef int log_level = logging.NOTSET
    
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
    av_log(log_level, msg)


libavutil.av_log_set_callback(av_log_callback)

libavformat.av_register_all()
