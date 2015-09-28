#include <libavutil/opt.h>

#include "marm.h"


/* video */


static int fill_video_frame(marm_gen_v_t *v) {
    int res, x, y, pts = v->pts;
    AVFrame *frame = v->frame;

    // take ownership of frame
    res = av_frame_make_writable(frame);
    if (res < 0) {
        MARM_ERROR(v->ctx, "could not make frame writeable: %s", av_err2str(res));
        return -1;
    }

    // y
    for (y = 0; y < v->height; y++) {
        for (x = 0; x < v->width; x++) {
            frame->data[0][y * frame->linesize[0] + x] = x + y + pts * 3;
        }
    }

    // cb and cr
    for (y = 0; y < v->height / 2; y++) {
        for (x = 0; x < v->width / 2; x++) {
            frame->data[1][y * frame->linesize[1] + x] = 128 + y + pts * 2;
            frame->data[2][y * frame->linesize[2] + x] = 64 + x + pts * 5;
        }
    }

    frame->pts = v->pts;

    return 0;
}


marm_result_t marm_gen_v_open(marm_gen_v_t *v) {
    int res = 0;

    // codec
    v->codec = avcodec_find_encoder_by_name(v->encoder_name);
    if (v->codec == NULL) {
        MARM_ERROR(v->ctx, "could not find encoder codec for \"%s\"", v->encoder_name);
        res = -1;
        goto cleanup;
    }

    // codec context
    v->codec_ctx = avcodec_alloc_context3(v->codec);
    if (v->codec_ctx == NULL) {
        MARM_ERROR(v->ctx, "could not alloc codec context");
        res = -1;
        goto cleanup;
    }
    v->codec_ctx->bit_rate = v->bit_rate;
    v->codec_ctx->width = v->width;
    v->codec_ctx->height = v->height;
    v->codec_ctx->time_base = (AVRational ) { 1, v->frame_rate };
    v->codec_ctx->gop_size = 12; // emit one intra frame every twelve frames at most
    v->codec_ctx->pix_fmt = v->pix_fmt;
    if (v->codec_ctx->codec_id == AV_CODEC_ID_MPEG2VIDEO) {
        // just for testing, we also add B frames
        v->codec_ctx->max_b_frames = 2;
    }
    if (v->codec_ctx->codec_id == AV_CODEC_ID_MPEG1VIDEO) {
        // needed to avoid using macroblocks in which some coeffs overflow.
        // this does not happen with normal video, it just happens here as
        // the motion of the chroma plane does not match the luma plane.
        v->codec_ctx->mb_decision = 2;
    }
    res = avcodec_open2(v->codec_ctx, v->codec, NULL);
    if (res < 0) {
        MARM_ERROR(v->ctx, "could not open video codec: %s", av_err2str(res));
        res = -1;
        goto cleanup;
    }

    // frame
    v->frame = av_frame_alloc();
    if (!v->frame) {
        MARM_ERROR(v->ctx, "could not allocate frame");
        res = -1;
        goto cleanup;
    }
    v->frame->format = v->pix_fmt;
    v->frame->width = v->width;
    v->frame->height = v->height;
    res = av_frame_get_buffer(v->frame, 32);
    if (res < 0) {
        MARM_ERROR(v->ctx, "could not get frame buffers: %s", av_err2str(res));
        res = -1;
        goto cleanup;
    }

    v->pts = 0;

cleanup:
    if (res < 0) {
        marm_gen_v_close(v);
    }

    return res;
}

void marm_gen_v_close(marm_gen_v_t *ctx) {
    if (ctx->frame) {
        av_frame_free(&ctx->frame);
        ctx->frame = NULL;
    }

    if (ctx->codec_ctx) {
        avcodec_free_context(&ctx->codec_ctx);
        ctx->codec_ctx = NULL;
    }
}

