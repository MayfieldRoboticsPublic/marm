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
        MARM_LOG_PACKET(ctx, MARM_LOG_LEVEL_DEBUG, "video ", &pkt, &codec_ctx->time_base)

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

struct a_state_s;

typedef void (*fill_audio_frame_t)(struct a_state_s *s, marm_gen_a_t *p);

typedef struct a_state_s {
    int64_t pts;
    AVFrame *src_frame;
    AVFrame *res_frame;
    SwrContext *swr_ctx;
    fill_audio_frame_t fill_frame;
    float t;
    float t_inc;
    float t_inc2;
} a_state_t;

static void sin_audio_frame(a_state_t *s, marm_gen_a_t *p) {
    int j, i, v;
    int16_t *d = (int16_t *)s->src_frame->data[0];

    for (j = 0; j < s->src_frame->nb_samples; j++) {
        v = (int) (sin(s->t) * 10000);
        for (i = 0; i < p->codec_ctx->channels; i++)
            *d++ = v;
        s->t += s->t_inc;
        s->t_inc += s->t_inc2;
    }
    s->src_frame->pts = s->pts;
}

static void zero_audio_frame(a_state_t *s, marm_gen_a_t *p) {
    memset(
        s->src_frame->data[0],
        0,
        s->src_frame->nb_samples * p->codec_ctx->channels * sizeof(int16_t)
   );
    s->src_frame->pts = s->pts;
}

static void a_state_close(marm_ctx_t *ctx, a_state_t *s) {
    if (s->src_frame) {
        av_frame_free(&s->src_frame);
    }
    if (s->res_frame) {
        av_frame_free(&s->res_frame);
    }
    if (s->swr_ctx) {
       swr_close(s->swr_ctx);
       swr_free(&s->swr_ctx);
    }
}

static marm_result_t a_state_open(marm_ctx_t *ctx, a_state_t *s, marm_gen_a_t *p) {
    marm_result_t res = MARM_RESULT_OK;
    int nb_samples;

    // number of samples
    if (p->codec->capabilities & CODEC_CAP_VARIABLE_FRAME_SIZE)
        nb_samples = 10000;
    else
        nb_samples = p->codec_ctx->frame_size;

    // source frame
    s->src_frame = av_frame_alloc();
    if (!s->src_frame) {
        MARM_ERROR(ctx, "could not allocate source frame");
        res = -1;
        goto cleanup;
    }
    s->src_frame->format = AV_SAMPLE_FMT_S16;
    s->src_frame->channel_layout = p->codec_ctx->channel_layout;
    s->src_frame->sample_rate = p->codec_ctx->sample_rate;

    s->src_frame->nb_samples = nb_samples;
    res = av_frame_get_buffer(s->src_frame, 0);
    if (res < 0) {
        MARM_ERROR(ctx, "could not get frame buffers: %s", av_err2str(res));
        res = -1;
        goto cleanup;
    }

    // resampled frame
    s->res_frame = av_frame_alloc();
    if (!s->res_frame) {
        MARM_ERROR(ctx, "could not allocate resampled frame");
        res = -1;
        goto cleanup;
    }
    s->res_frame->format = p->codec_ctx->sample_fmt;
    s->res_frame->channel_layout = p->codec_ctx->channel_layout;
    s->res_frame->sample_rate = p->codec_ctx->sample_rate;

    s->res_frame->nb_samples = nb_samples;
    res = av_frame_get_buffer(s->res_frame, 0);
    if (res < 0) {
        MARM_ERROR(ctx, "could not get frame buffers: %s", av_err2str(res));
        res = -1;
        goto cleanup;
    }

    // resampling
    s->swr_ctx = swr_alloc();
    if (!s->swr_ctx) {
        MARM_ERROR(ctx, "could not alloc resampling context");
        res = -1;
        goto cleanup;
    }
    av_opt_set_int(s->swr_ctx, "in_channel_count", p->codec_ctx->channels, 0);
    av_opt_set_int(s->swr_ctx, "in_sample_rate", p->codec_ctx->sample_rate, 0);
    av_opt_set_sample_fmt(s->swr_ctx, "in_sample_fmt", AV_SAMPLE_FMT_S16, 0);
    av_opt_set_int(s->swr_ctx, "out_channel_count", p->codec_ctx->channels, 0);
    av_opt_set_int(s->swr_ctx, "out_sample_rate", p->codec_ctx->sample_rate, 0);
    av_opt_set_sample_fmt(s->swr_ctx, "out_sample_fmt", p->codec_ctx->sample_fmt, 0);
    res = swr_init(s->swr_ctx);
    if (res < 0) {
        MARM_ERROR(ctx, "could not initialized resampling context: %d", res);
        res = -1;
        goto cleanup;
    }

    s->pts = 0;

    s->t = 0;
    s->t_inc = 2 * M_PI * 110.0 / p->codec_ctx->sample_rate;
    s->t_inc2 = 2 * M_PI * 110.0 / p->codec_ctx->sample_rate / p->codec_ctx->sample_rate;


cleanup:
    if (res != MARM_RESULT_OK) {
        a_state_close(ctx, s);
    }

    return res;
}

