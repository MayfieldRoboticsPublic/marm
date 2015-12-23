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
#define MARM_RESULT_MEMORY_ERROR    3
#define MARM_RESULT_BAD_VALUE       4

typedef int marm_result_t;

/* logging */

#define MARM_LOG(ctx, level, format, ...) ctx->log ? ctx->log(ctx, level, format, ##__VA_ARGS__) : 0;

#define MARM_LOG_LEVEL_DEBUG    10
#define MARM_LOG_LEVEL_INFO     20
#define MARM_LOG_LEVEL_WARN     30
#define MARM_LOG_LEVEL_ERROR    40

#define MARM_DEBUG(ctx, format, ...)    MARM_LOG(ctx, MARM_LOG_LEVEL_DEBUG, format, ##__VA_ARGS__)
#define MARM_INFO(ctx, format, ...)     MARM_LOG(ctx, MARM_LOG_LEVEL_INFO, format, ##__VA_ARGS__)
#define MARM_WARN(ctx, format, ...)     MARM_LOG(ctx, MARM_LOG_LEVEL_WARN, format, ##__VA_ARGS__)
#define MARM_ERROR(ctx, format, ...)    MARM_LOG(ctx, MARM_LOG_LEVEL_ERROR, format, ##__VA_ARGS__)

#define MARM_LOG_PACKET(ctx, level, prefix, pkt, tb) \
    MARM_LOG( \
        ctx, \
        level, \
        prefix \
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

#define MARM_PACKET_FILTER_KEEP 0
#define MARM_PACKET_FILTER_DROP 1
#define MARM_PACKET_FILTER_KEEP_ALL 2
#define MARM_PACKET_FILTER_DROP_ALL 3

/**
 * Filter packet callback.
 */
typedef int (*marm_filter_packet_t)(marm_ctx_t *ctx, void *filter, AVPacket *packet);

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
    marm_filter_packet_t filter_packet;
} marm_ctx_t;

#define MARM_MPEGTS_PAT_PID  0x0000
#define MARM_MPEGTS_SDT_PID  0x0011

/**
 * MPEGTS continuity counter.
 */
typedef struct marm_mpegts_cc_s {
    int pid;
    int cc;
} marm_mpegts_cc_t;

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
    float frame_rate;
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
    const char *encoder_name;
    int bit_rate;
    int sample_rate;
    uint64_t channel_layout;
    AVCodec *codec;
    AVCodecContext *codec_ctx;
    AVRational time_base;
} marm_gen_a_t;

/**
 * Initializes audio generation resources.
 */
marm_result_t marm_gen_a_open(marm_ctx_t *ctx, marm_gen_a_t *a);

/**
 * Frees audio generation resources.
 */
void marm_gen_a_close(marm_gen_a_t *a);

/**
 * Writes audio profile information used for generation.
 */
marm_result_t marm_gen_a_header(marm_ctx_t *ctx, void *file, marm_gen_a_t *p);

/**
 * Generates and writes encoded audio packets.
 */
marm_result_t marm_gen_a(
    marm_ctx_t *ctx,
    void *file,
    int *nb_samples,
    int *nb_frames,
    marm_gen_a_t* p,
    const char *type,
    int64_t dur,
    int samples,
    int64_t offset_ts,
    int raw);

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
    float frame_rate;
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
    uint64_t channel_layout;
    AVRational time_base;
    int initial_padding;
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
 * Mux streams into a container.
 */
marm_result_t marm_mux(
    marm_ctx_t *ctx,
    void *file,
    int flags,
    const char *format_name, const char *format_extension,
    marm_mux_v_t *v,
    marm_mux_a_t *a,
    AVDictionary *opts);

/**
 * Re-mux from one container into another.
 */
marm_result_t marm_remux(
    marm_ctx_t *ctx,
    void *out_file,
    const char *out_format_name,
    const char *out_format_extension,
    void *in_file,
    const char *in_format_name,
    const char *in_format_extension,
    void *filter,
    marm_mpegts_cc_t *mpegts_ccs,
    int nb_mpegts_cc,
    int64_t *offset_pts,
    int nb_offset_pts,
    AVDictionary *opts);

/**
 * Scan container.
 */
marm_result_t marm_scan(
    marm_ctx_t *ctx,
    void *in_file,
    const char *in_format_name,
    const char *in_format_extension,
    marm_mpegts_cc_t *mpegts_ccs,
    int *nb_mpegts_cc,
    int max_nb_mpegts_cc);

/**
 * Segment container.
 */
marm_result_t marm_segment(
    marm_ctx_t *ctx,
    const char *out_file_template,
    const char *out_format_name,
    void *in_file,
    const char *in_format_name,
    const char *in_format_extension,
    float time,
    float time_delta,
    marm_mpegts_cc_t *mpegts_ccs,
    int nb_mpegts_cc,
    AVDictionary *opts_arg);

#endif /* MARM_H */
