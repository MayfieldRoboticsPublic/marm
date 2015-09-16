from libc.stdint cimport uint8_t, int64_t, uint64_t
from libcx cimport va_list

cdef extern from 'libavutil/avutil.h':

    struct AVFrame:
    
        int width
        
        int height
    
        int format
    
        int key_frame

    AVFrame *av_frame_alloc()
    
    void av_frame_free(AVFrame **frame)
    
    AVFrame *av_frame_alloc()
    
    void av_frame_free(AVFrame **frame)
    
    int av_frame_get_buffer(AVFrame *frame, int align)

    int av_frame_make_writable(AVFrame *frame)
    
    struct AVRational:
    
        int num
        
        int den

    int av_compare_ts(int64_t ts_a, AVRational tb_a, int64_t ts_b, AVRational tb_b)

    struct AVDictionary:
    
        pass
    
    enum AVPixelFormat:
    
        AV_PIX_FMT_NONE = -1
        AV_PIX_FMT_YUV420P
        AV_PIX_FMT_YUYV422
    
    enum AVSampleFormat:
    
        AV_SAMPLE_FMT_NONE = -1
        AV_SAMPLE_FMT_U8
        AV_SAMPLE_FMT_S16
        AV_SAMPLE_FMT_S32
        
    enum AVMediaType:
    
        AVMEDIA_TYPE_UNKNOWN = -1
        AVMEDIA_TYPE_VIDEO
        AVMEDIA_TYPE_AUDIO
        AVMEDIA_TYPE_DATA
        AVMEDIA_TYPE_SUBTITLE
        AVMEDIA_TYPE_ATTACHMENT
        AVMEDIA_TYPE_NB

    int av_opt_set(void *obj, const char *name, const char *val, int search_flags)
    
    int av_opt_set_int(void *obj, const char *name, int64_t val, int search_flags)
    
    int av_opt_set_double(void *obj, const char *name, double val, int search_flags)
    
    int av_opt_set_q(void *obj, const char *name, AVRational  val, int search_flags)
    
    int av_opt_set_bin(void *obj, const char *name, const uint8_t *val, int size, int search_flags)
    
    int av_opt_set_image_size(void *obj, const char *name, int w, int h, int search_flags)
    
    int av_opt_set_pixel_fmt(void *obj, const char *name, AVPixelFormat fmt, int search_flags)
    
    int av_opt_set_sample_fmt(void *obj, const char *name, AVSampleFormat fmt, int search_flags)
    
    int av_opt_set_video_rate(void *obj, const char *name, AVRational val, int search_flags)
    
    int av_opt_set_channel_layout(void *obj, const char *name, int64_t ch_layout, int search_flags)

    int av_get_channel_layout_nb_channels(uint64_t channel_layout)
    
    int AV_LOG_QUIET
    int AV_LOG_PANIC
    int AV_LOG_FATAL
    int AV_LOG_ERROR
    int AV_LOG_WARNING
    int AV_LOG_INFO
    int AV_LOG_VERBOSE
    int AV_LOG_DEBUG
    int AV_LOG_TRACE
    
    void av_log_format_line(void *ptr, int level, const char *fmt, va_list vl, char *line, int line_size, int *print_prefix)

    void av_log_set_callback(void (*callback)(void *avcl, int level, const char *fmt, va_list vl))