marm_result_t marm_gen_v_header(marm_gen_v_t *v) {
    const char *type = "video";
    uint8_t type_len = strlen("video");
    uint8_t encoder_name_len = strlen(v->encoder_name);
    marm_ctx_t *ctx = v->ctx;

    if (ctx->write(ctx, v->file, &type_len, sizeof(type_len)) != sizeof(type_len) ||
        ctx->write(ctx, v->file, type, type_len) != type_len ||
        ctx->write(ctx, v->file, &encoder_name_len, sizeof(encoder_name_len)) != sizeof(encoder_name_len) ||
        ctx->write(ctx, v->file, v->encoder_name, encoder_name_len) != encoder_name_len ||
        ctx->write(ctx, v->file, &v->pix_fmt, sizeof(v->pix_fmt)) != sizeof(v->pix_fmt) ||
        ctx->write(ctx, v->file, &v->width, sizeof(v->width)) != sizeof(v->width) ||
        ctx->write(ctx, v->file, &v->height, sizeof(v->height)) != sizeof(v->height) ||
        ctx->write(ctx, v->file, &v->bit_rate, sizeof(v->bit_rate)) != sizeof(v->bit_rate) ||
        ctx->write(ctx, v->file, &v->frame_rate, sizeof(v->frame_rate)) != sizeof(v->frame_rate)) {
        return MARM_RESULT_WRITE_FAILED;
    }
    return MARM_RESULT_OK;
}

marm_result_t marm_gen_v(marm_gen_v_t* v, int64_t dur, int data_only) {
    int res = 0;
    int got_packet = 0;
    marm_ctx_t *ctx = v->ctx;
    AVFrame *frame = v->frame;
    AVRational tb = v->codec_ctx->time_base;
    AVCodecContext *codec_ctx = v->codec_ctx;

    // fill and encode
    while (!ctx->abort(ctx)) {
        // done?
        if (av_compare_ts(v->pts, tb, dur, (AVRational ) { 1, 1 }) >= 0) {
            break;
        }

        // generate frame
        fill_video_frame(v);
        v->pts += 1;

        // encode frame to packet
        AVPacket pkt = { 0 };
        av_init_packet(&pkt);
        res = avcodec_encode_video2(codec_ctx, &pkt, frame, &got_packet);
        if (res < 0) {
            MARM_ERROR(ctx, "could not encode video frame: %s", av_err2str(res));
            res = -1;
            goto cleanup;
        }
        if (!got_packet) {
            continue;
        }
        MARM_LOG_PACKET(ctx, MARM_LOG_LEVEL_DEBUG, &pkt, &codec_ctx->time_base)

        // write packet
        if (!data_only) {
            if (ctx->write(ctx, v->file, &pkt.pts, sizeof(pkt.pts)) != sizeof(pkt.pts) ||
                ctx->write(ctx, v->file, &pkt.flags, sizeof(pkt.flags)) != sizeof(pkt.flags) ||
                ctx->write(ctx, v->file, &pkt.size, sizeof(pkt.size)) != sizeof(pkt.size)) {
                res = MARM_RESULT_WRITE_FAILED;
                goto cleanup;
            }
        }
        if (ctx->write(ctx, v->file, pkt.data, pkt.size) != pkt.size) {
            res = MARM_RESULT_WRITE_FAILED;
            goto cleanup;
        }
    }
    if (ctx->abort(ctx)) {
        MARM_INFO(ctx, "aborted gen_v");
        res = MARM_RESULT_ABORTED;
        goto cleanup;
    }

cleanup:

    return res;
}

/* audio */

static void fill_audio_frame(marm_gen_a_t *a) {
    int j, i, v;
    int16_t *d = (int16_t *) a->src_frame->data[0];

    for (j = 0; j < a->src_frame->nb_samples; j++) {
        v = (int) (sin(a->t) * 10000);
        for (i = 0; i < a->codec_ctx->channels; i++)
            *d++ = v;
        a->t += a->t_inc;
        a->t_inc += a->t_inc2;
    }
    a->src_frame->pts = a->pts;
}

void marm_gen_a_close(marm_gen_a_t *a) {
   if (a->src_frame) {
       av_frame_free(&a->src_frame);
   }

   if (a->res_frame) {
      av_frame_free(&a->res_frame);
  }

   if (a->codec_ctx) {
       avcodec_free_context(&a->codec_ctx);
   }

   if (a->swr_ctx) {
       swr_close(a->swr_ctx);
       swr_free(&a->swr_ctx);
   }
}