marm_result_t marm_gen_a_open(marm_ctx_t *ctx, marm_gen_a_t *p) {
    int res = 0, i;

    // codec
    p->codec = avcodec_find_encoder_by_name(p->encoder_name);
    if (p->codec == NULL) {
        MARM_ERROR(ctx, "could not find codec for \"%s\"", p->encoder_name);
        res = 0;
        goto cleanup;
    }

    // codec context
    p->codec_ctx = avcodec_alloc_context3(p->codec);
    if (p->codec_ctx == NULL) {
        MARM_ERROR(ctx, "could not allocate codec context");
        res = -1;
        goto cleanup;
    }
    p->codec_ctx->sample_fmt = p->codec->sample_fmts ? p->codec->sample_fmts[0] : AV_SAMPLE_FMT_FLTP;
    p->codec_ctx->bit_rate = p->bit_rate;
    p->codec_ctx->sample_rate = p->sample_rate;
    p->codec_ctx->time_base = (AVRational ) { 1, p->sample_rate };
    if (p->codec->supported_samplerates) {
        p->codec_ctx->sample_rate = p->codec->supported_samplerates[0];
        for (i = 0; p->codec->supported_samplerates[i]; i++) {
            if (p->codec->supported_samplerates[i] == p->sample_rate)
                p->codec_ctx->sample_rate = p->sample_rate;
        }
    }
    p->codec_ctx->channels = av_get_channel_layout_nb_channels(p->codec_ctx->channel_layout);
    p->codec_ctx->channel_layout = p->channel_layout;
    if (p->codec->channel_layouts) {
        p->codec_ctx->channel_layout = p->codec->channel_layouts[0];
        for (i = 0; p->codec->channel_layouts[i]; i++) {
            if (p->codec->channel_layouts[i] == p->channel_layout)
                p->codec_ctx->channel_layout = p->channel_layout;
        }
    }
    p->codec_ctx->channels = av_get_channel_layout_nb_channels(p->codec_ctx->channel_layout);
    res = avcodec_open2(p->codec_ctx, p->codec, NULL);
    if (res < 0) {
        MARM_ERROR(ctx, "could not open audio codec: %s", av_err2str(res));
        res = -1;
        goto cleanup;
    }
    p->codec_ctx->initial_padding = 0;

cleanup:
    if (res < 0) {
        marm_gen_a_close(p);
    }

    return res;
}

void marm_gen_a_close(marm_gen_a_t *p) {
    if (p->codec_ctx) {
       avcodec_free_context(&p->codec_ctx);
    }
}

