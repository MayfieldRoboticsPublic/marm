#ifndef MARM_H
#define MARM_H

#include <libavcodec/avcodec.h>
#include <libavformat/avformat.h>
#include <libavutil/avassert.h>
#include <libavutil/timestamp.h>
#include <libswresample/swresample.h>


/* results */

#define MARM_RESULT_OK              0
#define MARM_RESULT_ABORTED         1
#define MARM_RESULT_WRITE_FAILED    2

typedef int marm_result_t;

/* loggging */

#define MARM_LOG(ctx, level, format, ...) ctx->log ? ctx->log(ctx, level, format, ##__VA_ARGS__) : 0;

#define MARM_LOG_LEVEL_DEBUG    10
#define MARM_LOG_LEVEL_INFO     20
#define MARM_LOG_LEVEL_WARN     30
#define MARM_LOG_LEVEL_ERROR    40

#define MARM_DEBUG(ctx, format, ...)    MARM_LOG(ctx, MARM_LOG_LEVEL_DEBUG, format, ##__VA_ARGS__)
#define MARM_INFO(ctx, format, ...)     MARM_LOG(ctx, MARM_LOG_LEVEL_INFO, format, ##__VA_ARGS__)
#define MARM_WARN(ctx, format, ...)     MARM_LOG(ctx, MARM_LOG_LEVEL_WARN, format, ##__VA_ARGS__)
#define MARM_ERROR(ctx, format, ...)    MARM_LOG(ctx, MARM_LOG_LEVEL_ERROR, format, ##__VA_ARGS__)

#define MARM_LOG_PACKET(ctx, level, pkt, tb) \
    MARM_LOG( \
        ctx, \
        level, \
        "pts:%s pts_time:%s dts:%s dts_time:%s duration:%s duration_time:%s stream_index:%d size:%d flags:%04x", \
        av_ts2str((pkt)->pts), av_ts2timestr((pkt)->pts, tb), \
        av_ts2str((pkt)->dts), av_ts2timestr((pkt)->dts, tb), \
        av_ts2str((pkt)->duration), av_ts2timestr((pkt)->duration, tb), \
        (pkt)->stream_index, \
        (pkt)->size, \
        (pkt)->flags \
    )

typedef struct marm_ctx_s marm_ctx_t;

/**
 * Log callback.
 */
typedef void (*marm_log_t)(marm_ctx_t *ctx, int level, const char*, ...);

/**
 * Abort callback.
 */
typedef int (*marm_abort_t)(marm_ctx_t *ctx);

/**
 * File write callback.
 */
typedef int (*marm_write_t)(marm_ctx_t *ctx, void *file, const void *data, size_t size);

/**
 * File read callback.
 */
typedef long (*marm_read_t)(marm_ctx_t *ctx, void *file, void *data, size_t size);

/**
 * File seek callback.
 */
typedef long (*marm_seek_t)(marm_ctx_t *ctx, void *file, long offset, int whence);

/**
 * Next packet callback.
 */
typedef int (*marm_next_packet_t)(marm_ctx_t *ctx, void *packets, AVPacket *packet);

/**
 * Platform (logging, file i/o, etc) context.
 */
typedef struct marm_ctx_s {
    marm_log_t log;
    marm_abort_t abort;
    marm_read_t read;
    marm_write_t write;
    marm_seek_t seek;
    marm_next_packet_t next_packet;
} marm_ctx_t;

/**
 * Video generation context.
 */
typedef struct marm_gen_v_s {
    marm_ctx_t *ctx;
    void *file;
    const char *encoder_name;
    enum AVPixelFormat pix_fmt;
    int width;
    int height;
    int bit_rate;
    int frame_rate;
    AVCodec *codec;
    AVCodecContext *codec_ctx;
    AVFrame *frame;
    int64_t pts;
} marm_gen_v_t;

/**
 * Initializes video generation resources.
 */
marm_result_t marm_gen_v_open(marm_gen_v_t *ctx);

/**
 * Frees video generation resources.
 */
void marm_gen_v_close(marm_gen_v_t *ctx);

/**
 * Writes video profile information used for generation.
 */
marm_result_t marm_gen_v_header(marm_gen_v_t *ctx);

/**
 * Generates and writes encoded video packets.
 */
marm_result_t marm_gen_v(marm_gen_v_t *ctx, int64_t dur, int raw);

/**
 * Audio generation context.
 */
typedef struct marm_gen_a_s {
    marm_ctx_t *ctx;
    void *file;
    const char *encoder_name;
    int bit_rate;
    int sample_rate;
    float t;
    float t_inc;
    float t_inc2;
    AVFrame *src_frame;
    AVFrame *res_frame;
    SwrContext *swr_ctx;
    AVCodec *codec;
    AVCodecContext *codec_ctx;
    int64_t pts;
} marm_gen_a_t;

/**
 * Initializes audio generation resources.
 */
marm_result_t marm_gen_a_open(marm_gen_a_t *a);

/**
 * Frees audio generation resources.
 */
void marm_gen_a_close(marm_gen_a_t *a);

/**
 * Writes audio profile information used for generation.
 */
marm_result_t marm_gen_a_header(marm_gen_a_t *a);

/**
 * Generates and writes encoded audio packets.
 */
marm_result_t marm_gen_a(marm_gen_a_t* a, int64_t dur, int raw);

/**
 * Video stream to be muxed.
 */
typedef struct marm_mux_v_s {
    marm_ctx_t *ctx;
    void *packets;
    const char *encoder_name;
    enum AVPixelFormat pix_fmt;
    int width;
    int height;
    int bit_rate;
    int frame_rate;
    AVRational time_base;
    AVCodec *codec;
    AVStream *st;
} marm_mux_v_t;

/**
 * Initializes video stream for muxing.
 */
marm_result_t marm_mux_v_open(marm_mux_v_t *v);

/**
 * Releases resources allocated for video stream.
 */
void marm_mux_v_close(marm_mux_v_t *v);

/**
 * Audio stream to be muxed.
 */
typedef struct marm_mux_a_s {
    marm_ctx_t *ctx;
    void *packets;
    const char *encoder_name;
    int bit_rate;
    int sample_rate;
    AVRational time_base;
    AVCodec *codec;
    AVStream *st;
} marm_mux_a_t;

/**
 * Initialize audio stream for muxing.
 */
marm_result_t marm_mux_a_open(marm_mux_a_t *s);

/**
 * Frees audio stream resources.
 */
void marm_mux_a_close(marm_mux_a_t *a);

#define MARM_MUX_FLAG_MONOTONIC_FILTER 1 << 0   /* Drop packets w/ non-monotonically increasing timestamp */

/**
 * Mux context.
 */
typedef struct marm_mux_s {
    marm_ctx_t *ctx;
    void *file;
    int flags;
    const char *format_name;
    const char *format_extension;
} marm_mux_t;

/**
 * Mux video and audio streams.
 */
marm_result_t marm_mux(marm_mux_t *ctx, marm_mux_v_t *v, marm_mux_a_t *a);

/**
 * Container stat context.
 */
typedef struct marm_stat_s {
    marm_ctx_t *ctx;
    void *file;
    const char *format_name;
    const char *format_extension;
    AVFormatContext *format;
} marm_stat_t;

/**
 * Determines container format.
 */
marm_result_t marm_stat(marm_stat_t *s);

/**
 * Frees stat context resources.
 */
void marm_stat_close(marm_stat_t *s);

#endif /* MARM_H */
