from libc.stdint cimport uint8_t, int64_t

from libavutil cimport AVFrame, AVRational, AVDictionary, AVMediaType

cdef extern from 'libavcodec/avcodec.h':

    struct AVCodec:

        const char *name
        const char *long_name
        AVMediaType type

    struct AVCodecContext:
    
        pass

    struct AVPacket:
    
        int64_t pts
        int64_t dts
        uint8_t *data
        int size
        int stream_index
        int flags

    AVCodec *avcodec_find_encoder_by_name(const char *name)

    AVCodecContext *avcodec_alloc_context3(const AVCodec *codec)

    void avcodec_free_context(AVCodecContext **avctx)

    int avcodec_open2(AVCodecContext *avctx, const AVCodec *codec, AVDictionary **options)

    void av_init_packet(AVPacket *pkt)

    int av_new_packet(AVPacket *pkt, int size)

    void av_shrink_packet(AVPacket *pkt, int size)

    int av_grow_packet(AVPacket *pkt, int grow_by)
    
    void av_free_packet(AVPacket *pkt)

    void av_packet_rescale_ts(AVPacket *pkt, AVRational tb_src, AVRational tb_dst)

    int avcodec_encode_audio2(AVCodecContext *avctx, AVPacket *avpkt, const AVFrame *frame, int *got_packet_ptr)

    int avcodec_encode_video2(AVCodecContext *avctx, AVPacket *avpkt, const AVFrame *frame, int *got_packet_ptr)
    
    AVCodec *av_codec_next(const AVCodec *c)
