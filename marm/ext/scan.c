#include "marm.h"
#include "mpegts.h"
#include "util.h"

marm_result_t marm_scan(
    marm_ctx_t *ctx,
    void *in_file,
    const char *in_format_name,
    const char *in_format_extension,
    marm_mpegts_cc_t *mpegts_ccs,
    int *nb_mpegts_cc,
    int max_nb_mpegts_cc) {

    int ret = 0, done = 0;
    marm_result_t res = MARM_RESULT_OK;
    AVPacket pkt = {0};
    unsigned char *buffer = NULL;
    int buffer_len = 4096;

    AVInputFormat *i_fmt = NULL;
    AVFormatContext *i_fmtctx = NULL;
    AVStream *i_st = NULL;
    file_ctx_t i_filectx = { .ctx = ctx, .file = in_file };

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
        load_mpegts_ccs(ctx, mpegts_ccs, nb_mpegts_cc, max_nb_mpegts_cc, i_fmtctx);
    }

cleanup:
    av_free_packet(&pkt);
    if (buffer)
        av_freep(&buffer);
    if (i_fmtctx)
        avformat_close_input(&i_fmtctx);

    return res;
}
