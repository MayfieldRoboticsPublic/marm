#include "marm.h"
#include "util.h"


int marm_mux_v_open(marm_mux_v_t *v) {
    int res = 0;

    // codec
    v->codec = avcodec_find_encoder_by_name(v->encoder_name);
    if (v->codec == NULL) {
        MARM_ERROR(v->ctx, "could not find encoder codec for \"%s\"", v->encoder_name);
        res = -1;
        goto cleanup;
    }

cleanup:
    if (res != 0) {
        marm_mux_v_close(v);
    }

    return res;
}

void marm_mux_v_close(marm_mux_v_t *v) {
}

int marm_mux_a_open(marm_mux_a_t *a) {
    int res = 0;

    // codec
    a->codec = avcodec_find_encoder_by_name(a->encoder_name);
    if (a->codec == NULL) {
        MARM_ERROR(a->ctx, "could not find encoder codec for \"%s\"", a->encoder_name);
        res = -1;
        goto cleanup;
    }

cleanup:
    if (res != 0) {
        marm_mux_a_close(a);
    }

    return res;
}

void marm_mux_a_close(marm_mux_a_t *a) {
}

int marm_mux(
        marm_ctx_t *ctx,
        void *file,
        int flags,
        const char *format_name,
        const char *format_extension,
        marm_mux_v_t *v,
        marm_mux_a_t *a,
        AVDictionary *opts_arg) {
    AVFormatContext *o_ctx = NULL;
    AVOutputFormat *o_fmt = NULL;
    AVStream *v_st = NULL, *a_st = NULL;
    int res = 0, v_pkts = 0, a_pkts = 0, i;
    int64_t v_pts = INT64_MIN, a_pts = INT64_MIN;
    AVPacket v_pkt = {0}, a_pkt = {0};
    unsigned char *buffer = NULL;
    int buffer_len = 4096;
    file_ctx_t file_ctx = { .ctx = ctx, .file = file };

    AVDictionary *opts = NULL;
    if (opts_arg)
        av_dict_copy(&opts, opts_arg, 0);

    // output context
    avformat_alloc_output_context2(&o_ctx, NULL, format_name, format_extension);
    if (!o_ctx) {
        MARM_ERROR(ctx, "could not allocate output context");
        res = -1;
        goto cleanup;
    }
    o_fmt = o_ctx->oformat;

    // add video stream
    if (v) {
        // codec stream
        v_st = avformat_new_stream(o_ctx, v->codec);
        if (!v_st) {
            res = -1;
            goto cleanup;
        }

        // codec params
        v_st->codec->bit_rate = v->bit_rate;
        v_st->codec->width = v->width;
        v_st->codec->height = v->height;
        v_st->codec->gop_size = 12; // emit one intra frame every twelve frames at most
        v_st->codec->pix_fmt = v->pix_fmt;
        if (v_st->codec->codec_id == AV_CODEC_ID_MPEG2VIDEO) {
            // just for testing, we also add B frames
            v_st->codec->max_b_frames = 2;
        }
        if (v_st->codec->codec_id == AV_CODEC_ID_MPEG1VIDEO) {
            // needed to avoid using macroblocks in which some coeffs overflow.
            // this does not happen with normal video, it just happens here as
            // the motion of the chroma plane does not match the luma plane.
            v_st->codec->mb_decision = 2;
        }
        if (o_fmt->flags & AVFMT_GLOBALHEADER) {
            v_st->codec->flags |= CODEC_FLAG_GLOBAL_HEADER;
        }
        v_st->time_base = v->time_base;
        v_st->codec->time_base = v_st->time_base;

        // context for stream codec
        res = avcodec_open2(v_st->codec, v->codec, &opts);
        if (res < 0) {
            MARM_ERROR(ctx, "could not open codec: %d - %s", res, av_err2str(res));
            res = -1;
            goto cleanup;
        }

        res = av_new_packet(&v_pkt, 1024);
        if (res != 0) {
            MARM_ERROR(ctx, "could not create new packet: %d - %s", res, av_err2str(res));
            res = -1;
            goto cleanup;
        }

        v_pkts = 1;
    }

    // add audio stream
    if (a) {
        // codec stream
        a_st = avformat_new_stream(o_ctx, a->codec);
        if (!a_st) {
            res = -1;
            goto cleanup;
        }

        // codec params
        a_st->codec->sample_fmt = a->codec->sample_fmts ? a->codec->sample_fmts[0] : AV_SAMPLE_FMT_FLTP;
        a_st->codec->bit_rate = a->bit_rate;
        a_st->codec->sample_rate = a->sample_rate;
        if (a->codec->supported_samplerates) {
            a_st->codec->sample_rate = a->codec->supported_samplerates[0];
            for (i = 0; a->codec->supported_samplerates[i]; i++) {
                if (a->codec->supported_samplerates[i] == a->sample_rate)
                    a_st->codec->sample_rate = a->sample_rate;
            }
        }
        a_st->codec->channels = av_get_channel_layout_nb_channels(a_st->codec->channel_layout);
        a_st->codec->channel_layout = a->channel_layout;
        if (a->codec->channel_layouts) {
            a_st->codec->channel_layout = a->codec->channel_layouts[0];
            for (i = 0; a->codec->channel_layouts[i]; i++) {
                if (a->codec->channel_layouts[i] == a->channel_layout)
                    a_st->codec->channel_layout = a->channel_layout;
            }
        }
        a_st->codec->channels = av_get_channel_layout_nb_channels(a_st->codec->channel_layout);
        if (o_fmt->flags & AVFMT_GLOBALHEADER) {
            a_st->codec->flags |= CODEC_FLAG_GLOBAL_HEADER;
        }
        a_st->time_base = a->time_base;
        a_st->codec->time_base = a_st->time_base;

        // context for stream codec
        res = avcodec_open2(a_st->codec, a->codec, &opts);
        if (res < 0) {
            MARM_ERROR(ctx, "could not open codec: %d - %s", res, av_err2str(res));
            res = -1;
            goto cleanup;
        }

        // initial padding
        if (a->initial_padding != -1) {
            a_st->codec->initial_padding = a->initial_padding;
        }

        res = av_new_packet(&a_pkt, 1024);
        if (res != 0) {
            MARM_ERROR(ctx, "could not create new packet: %d - %s", res, av_err2str(res));
            res = -1;
            goto cleanup;
        }

        a_pkts = 1;
    }

    // i/o context
    buffer = av_malloc(buffer_len);
    if (buffer == NULL) {
        MARM_ERROR(ctx, "could not allocate %s i/o buffer", buffer_len);
        res = -1;
        goto cleanup;
    }
    o_ctx->pb = avio_alloc_context(
        buffer,
        buffer_len,
        1,
        &file_ctx,
        NULL,
        file_write,
        file_seek
    );
    if (o_ctx->pb == NULL) {
        MARM_ERROR(ctx, "could not allocate i/o context");
        res = -1;
        goto cleanup;
    }
    buffer = NULL;

    // write header
    res = avformat_write_header(o_ctx, &opts);
    if (res < 0) {
        MARM_ERROR(ctx, "could not write header: %d - %s", res, av_err2str(res));
        res = -1;
        goto cleanup;
    }

    // read first packet
    if (v_pkts && ctx->next_packet(ctx, v->packets, &v_pkt) != 0) {
        // no more
        v_pkts = 0;
    }
    if (a_pkts && ctx->next_packet(ctx, a->packets, &a_pkt) != 0) {
        // no more
        a_pkts = 0;
    }

    // write packets
    while ((v_pkts || a_pkts) && !ctx->abort(ctx)) {
        if (v_pkts && (!a_pkts || av_compare_ts(v_pkt.pts, v_st->codec->time_base, a_pkt.pts, a_st->codec->time_base) <= 0)) {
            // write video packet
            av_packet_rescale_ts(&v_pkt, v_st->codec->time_base, v_st->time_base);
            v_pkt.stream_index = v_st->index;
            MARM_LOG_PACKET(ctx, MARM_LOG_LEVEL_DEBUG, "video ", &v_pkt, &v_st->time_base);
            if ((flags & MARM_MUX_FLAG_MONOTONIC_FILTER) && v_pkt.pts <= v_pts) {
                MARM_INFO(ctx, "dropping video packet w/ non-monotonically increasing pts %"PRId64" <= %"PRId64"", v_pkt.pts, v_pts);
            } else {
                v_pts = v_pkt.pts;
                res = av_interleaved_write_frame(o_ctx, &v_pkt);
                if (res != 0) {
                    MARM_ERROR(ctx, "could not write video frame: %d - %s", res, av_err2str(res));
                    res = MARM_RESULT_WRITE_FAILED;
                    goto cleanup;
                }
                res = av_new_packet(&v_pkt, 1024);
                if (res != 0) {
                    MARM_ERROR(ctx, "could not create new packet: %d - %s", res, av_err2str(res));
                    res = -1;
                    goto cleanup;
                }
            }

            // read next video packet
            if (ctx->next_packet(ctx, v->packets, &v_pkt) != 0) {
                // no more
                v_pkts = 0;
            }
        } else if (a_pkts) {
            // write audio packet
            av_packet_rescale_ts(&a_pkt, a_st->codec->time_base, a_st->time_base);
            a_pkt.stream_index = a_st->index;
            MARM_LOG_PACKET(ctx, MARM_LOG_LEVEL_DEBUG, "audio ", &a_pkt, &a_st->time_base);
            if ((flags & MARM_MUX_FLAG_MONOTONIC_FILTER) && a_pkt.pts <= a_pts) {
                MARM_INFO(ctx, "dropping audio packet w/ non-monotonically increasing pts %"PRId64" <= %"PRId64"", a_pkt.pts, a_pts);
            } else {
                a_pts = a_pkt.pts;
                res = av_interleaved_write_frame(o_ctx, &a_pkt);
                if (res != 0) {
                    MARM_ERROR(ctx, "could not write audio frame: %d - %s", res, av_err2str(res));
                    res = MARM_RESULT_WRITE_FAILED;
                    goto cleanup;
                }
                res = av_new_packet(&a_pkt, 1024);
                if (res != 0) {
                    MARM_ERROR(ctx, "could not create new packet: %d - %s", res, av_err2str(res));
                    res = -1;
                    goto cleanup;
                }
            }

            // read next audio packet
            if (ctx->next_packet(ctx, a->packets, &a_pkt) != 0) {
                // no more
                a_pkts = 0;
            }
        }
    }
    if (ctx->abort(ctx)) {
        MARM_INFO(ctx, "aborted mux");
        res = MARM_RESULT_ABORTED;
        goto cleanup;
    }

    // write trailer
    res = av_write_trailer(o_ctx);
    if (res != 0) {
        MARM_ERROR(ctx, "could not write trailer: %d - %s", res, av_err2str(res));
        res = -1;
        goto cleanup;
    }

cleanup:
    if (opts) {
        av_dict_free(&opts);
    }

    av_free_packet(&v_pkt);
    av_free_packet(&a_pkt);

    if  (buffer) {
        av_free(buffer);
        buffer = NULL;
    }

    if (o_ctx && o_ctx->pb->buffer) {
        av_free(o_ctx->pb->buffer);
        o_ctx->pb->buffer = NULL;
    }

    if (o_ctx && o_ctx->pb) {
        av_free(o_ctx->pb);
        o_ctx->pb = NULL;
    }

    if (o_ctx) {
        avformat_free_context(o_ctx);
        o_ctx = NULL;
    }

    return res;
}

