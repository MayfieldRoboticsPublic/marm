#include "marm.h"
#include "mpegts.h"
#include "util.h"

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
        AVDictionary *opts_arg) {

    int ret = 0, done = 0, i;
    marm_result_t res = MARM_RESULT_OK;
    AVPacket pkt;
    unsigned char *buffer = NULL;
    int buffer_len = 4096;

    AVInputFormat *i_fmt = NULL;
    AVFormatContext *i_fmtctx = NULL;
    AVStream *i_st = NULL;
    file_ctx_t i_filectx = { .ctx = ctx, .file = in_file };

    AVFormatContext *o_fmtctx = NULL;
    AVStream *o_st = NULL;
    file_ctx_t o_filectx = { .ctx = ctx, .file = out_file };

    AVDictionary *opts = NULL;
    if (opts_arg)
        av_dict_copy(&opts, opts_arg, 0);

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
    ret = avformat_find_stream_info(i_fmtctx, 0);
    if (ret < 0) {
        MARM_ERROR(ctx, "could not find stream info: %d - %s", ret, av_err2str(ret));
        res = -1;
        goto cleanup;
    }

    // out format context
    avformat_alloc_output_context2(&o_fmtctx, NULL, out_format_name, out_format_extension);
    if (!o_fmtctx) {
        MARM_ERROR(ctx, "could not allocate output contextL");
        res = MARM_RESULT_MEMORY_ERROR;
        goto cleanup;
    }

    // out i/o context
    buffer = av_malloc(buffer_len);
    if (buffer == NULL) {
        MARM_ERROR(ctx, "could not allocate %s i/o buffer", buffer_len);
        res = MARM_RESULT_MEMORY_ERROR;
        goto cleanup;
    }
    o_fmtctx->pb = avio_alloc_context(
        buffer,
        buffer_len,
        1,
        &o_filectx,
        NULL,
        file_write,
        file_seek
    );
    if (o_fmtctx->pb == NULL) {
        MARM_ERROR(ctx, "could not allocate i/o context");
        res = MARM_RESULT_MEMORY_ERROR;
        goto cleanup;
    }
    buffer = NULL;

    // copy streams from input to output
    for (i = 0; i < i_fmtctx->nb_streams; i++) {
       i_st = i_fmtctx->streams[i];
       o_st = avformat_new_stream(o_fmtctx, i_st->codec->codec);
       if (!o_st) {
           MARM_ERROR(ctx, "could not allocate output stream");
           res = MARM_RESULT_MEMORY_ERROR;
           goto cleanup;
       }
       o_st->time_base = i_st->time_base;
       ret = avcodec_copy_context(o_st->codec, i_st->codec);
       if (ret < 0) {
           MARM_ERROR(ctx, "failed to copy codec context: %d - %s", ret, av_err2str(ret));
           res = -1;
           goto cleanup;
       }
       o_st->codec->codec_tag = 0;
       if (o_fmtctx->oformat->flags & AVFMT_GLOBALHEADER)
           o_st->codec->flags |= CODEC_FLAG_GLOBAL_HEADER;
    }

    // write header
    ret = avformat_write_header(o_fmtctx, &opts);
    if (ret < 0) {
        MARM_ERROR(ctx, "could not write header: %d - %s", res, av_err2str(ret));
        res = MARM_RESULT_WRITE_FAILED;
        goto cleanup;
    }

    // reset mpegts ccs
    // NOTE: these are set by `mpegts_write_header` via `avformat_write_header`.
    if (mpegts_ccs &&
        nb_mpegts_cc != 0 &&
        strcmp(o_fmtctx->oformat->name, "mpegts") == 0) {
        reset_mpegts_ccs(ctx, o_fmtctx, mpegts_ccs, nb_mpegts_cc);
    }

    // packets
    while (!done) {
        // read from in
        ret = av_read_frame(i_fmtctx, &pkt);
        if (ret < 0)
            break;
        i_st  = i_fmtctx->streams[pkt.stream_index];
        o_st = o_fmtctx->streams[pkt.stream_index];
        MARM_LOG_PACKET(ctx, MARM_LOG_LEVEL_DEBUG, "in ", &pkt, &i_st->time_base);

        // filter
        if (filter) {
            ret = ctx->filter_packet(ctx, filter, &pkt);
            switch (ret) {
                case MARM_PACKET_FILTER_DROP:
                    av_free_packet(&pkt);
                    continue;
                case MARM_PACKET_FILTER_KEEP_ALL:
                    filter = NULL;
                    break;
                case MARM_PACKET_FILTER_DROP_ALL:
                    av_free_packet(&pkt);
                    done = 1;
                    continue;
                case MARM_PACKET_FILTER_KEEP:
                default:
                    break;
            }
        }

        // offset pts
        if (offset_pts) {
            pkt.pts += offset_pts[pkt.stream_index];
            pkt.dts += offset_pts[pkt.stream_index];
        }

        // prepare it for out
        pkt.pts = av_rescale_q_rnd(pkt.pts, i_st->time_base, o_st->time_base, AV_ROUND_NEAR_INF|AV_ROUND_PASS_MINMAX);
        pkt.dts = av_rescale_q_rnd(pkt.dts, i_st->time_base, o_st->time_base, AV_ROUND_NEAR_INF|AV_ROUND_PASS_MINMAX);
        pkt.duration = av_rescale_q(pkt.duration, i_st->time_base, o_st->time_base);
        pkt.pos = -1;
        MARM_LOG_PACKET(ctx, MARM_LOG_LEVEL_DEBUG, "out ", &pkt, &i_st->time_base);

        // write it out
        ret = av_interleaved_write_frame(o_fmtctx, &pkt);
        av_free_packet(&pkt);
        if (ret < 0) {
            MARM_ERROR(ctx, "failed to write frame: %d - %s", res, av_err2str(res));
            res = MARM_RESULT_WRITE_FAILED;
            goto cleanup;
        }
    }

    // write trailer
    res = av_write_trailer(o_fmtctx);
    if (res != 0) {
        MARM_ERROR(ctx, "could not write trailer: %d - %s", res, av_err2str(res));
        res = -1;
        goto cleanup;
    }

cleanup:
    if (opts) {
        av_dict_free(&opts);
    }
    if (buffer) {
        av_freep(&buffer);
    }
    if (i_fmtctx) {
        avformat_close_input(&i_fmtctx);
    }
    if (o_fmtctx && o_fmtctx->pb->buffer) {
        av_free(o_fmtctx->pb->buffer);
        o_fmtctx->pb->buffer = NULL;
    }

    if (o_fmtctx && o_fmtctx->pb) {
        av_free(o_fmtctx->pb);
        o_fmtctx->pb = NULL;
    }

    if (o_fmtctx) {
        avformat_free_context(o_fmtctx);
        o_fmtctx = NULL;
    }

    return res;
}
