from libavcodec cimport AVCodec, AVPacket
from libavutil cimport AVDictionary
from libc.stdint cimport int64_t

cdef extern from 'libavformat/avformat.h':

    struct AVIOContext:
    
        unsigned char *buffer
    
    struct AVStream:
    
        pass
    
    struct AVInputFormat:
    
        const char *name
        const char *long_name
        int flags
        const char *extensions
    
    struct AVOutputFormat:
    
        const char *name
        const char *long_name
        int flags
        const char *mime_type
        const char *extensions
    
    struct AVFormatContext:
    
        AVInputFormat *iformat
        AVOutputFormat *oformat
        AVIOContext *pb
        unsigned int nb_streams
        AVStream **streams
        int64_t start_time
        int64_t duration
    
    void av_register_all()
    
    int avformat_alloc_output_context2(AVFormatContext **ctx, AVOutputFormat *oformat, const char *format_name, const char *filename)
    
    void avformat_free_context(AVFormatContext *s)
    
    int avio_open(AVIOContext **s, const char *url, int flags)
    
    int avformat_write_header(AVFormatContext *s, AVDictionary **options)
    
    int av_write_trailer(AVFormatContext *s)
    
    int av_interleaved_write_frame(AVFormatContext *s, AVPacket *pkt)
    
    AVStream *avformat_new_stream(AVFormatContext *s, const AVCodec *c)
    
    AVInputFormat *av_iformat_next(AVInputFormat *f)
    
    AVOutputFormat *av_oformat_next(AVOutputFormat *f)
    
    void avformat_close_input(AVFormatContext **s)