marm_result_t marm_gen_a_open(marm_gen_a_t *a) {
    int res = 0, i, nb_samples;
    marm_ctx_t *ctx = a->ctx;

    // codec
    a->codec = avcodec_find_encoder_by_name(a->encoder_name);
    if (a->codec == NULL) {
        MARM_ERROR(ctx, "could not find codec for \"%s\"", a->encoder_name);
        res = 0;
        goto cleanup;
    }

    // codec context
    a->codec_ctx = avcodec_alloc_context3(a->codec);
    if (a->codec_ctx == NULL) {
        MARM_ERROR(ctx, "could not allocate codec context");
        res = -1;
        goto cleanup;
    }
    a->codec_ctx->sample_fmt = a->codec->sample_fmts ? a->codec->sample_fmts[0] : AV_SAMPLE_FMT_FLTP;
    a->codec_ctx->bit_rate = a->bit_rate;
    a->codec_ctx->sample_rate = a->sample_rate;
    a->codec_ctx->time_base = (AVRational ) { 1, a->sample_rate };
    if (a->codec->supported_samplerates) {
        a->codec_ctx->sample_rate = a->codec->supported_samplerates[0];
        for (i = 0; a->codec->supported_samplerates[i]; i++) {
            if (a->codec->supported_samplerates[i] == a->sample_rate)
                a->codec_ctx->sample_rate = a->sample_rate;
        }
    }
    a->codec_ctx->channels = av_get_channel_layout_nb_channels(a->codec_ctx->channel_layout);
    a->codec_ctx->channel_layout = AV_CH_LAYOUT_STEREO;
    if (a->codec->channel_layouts) {
        a->codec_ctx->channel_layout = a->codec->channel_layouts[0];
        for (i = 0; a->codec->channel_layouts[i]; i++) {
            if (a->codec->channel_layouts[i] == AV_CH_LAYOUT_STEREO)
                a->codec_ctx->channel_layout = AV_CH_LAYOUT_STEREO;
        }
    }
    a->codec_ctx->channels = av_get_channel_layout_nb_channels(a->codec_ctx->channel_layout);
    res = avcodec_open2(a->codec_ctx, a->codec, NULL);
    if (res < 0) {
        MARM_ERROR(ctx, "could not open audio codec: %s", av_err2str(res));
        res = -1;
        goto cleanup;
    }

    // number of samples
    if (a->codec->capabilities & CODEC_CAP_VARIABLE_FRAME_SIZE)
        nb_samples = 10000;
    else
        nb_samples = a->codec_ctx->frame_size;

    // source frame
    a->src_frame = av_frame_alloc();
    if (!a->src_frame) {
        MARM_ERROR(ctx, "could not allocate source frame");
        res = -1;
        goto cleanup;
    }
    a->src_frame->format = AV_SAMPLE_FMT_S16;
    a->src_frame->channel_layout = a->codec_ctx->channel_layout;
    a->src_frame->sample_rate = a->codec_ctx->sample_rate;

    a->src_frame->nb_samples = nb_samples;
    res = av_frame_get_buffer(a->src_frame, 0);
    if (res < 0) {
        MARM_ERROR(ctx, "could not get frame buffers: %s", av_err2str(res));
        res = -1;
        goto cleanup;
    }

    // resampled frame
    a->res_frame = av_frame_alloc();
    if (!a->res_frame) {
        MARM_ERROR(ctx, "could not allocate resampled frame");
        res = -1;
        goto cleanup;
    }
    a->res_frame->format = a->codec_ctx->sample_fmt;
    a->res_frame->channel_layout = a->codec_ctx->channel_layout;
    a->res_frame->sample_rate = a->codec_ctx->sample_rate;

    a->res_frame->nb_samples = nb_samples;
    res = av_frame_get_buffer(a->res_frame, 0);
    if (res < 0) {
        MARM_ERROR(ctx, "could not get frame buffers: %s", av_err2str(res));
        res = -1;
        goto cleanup;
    }

    // resampling
    a->swr_ctx = swr_alloc();
    if (!a->swr_ctx) {
        MARM_ERROR(ctx, "could not alloc resampling context");
        res = -1;
        goto cleanup;
    }
    av_opt_set_int(a->swr_ctx, "in_channel_count", a->codec_ctx->channels, 0);
    av_opt_set_int(a->swr_ctx, "in_sample_rate", a->codec_ctx->sample_rate, 0);
    av_opt_set_sample_fmt(a->swr_ctx, "in_sample_fmt", AV_SAMPLE_FMT_S16, 0);
    av_opt_set_int(a->swr_ctx, "out_channel_count", a->codec_ctx->channels, 0);
    av_opt_set_int(a->swr_ctx, "out_sample_rate", a->codec_ctx->sample_rate, 0);
    av_opt_set_sample_fmt(a->swr_ctx, "out_sample_fmt", a->codec_ctx->sample_fmt, 0);
    res = swr_init(a->swr_ctx);
    if (res < 0) {
        MARM_ERROR(ctx, "could not initialized resampling context: %d", res);
        res = -1;
        goto cleanup;
    }

    a->t = 0;
    a->t_inc = 2 * M_PI * 110.0 / a->codec_ctx->sample_rate;
    a->t_inc2 = 2 * M_PI * 110.0 / a->codec_ctx->sample_rate / a->codec_ctx->sample_rate;

    a->pts = 0;

cleanup:
    if (res < 0) {
        marm_gen_a_close(a);
    }

    return res;
}