marm_result_t marm_gen_a_header(marm_ctx_t *ctx, void *file, marm_gen_a_t *p) {
    const char *type = "audio";
    uint8_t type_len = strlen("audio");
    uint8_t encoder_name_len = strlen(p->encoder_name);

    if(ctx->write(ctx, file, &type_len, sizeof(type_len)) != sizeof(type_len) ||
       ctx->write(ctx, file, type, type_len) != type_len ||
       ctx->write(ctx, file, &encoder_name_len, sizeof(encoder_name_len)) != sizeof(encoder_name_len) ||
       ctx->write(ctx, file, p->encoder_name, encoder_name_len) != encoder_name_len ||
       ctx->write(ctx, file, &p->bit_rate, sizeof(p->bit_rate)) != sizeof(p->bit_rate) ||
       ctx->write(ctx, file, &p->sample_rate, sizeof(p->sample_rate)) != sizeof(p->sample_rate) ||
       ctx->write(ctx, file, &p->channel_layout, sizeof(p->channel_layout)) != sizeof(p->channel_layout)) {
        return MARM_RESULT_WRITE_FAILED;
    }
    return MARM_RESULT_OK;
}

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
        int data_only) {
    int res = 0;
    int got_packet = 0;
    int dst_nb_samples;
    int samples_count = 0;
    AVCodecContext *codec_ctx = p->codec_ctx;
    a_state_t s = {0};
    int64_t f = 0;
    AVRational time_base = p->time_base;
    AVPacket pkt = {0};

    // state
    if (strcmp(type, "zero") == 0) {
        s.fill_frame = zero_audio_frame;
    }
    else if (strcmp(type, "sin") == 0) {
        s.fill_frame = sin_audio_frame;
    } else {
        MARM_ERROR(ctx, "invalid type \"%s\"", type);
        goto cleanup;
    }
    res = a_state_open(ctx, &s, p);
    if (res != 0) {
        goto cleanup;
    }

    // generate
    while (!ctx->abort(ctx)) {
        // done?
        if (dur > 0 && av_compare_ts(s.pts, codec_ctx->time_base, dur, (AVRational ) { 1, 1 }) >= 0) {
            break;
        }
        if (samples == 0) {
            break;
        }

        // fill source frame
        if (samples > 0) {
            if (samples < s.src_frame->nb_samples)
                s.src_frame->nb_samples = samples;
            samples -= s.src_frame->nb_samples;
        }
        s.fill_frame(&s, p);
        s.pts += s.src_frame->nb_samples;

        // resample frame
        dst_nb_samples = av_rescale_rnd(
            swr_get_delay(s.swr_ctx, codec_ctx->sample_rate) + s.src_frame->nb_samples,
            codec_ctx->sample_rate,
            codec_ctx->sample_rate,
            AV_ROUND_UP
        );
        av_assert0(dst_nb_samples == s.src_frame->nb_samples);
        res = av_frame_make_writable(s.res_frame);
        if (res < 0) {
            MARM_ERROR(ctx, "could not make frame writeable: %s", av_err2str(res));
            res = -1;
            goto cleanup;
        }
        res = swr_convert(
            s.swr_ctx,
            s.res_frame->data, dst_nb_samples,
            (const uint8_t **) s.src_frame->data, s.src_frame->nb_samples
        );
        if (res < 0) {
            res = -1;
            goto cleanup;
        }
        s.res_frame->pts = av_rescale_q(
            samples_count,
            (AVRational ) { 1, codec_ctx->sample_rate },
            codec_ctx->time_base
        );
        samples_count += dst_nb_samples;

        // encode frame to packet
        res = avcodec_encode_audio2(codec_ctx, &pkt, s.res_frame, &got_packet);
        if (res < 0) {
            res = -1;
            goto cleanup;
        }
        if (!got_packet) {
            continue;
        }
        if (pkt.pts != AV_NOPTS_VALUE)
            pkt.pts += offset_ts;
        if (pkt.dts != AV_NOPTS_VALUE)
            pkt.dts += offset_ts;
        if (time_base.den != 0) {
            av_packet_rescale_ts(&pkt, codec_ctx->time_base, time_base);
            MARM_LOG_PACKET(ctx, MARM_LOG_LEVEL_DEBUG, "audio ", &pkt, &time_base)
        } else {
            MARM_LOG_PACKET(ctx, MARM_LOG_LEVEL_DEBUG, "audio ", &pkt, &codec_ctx->time_base)
        }
        f += 1;

        // write packet
        if (!data_only) {
            if (ctx->write(ctx, file, &pkt.pts, sizeof(pkt.pts)) != sizeof(pkt.pts) ||
                ctx->write(ctx, file, &pkt.flags, sizeof(pkt.flags)) != sizeof(pkt.flags) ||
                ctx->write(ctx, file, &pkt.size, sizeof(pkt.size)) != sizeof(pkt.size)) {
                res = MARM_RESULT_WRITE_FAILED;
                goto cleanup;
            }
        }
        if (ctx->write(ctx, file, pkt.data, pkt.size) != pkt.size) {
            res = MARM_RESULT_WRITE_FAILED;
            goto cleanup;
        }
        av_free_packet(&pkt);
        av_init_packet(&pkt);
    }
    if (ctx->abort(ctx)) {
        MARM_INFO(ctx, "aborted gen_a");
        res = MARM_RESULT_ABORTED;
        goto cleanup;
    }

    // flush
    while (1) {
        // encode queued frame(s) to packet(s)
        res = avcodec_encode_audio2(codec_ctx, &pkt, NULL, &got_packet);
        if (res < 0) {
            res = -1;
            goto cleanup;
        }
        if (!got_packet) {
            break;
        }
        if (pkt.pts != AV_NOPTS_VALUE)
            pkt.pts += offset_ts;
        if (pkt.dts != AV_NOPTS_VALUE)
            pkt.dts += offset_ts;
        if (time_base.den != 0) {
            av_packet_rescale_ts(&pkt, codec_ctx->time_base, time_base);
            MARM_LOG_PACKET(ctx, MARM_LOG_LEVEL_DEBUG, "audio ", &pkt, &time_base)
        } else {
            MARM_LOG_PACKET(ctx, MARM_LOG_LEVEL_DEBUG, "audio ", &pkt, &codec_ctx->time_base)
        }
        f += 1;

        // write packet
        if (!data_only) {
            if (ctx->write(ctx, file, &pkt.pts, sizeof(pkt.pts)) != sizeof(pkt.pts) ||
                ctx->write(ctx, file, &pkt.flags, sizeof(pkt.flags)) != sizeof(pkt.flags) ||
                ctx->write(ctx, file, &pkt.size, sizeof(pkt.size)) != sizeof(pkt.size)) {
                res = MARM_RESULT_WRITE_FAILED;
                goto cleanup;
            }
        }
        if (ctx->write(ctx, file, pkt.data, pkt.size) != pkt.size) {
            res = MARM_RESULT_WRITE_FAILED;
            goto cleanup;
        }
        av_free_packet(&pkt);
        av_init_packet(&pkt);
    }

cleanup:
    av_free_packet(&pkt);

    a_state_close(ctx, &s);

    if (nb_samples)
        *nb_samples = samples_count;
    if (nb_frames)
        *nb_frames = f;

    return res;
}
