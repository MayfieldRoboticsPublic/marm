#include "marm.h"
#include "util.h"

// https://github.com/FFmpeg/FFmpeg/blob/6255bf3d0d2ee843ede8c0d74e4b35d2fd574b48/libavformat/mpegts.c

#define NB_PID_MAX 8192

typedef struct {
    int pid;
    int es_id;
    int last_cc;
    // ...
} MpegTSFilter;

typedef struct  {
    const AVClass *class;
    AVFormatContext *stream;
    int raw_packet_size;
    int size_stat[3];
    int size_stat_count;
    int64_t pos47_full;
    int auto_guess;
    int mpeg2ts_compute_pcr;
    int fix_teletext_pts;
    int64_t cur_pcr;
    int pcr_incr;
    int stop_parse;
    AVPacket *pkt;
    int64_t last_pos;
    int skip_changes;
    int skip_clear;
    int scan_all_pmts;
    int resync_size;
    unsigned int nb_prg;
    struct Program *prg;
    int8_t crc_validity[NB_PID_MAX];
    MpegTSFilter *pids[NB_PID_MAX];
    int current_pid;
} MpegTSContext;

marm_result_t marm_scan(
    marm_ctx_t *ctx,
    void *in_file,
    const char *in_format_name,
    const char *in_format_extension,
    marm_mpegts_cc_t *mpegts_ccs,
    int *nb_mpegts_cc,
    int max_nb_mpegts_cc) {

    int ret = 0, done = 0, i, j;
    marm_result_t res = MARM_RESULT_OK;
    AVPacket pkt = {0};
    unsigned char *buffer = NULL;
    int buffer_len = 4096;

    AVInputFormat *i_fmt = NULL;
    AVFormatContext *i_fmtctx = NULL;
    AVStream *i_st = NULL;
    file_ctx_t i_filectx = { .ctx = ctx, .file = in_file };

    MpegTSContext *mpegts;

    // in format context
    i_fmtctx  = avformat_alloc_context();
    if (!i_fmtctx) {
        MARM_ERROR(ctx, "could not allocate input context");
        res = MARM_RESULT_MEMORY_ERROR;
        goto cleanup;
    }

    // in i/o context
    buffer = av_malloc(buffer_len);
    if (buffer == NULL) {
        MARM_ERROR(ctx, "could not allocate %d i/o buffer", buffer_len);
        res = MARM_RESULT_MEMORY_ERROR;
        goto cleanup;
    }
    i_fmtctx->pb = avio_alloc_context(
        buffer,
        buffer_len,
        0,
        &i_filectx,
        file_read,
        NULL,
        file_seek
    );
    if (i_fmtctx->pb == NULL) {
        MARM_ERROR(ctx, "could not allocate i/o context");
        res = MARM_RESULT_MEMORY_ERROR;
        goto cleanup;
    }
    buffer = NULL;

    // open input
    if (in_format_name) {
        i_fmt = av_find_input_format(in_format_name);
        if (!i_fmt) {
            MARM_ERROR(ctx, "no format w/ short name %s", in_format_name);
            res = -1;
            goto cleanup;
        }
    }
    ret = avformat_open_input(&i_fmtctx, in_format_extension, i_fmt, NULL);
    if (ret < 0) {
        MARM_ERROR(ctx, "could not open input: %d - %s", ret, av_err2str(ret));
        res = -1;
        goto cleanup;
    }

    // packets
    while (!done) {
        // read from in
        ret = av_read_frame(i_fmtctx, &pkt);
        if (ret < 0)
            break;
        i_st  = i_fmtctx->streams[pkt.stream_index];
        MARM_LOG_PACKET(ctx, MARM_LOG_LEVEL_DEBUG, "in ", &pkt, &i_st->time_base);
        av_free_packet(&pkt);
    }

    if (mpegts_ccs) {
        // FIXME: uses private libav* data, is there a public way?
        mpegts = i_fmtctx->priv_data;
        for (i = 0, j = 0; i < NB_PID_MAX; i += 1) {
            if (!mpegts->pids[i])
                continue;
            if (j >= max_nb_mpegts_cc) {
                MARM_INFO(ctx, "skipping pid %d w/ last cc %d (%d >= %d)", mpegts->pids[i]->pid, mpegts->pids[i]->last_cc, j, max_nb_mpegts_cc);
            } else {
                MARM_DEBUG(ctx, "pid %d w/ last cc %d (%d/%d)", mpegts->pids[i]->pid, mpegts->pids[i]->last_cc, j, max_nb_mpegts_cc);
                mpegts_ccs[j].pid = mpegts->pids[i]->pid;
                mpegts_ccs[j].cc = mpegts->pids[i]->last_cc;
            }
            j += 1;
        }
        *nb_mpegts_cc = j < max_nb_mpegts_cc ? j : max_nb_mpegts_cc;
    }

cleanup:
    av_free_packet(&pkt);
    if (buffer)
        av_freep(&buffer);
    if (i_fmtctx)
        avformat_close_input(&i_fmtctx);

    return res;
}