marm_result_t marm_gen_a_header(marm_gen_a_t *a) {
    const char *type = "audio";
    uint8_t type_len = strlen("audio");
    uint8_t encoder_name_len = strlen(a->encoder_name);
    marm_ctx_t *ctx = a->ctx;

    if(ctx->write(ctx, a->file, &type_len, sizeof(type_len)) != sizeof(type_len) ||
       ctx->write(ctx, a->file, type, type_len) != type_len ||
       ctx->write(ctx, a->file, &encoder_name_len, sizeof(encoder_name_len)) != sizeof(encoder_name_len) ||
       ctx->write(ctx, a->file, a->encoder_name, encoder_name_len) != encoder_name_len ||
       ctx->write(ctx, a->file, &a->bit_rate, sizeof(a->bit_rate)) != sizeof(a->bit_rate) ||
       ctx->write(ctx, a->file, &a->sample_rate, sizeof(a->sample_rate)) != sizeof(a->sample_rate))  {
        return MARM_RESULT_WRITE_FAILED;
    }
    return MARM_RESULT_OK;
}

marm_result_t marm_gen_a(marm_gen_a_t *a, int64_t dur, int data_only) {
    int res = 0;
    int got_packet = 0;
    int dst_nb_samples;
    int samples_count = 0;
    AVCodecContext *codec_ctx = a->codec_ctx;
    marm_ctx_t *ctx = a->ctx;

    // fill and encode
    while (!ctx->abort(ctx)) {
        // done?
        if (av_compare_ts(a->pts, codec_ctx->time_base, dur, (AVRational ) { 1, 1 }) >= 0) {
            break;
        }

        // fill source frame
        fill_audio_frame(a);
        a->pts += a->src_frame->nb_samples;

        // resample frame
        dst_nb_samples = av_rescale_rnd(
                swr_get_delay(
                    a->swr_ctx,
                    codec_ctx->sample_rate) + a->src_frame->nb_samples, codec_ctx->sample_rate,
                    codec_ctx->sample_rate, AV_ROUND_UP
            );
        av_assert0(dst_nb_samples == a->src_frame->nb_samples);
        res = av_frame_make_writable(a->res_frame);
        if (res < 0) {
            MARM_ERROR(ctx, "could not make frame writeable: %s", av_err2str(res));
            res = -1;
            goto cleanup;
        }
        res = swr_convert(
                a->swr_ctx,
                a->res_frame->data, dst_nb_samples,
                (const uint8_t **) a->src_frame->data, a->src_frame->nb_samples
            );
        if (res < 0) {
            res = -1;
            goto cleanup;
        }
        a->res_frame->pts = av_rescale_q(
                samples_count,
                (AVRational ) { 1, codec_ctx->sample_rate },
                codec_ctx->time_base
            );
        samples_count += dst_nb_samples;

        // encode frame to packet
        AVPacket pkt = { 0 };
        av_init_packet(&pkt);
        res = avcodec_encode_audio2(codec_ctx, &pkt, a->res_frame, &got_packet);
        if (res < 0) {
            res = -1;
            goto cleanup;
        }
        if (!got_packet) {
            continue;
        }
        MARM_LOG_PACKET(ctx, MARM_LOG_LEVEL_DEBUG, &pkt, &codec_ctx->time_base)

        // write packet
        if (!data_only) {
            if (ctx->write(ctx, a->file, &pkt.pts, sizeof(pkt.pts)) != sizeof(pkt.pts) ||
                ctx->write(ctx, a->file, &pkt.flags, sizeof(pkt.flags)) != sizeof(pkt.flags) ||
                ctx->write(ctx, a->file, &pkt.size, sizeof(pkt.size)) != sizeof(pkt.size)) {
                res = MARM_RESULT_WRITE_FAILED;
                goto cleanup;
            }
        }
        if (ctx->write(ctx, a->file, pkt.data, pkt.size) != pkt.size) {
            res = MARM_RESULT_WRITE_FAILED;
            goto cleanup;
        }
    }
    if (ctx->abort(ctx)) {
        MARM_INFO(ctx, "aborted gen_a");
        res = MARM_RESULT_ABORTED;
        goto cleanup;
    }

cleanup:

    return res;
}
