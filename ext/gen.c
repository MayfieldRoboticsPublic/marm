#include <libavutil/opt.h>

#include "marm.h"


/* video */


static int fill_video_frame(marm_gen_v_t *ctx) {
    int res, x, y, pts = ctx->pts;
    AVFrame *frame = ctx->frame;

    // take ownership of frame
    res = av_frame_make_writable(frame);
    if (res < 0) {
        MARM_ERROR(ctx, "could not make frame writeable: %s", av_err2str(res));
        return -1;
    }

    // y
    for (y = 0; y < ctx->height; y++) {
        for (x = 0; x < ctx->width; x++) {
            frame->data[0][y * frame->linesize[0] + x] = x + y + pts * 3;
        }
    }

    // cb and cr
    for (y = 0; y < ctx->height / 2; y++) {
        for (x = 0; x < ctx->width / 2; x++) {
            frame->data[1][y * frame->linesize[1] + x] = 128 + y + pts * 2;
            frame->data[2][y * frame->linesize[2] + x] = 64 + x + pts * 5;
        }
    }

    frame->pts = ctx->pts;

    return 0;
}


int marm_gen_v_open(marm_gen_v_t *ctx) {
    int res = 0;

    // codec
    ctx->codec = avcodec_find_encoder_by_name(ctx->encoder_name);
    if (ctx->codec == NULL) {
        MARM_ERROR(ctx, "could not find encoder codec for \"%s\"", ctx->encoder_name);
        res = -1;
        goto cleanup;
    }

    // codec context
    ctx->codec_ctx = avcodec_alloc_context3(ctx->codec);
    if (ctx->codec_ctx == NULL) {
        MARM_ERROR(ctx, "could not alloc codec context");
        res = -1;
        goto cleanup;
    }
    ctx->codec_ctx->bit_rate = ctx->bit_rate;
    ctx->codec_ctx->width = ctx->width;
    ctx->codec_ctx->height = ctx->height;
    ctx->codec_ctx->time_base = (AVRational ) { 1, ctx->frame_rate };
    ctx->codec_ctx->gop_size = 12; // emit one intra frame every twelve frames at most
    ctx->codec_ctx->pix_fmt = ctx->pix_fmt;
    if (ctx->codec_ctx->codec_id == AV_CODEC_ID_MPEG2VIDEO) {
        // just for testing, we also add B frames
        ctx->codec_ctx->max_b_frames = 2;
    }
    if (ctx->codec_ctx->codec_id == AV_CODEC_ID_MPEG1VIDEO) {
        // needed to avoid using macroblocks in which some coeffs overflow.
        // this does not happen with normal video, it just happens here as
        // the motion of the chroma plane does not match the luma plane.
        ctx->codec_ctx->mb_decision = 2;
    }
    res = avcodec_open2(ctx->codec_ctx, ctx->codec, NULL);
    if (res < 0) {
        MARM_ERROR(ctx, "could not open video codec: %s", av_err2str(res));
        res = -1;
        goto cleanup;
    }

    // frame
    ctx->frame = av_frame_alloc();
    if (!ctx->frame) {
        MARM_ERROR(ctx, "could not allocate frame");
        res = -1;
        goto cleanup;
    }
    ctx->frame->format = ctx->pix_fmt;
    ctx->frame->width = ctx->width;
    ctx->frame->height = ctx->height;
    res = av_frame_get_buffer(ctx->frame, 32);
    if (res < 0) {
        MARM_ERROR(ctx, "could not get frame buffers: %s", av_err2str(res));
        res = -1;
        goto cleanup;
    }

    ctx->pts = 0;

cleanup:
    if (res < 0) {
        marm_gen_v_close(ctx);
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

void marm_gen_v_header(marm_gen_v_t *ctx) {
    const char *type = "video";
    uint8_t type_len = strlen("video");
    uint8_t encoder_name_len = strlen(ctx->encoder_name);

    ctx->io.write(ctx->io.p, &type_len, sizeof(type_len));
    ctx->io.write(ctx->io.p, type, type_len);
    ctx->io.write(ctx->io.p, &encoder_name_len, sizeof(encoder_name_len));
    ctx->io.write(ctx->io.p, ctx->encoder_name, encoder_name_len);
    ctx->io.write(ctx->io.p, &ctx->pix_fmt, sizeof(ctx->pix_fmt));
    ctx->io.write(ctx->io.p, &ctx->width, sizeof(ctx->width));
    ctx->io.write(ctx->io.p, &ctx->height, sizeof(ctx->height));
    ctx->io.write(ctx->io.p, &ctx->bit_rate, sizeof(ctx->bit_rate));
    ctx->io.write(ctx->io.p, &ctx->frame_rate, sizeof(ctx->frame_rate));
}

int marm_gen_v(marm_gen_v_t* ctx, int64_t dur, int data_only) {
    int res = 0;
    int got_packet = 0;
    AVFrame *frame = ctx->frame;
    AVRational tb = ctx->codec_ctx->time_base;
    AVCodecContext *codec_ctx = ctx->codec_ctx;

    // fill and encode
    while (1) {
        // done?
        if (av_compare_ts(ctx->pts, tb, dur, (AVRational ) { 1, 1 }) >= 0) {
            break;
        }

        // generate frame
        fill_video_frame(ctx);
        ctx->pts += 1;

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
            ctx->io.write(ctx->io.p, &pkt.pts, sizeof(pkt.pts));
            ctx->io.write(ctx->io.p, &pkt.flags, sizeof(pkt.flags));
            ctx->io.write(ctx->io.p, &pkt.size, sizeof(pkt.size));
        }
        ctx->io.write(ctx->io.p, pkt.data, pkt.size);
    }

cleanup:

    return res;
}

/* audio */

static void fill_audio_frame(marm_gen_a_t *ctx) {
    int j, i, v;
    int16_t *d = (int16_t *) ctx->src_frame->data[0];

    for (j = 0; j < ctx->src_frame->nb_samples; j++) {
        v = (int) (sin(ctx->t) * 10000);
        for (i = 0; i < ctx->codec_ctx->channels; i++)
            *d++ = v;
        ctx->t += ctx->t_inc;
        ctx->t_inc += ctx->t_inc2;
    }
    ctx->src_frame->pts = ctx->pts;
}

void marm_gen_a_close(marm_gen_a_t *ctx) {
   if (ctx->src_frame) {
       av_frame_free(&ctx->src_frame);
   }

   if (ctx->res_frame) {
      av_frame_free(&ctx->res_frame);
  }

   if (ctx->codec_ctx) {
       avcodec_free_context(&ctx->codec_ctx);
   }

   if (ctx->swr_ctx) {
       swr_close(ctx->swr_ctx);
       swr_free(&ctx->swr_ctx);
   }
}

int marm_gen_a_open(marm_gen_a_t *ctx) {
    int res = 0, i, nb_samples;

    // codec
    ctx->codec = avcodec_find_encoder_by_name(ctx->encoder_name);
    if (ctx->codec == NULL) {
        MARM_ERROR(ctx, "could not find codec for \"%s\"", ctx->encoder_name);
        res = 0;
        goto cleanup;
    }

    // codec context
    ctx->codec_ctx = avcodec_alloc_context3(ctx->codec);
    if (ctx->codec_ctx == NULL) {
        MARM_ERROR(ctx, "could not allocate codec context");
        res = -1;
        goto cleanup;
    }
    ctx->codec_ctx->sample_fmt = ctx->codec->sample_fmts ? ctx->codec->sample_fmts[0] : AV_SAMPLE_FMT_FLTP;
    ctx->codec_ctx->bit_rate = ctx->bit_rate;
    ctx->codec_ctx->sample_rate = ctx->sample_rate;
    ctx->codec_ctx->time_base = (AVRational ) { 1, ctx->sample_rate };
    if (ctx->codec->supported_samplerates) {
        ctx->codec_ctx->sample_rate = ctx->codec->supported_samplerates[0];
        for (i = 0; ctx->codec->supported_samplerates[i]; i++) {
            if (ctx->codec->supported_samplerates[i] == ctx->sample_rate)
                ctx->codec_ctx->sample_rate = ctx->sample_rate;
        }
    }
    ctx->codec_ctx->channels = av_get_channel_layout_nb_channels(ctx->codec_ctx->channel_layout);
    ctx->codec_ctx->channel_layout = AV_CH_LAYOUT_STEREO;
    if (ctx->codec->channel_layouts) {
        ctx->codec_ctx->channel_layout = ctx->codec->channel_layouts[0];
        for (i = 0; ctx->codec->channel_layouts[i]; i++) {
            if (ctx->codec->channel_layouts[i] == AV_CH_LAYOUT_STEREO)
                ctx->codec_ctx->channel_layout = AV_CH_LAYOUT_STEREO;
        }
    }
    ctx->codec_ctx->channels = av_get_channel_layout_nb_channels(ctx->codec_ctx->channel_layout);
    res = avcodec_open2(ctx->codec_ctx, ctx->codec, NULL);
    if (res < 0) {
        MARM_ERROR(ctx, "could not open audio codec: %s", av_err2str(res));
        res = -1;
        goto cleanup;
    }

    // number of samples
    if (ctx->codec->capabilities & CODEC_CAP_VARIABLE_FRAME_SIZE)
        nb_samples = 10000;
    else
        nb_samples = ctx->codec_ctx->frame_size;

    // source frame
    ctx->src_frame = av_frame_alloc();
    if (!ctx->src_frame) {
        MARM_ERROR(ctx, "could not allocate source frame");
        res = -1;
        goto cleanup;
    }
    ctx->src_frame->format = AV_SAMPLE_FMT_S16;
    ctx->src_frame->channel_layout = ctx->codec_ctx->channel_layout;
    ctx->src_frame->sample_rate = ctx->codec_ctx->sample_rate;

    ctx->src_frame->nb_samples = nb_samples;
    res = av_frame_get_buffer(ctx->src_frame, 0);
    if (res < 0) {
        MARM_ERROR(ctx, "could not get frame buffers: %s", av_err2str(res));
        res = -1;
        goto cleanup;
    }

    // resampled frame
    ctx->res_frame = av_frame_alloc();
    if (!ctx->res_frame) {
        MARM_ERROR(ctx, "could not allocate resampled frame");
        res = -1;
        goto cleanup;
    }
    ctx->res_frame->format = ctx->codec_ctx->sample_fmt;
    ctx->res_frame->channel_layout = ctx->codec_ctx->channel_layout;
    ctx->res_frame->sample_rate = ctx->codec_ctx->sample_rate;

    ctx->res_frame->nb_samples = nb_samples;
    res = av_frame_get_buffer(ctx->res_frame, 0);
    if (res < 0) {
        MARM_ERROR(ctx, "could not get frame buffers: %s", av_err2str(res));
        res = -1;
        goto cleanup;
    }

    // resampling
    ctx->swr_ctx = swr_alloc();
    if (!ctx->swr_ctx) {
        MARM_ERROR(ctx, "could not alloc resampling context");
        res = -1;
        goto cleanup;
    }
    av_opt_set_int(ctx->swr_ctx, "in_channel_count", ctx->codec_ctx->channels, 0);
    av_opt_set_int(ctx->swr_ctx, "in_sample_rate", ctx->codec_ctx->sample_rate, 0);
    av_opt_set_sample_fmt(ctx->swr_ctx, "in_sample_fmt", AV_SAMPLE_FMT_S16, 0);
    av_opt_set_int(ctx->swr_ctx, "out_channel_count", ctx->codec_ctx->channels, 0);
    av_opt_set_int(ctx->swr_ctx, "out_sample_rate", ctx->codec_ctx->sample_rate, 0);
    av_opt_set_sample_fmt(ctx->swr_ctx, "out_sample_fmt", ctx->codec_ctx->sample_fmt, 0);
    res = swr_init(ctx->swr_ctx);
    if (res < 0) {
        MARM_ERROR(ctx, "could not initialized resampling context: %d", res);
        res = -1;
        goto cleanup;
    }

    ctx->t = 0;
    ctx->t_inc = 2 * M_PI * 110.0 / ctx->codec_ctx->sample_rate;
    ctx->t_inc2 = 2 * M_PI * 110.0 / ctx->codec_ctx->sample_rate / ctx->codec_ctx->sample_rate;

    ctx->pts = 0;

cleanup:
    if (res < 0) {
        marm_gen_a_close(ctx);
    }

    return res;
}

void marm_gen_a_header(marm_gen_a_t *ctx) {
    const char *type = "audio";
    uint8_t type_len = strlen("audio");
    uint8_t encoder_name_len = strlen(ctx->encoder_name);

    ctx->io.write(ctx->io.p, &type_len, sizeof(type_len));
    ctx->io.write(ctx->io.p, type, type_len);
    ctx->io.write(ctx->io.p, &encoder_name_len, sizeof(encoder_name_len));
    ctx->io.write(ctx->io.p, ctx->encoder_name, encoder_name_len);
    ctx->io.write(ctx->io.p, &ctx->bit_rate, sizeof(ctx->bit_rate));
    ctx->io.write(ctx->io.p, &ctx->sample_rate, sizeof(ctx->sample_rate));
}

int marm_gen_a(marm_gen_a_t *ctx, int64_t dur, int data_only) {
    int res = 0;
    int got_packet = 0;
    int dst_nb_samples;
    int samples_count = 0;
    AVCodecContext *codec_ctx = ctx->codec_ctx;

    // fill and encode
    while (1) {
        // done?
        if (av_compare_ts(ctx->pts, codec_ctx->time_base, dur, (AVRational ) { 1, 1 }) >= 0) {
            break;
        }

        // fill source frame
        fill_audio_frame(ctx);
        ctx->pts += ctx->src_frame->nb_samples;

        // resample frame
        dst_nb_samples = av_rescale_rnd(
                swr_get_delay(ctx->swr_ctx, codec_ctx->sample_rate) + ctx->src_frame->nb_samples,
                codec_ctx->sample_rate,codec_ctx->sample_rate, AV_ROUND_UP
            );
        av_assert0(dst_nb_samples == ctx->src_frame->nb_samples);
        res = av_frame_make_writable(ctx->res_frame);
        if (res < 0) {
            MARM_ERROR(ctx, "could not make frame writeable: %s", av_err2str(res));
            res = -1;
            goto cleanup;
        }
        res = swr_convert(
                ctx->swr_ctx,
                ctx->res_frame->data, dst_nb_samples,
                (const uint8_t **) ctx->src_frame->data, ctx->src_frame->nb_samples
            );
        if (res < 0) {
            res = -1;
            goto cleanup;
        }
        ctx->res_frame->pts = av_rescale_q(
                samples_count,
                (AVRational ) { 1, codec_ctx->sample_rate },
                codec_ctx->time_base
            );
        samples_count += dst_nb_samples;

        // encode frame to packet
        AVPacket pkt = { 0 };
        av_init_packet(&pkt);
        res = avcodec_encode_audio2(codec_ctx, &pkt, ctx->res_frame, &got_packet);
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
            ctx->io.write(ctx->io.p, &pkt.pts, sizeof(pkt.pts));
            ctx->io.write(ctx->io.p, &pkt.flags, sizeof(pkt.flags));
            ctx->io.write(ctx->io.p, &pkt.size, sizeof(pkt.size));
        }
        ctx->io.write(ctx->io.p, pkt.data, pkt.size);
    }

cleanup:

    return res;
}
