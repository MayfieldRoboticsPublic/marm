#ifndef MARM_H
#define MARM_H

#include <libavcodec/avcodec.h>
#include <libavformat/avformat.h>
#include <libavutil/avassert.h>
#include <libavutil/timestamp.h>
#include <libswresample/swresample.h>


#define MARM_RESULT_OK 0

/**
 *
 */
typedef void (*marm_write_t)(void *p, const void *data, size_t size);

/**
 *
 */
typedef size_t (*marm_read_t)(void *p, void *data, size_t size);

/**
 *
 */
typedef long (*marm_seek_t)(void *p, long offset, int whence);

/**
 *
 */
typedef struct marm_io_s {
    void *p;
    marm_read_t read;
    marm_write_t write;
    marm_seek_t seek;
} marm_io_t;

/**
 *
 */
typedef void (*marm_log_t)(void *p, int level, const char*, ...);

#define MARM_LOG(ctx, level, format, ...) ctx->log ? ctx->log(ctx->log_p, level, format, ##__VA_ARGS__) : 0;

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


/**
 *
 */
typedef struct marm_gen_v_s {
    void *log_p;
    marm_log_t log;
    marm_io_t io;
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
 *
 */
int marm_gen_v_open(marm_gen_v_t *ctx);

/**
 *
 */
void marm_gen_v_close(marm_gen_v_t *ctx);

/**
 *
 */
void marm_gen_v_header(marm_gen_v_t *ctx);

/**
 *
 */
int marm_gen_v(marm_gen_v_t *ctx, int64_t dur, int raw);

/**
 *
 */
typedef struct marm_gen_a_s {
    marm_log_t log;
    void *log_p;
    marm_io_t io;
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
 *
 */
int marm_gen_a_open(marm_gen_a_t *ctx);

/**
 *
 */
void marm_gen_a_close(marm_gen_a_t *ctx);


/**
 *
 */
void marm_gen_a_header(marm_gen_a_t *ctx);

/**
 *
 */
int marm_gen_a(marm_gen_a_t* a, int64_t dur, int raw);

/**
 *
 */
typedef struct marm_mux_v_s {
    marm_log_t log;
    void *log_p;
    void *read_packet_p;
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
 *
 */
int marm_mux_v_open(marm_mux_v_t *v);

/**
 *
 */
void marm_mux_v_close(marm_mux_v_t *v);

/**
 *
 */
typedef struct marm_mux_a_s {
    marm_log_t log;
    void *log_p;
    void *read_packet_p;
    const char *encoder_name;
    int bit_rate;
    int sample_rate;
    AVRational time_base;
    AVCodec *codec;
    AVStream *st;
} marm_mux_a_t;

/**
 *
 */
int marm_mux_a_open(marm_mux_a_t *s);

/**
 *
 */
void marm_mux_a_close(marm_mux_a_t *a);

/**
 *
 */
typedef int (*marm_read_packet_t)(void *p, AVPacket *packet);

/**
 *
 */
typedef struct marm_mux_s {
    marm_log_t log;
    void *log_p;
    marm_read_packet_t read_packet;
    marm_io_t io;
    const char *format_name;
    const char *format_extension;
} marm_mux_t;

/**
 * Muxes video and audio streams.
 */
int marm_mux(marm_mux_t *ctx, marm_mux_v_t *v, marm_mux_a_t *a);

/**
 * Stat context.
 */
typedef struct marm_stat_s {
    marm_log_t log;
    void *log_p;
    marm_io_t io;
    const char *format_name;
    const char *format_extension;
    AVFormatContext *format;
} marm_stat_t;

/**
 * Determines and opens format from stat context.
 */
int marm_stat(marm_stat_t *ctx);

/**
 * Frees resources associated w/ stat context.
 */
void marm_stat_close(marm_stat_t *ctx);

#endif /* MARM_H */
