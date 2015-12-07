#include "marm.h"
#include "mpegts.h"
#include "util.h"

typedef struct segment_s {
    marm_ctx_t *ctx;
    AVFormatContext *ifctx;
    int ref_stream_index;
    AVStream *ref_stream;
    int ref_stream_is_video;
    const char *tpl;
    const char *format_name;
    float time;
    float time_delta;
    int64_t interval;
    int64_t prev_pts;
    marm_mpegts_cc_t *mpegts_ccs;
    int nb_mpegts_cc;
    AVDictionary *opts;
    char *file;
    size_t max_file_len;
    int nb;
    AVFormatContext *ofctx;
} segment_t;

static void segment_free(segment_t *seg) {
    // free out format context
    if (seg->ofctx) {
        avformat_free_context(seg->ofctx);
        seg->ofctx = NULL;
    }

    // free file name buffer
    if (seg->file) {
        free(seg->file);
        seg->file = NULL;
    }

    if (seg->opts) {
        av_dict_free(&seg->opts);
    }
}

static marm_result_t segment_init(segment_t *seg, AVDictionary *opts) {
    int ret = 0, i;
    marm_result_t res = MARM_RESULT_OK;
    AVStream *ist, *ost;

    // copy opts
    if (opts) {
        av_dict_copy(&seg->opts, opts, 0);
    }

    // allocate file name buffer
    seg->max_file_len = strlen(seg->tpl) + 32;
    seg->file = malloc(seg->max_file_len);
    if (!seg->file) {
        MARM_ERROR(seg->ctx, "could not allocate file name buffer %d", seg->max_file_len);
        res = MARM_RESULT_MEMORY_ERROR;
        goto error;
    }
    memset(seg->file, 0, seg->max_file_len);

    // allocate out format context
    ret = avformat_alloc_output_context2(&seg->ofctx, NULL, seg->format_name, seg->file);
    if (ret < 0) {
        MARM_ERROR(seg->ctx, "could not allocate output context: %d - %s", ret, av_err2str(ret));
        res = MARM_RESULT_MEMORY_ERROR;
        goto cleanup;
    }

    // copy streams from input to output
    for (i = 0; i < seg->ifctx->nb_streams; i++) {
       ist = seg->ifctx->streams[i];
       ost = avformat_new_stream(seg->ofctx, ist->codec->codec);
       if (!ost) {
           MARM_ERROR(seg->ctx, "could not allocate output stream");
           res = MARM_RESULT_MEMORY_ERROR;
           goto cleanup;
       }
       ost->time_base = ist->time_base;
       ret = avcodec_copy_context(ost->codec, ist->codec);
       if (ret < 0) {
           MARM_ERROR(seg->ctx, "failed to copy codec context: %d - %s", ret, av_err2str(ret));
           res = -1;
           goto cleanup;
       }
       ost->codec->codec_tag = 0;
       if (seg->ofctx->oformat->flags & AVFMT_GLOBALHEADER)
           ost->codec->flags |= CODEC_FLAG_GLOBAL_HEADER;
    }

    // select reference stream to use for "time-to-split" decision
    if (seg->ref_stream_index == -1) {
        // TODO: smarter auto selection
        seg->ref_stream_index = 0;
    }
    seg->ref_stream = seg->ifctx->streams[seg->ref_stream_index];
    seg->ref_stream_is_video = seg->ref_stream->codec->codec_type == AVMEDIA_TYPE_VIDEO;

    // calculate segment interval in reference stream timebase
    seg->interval = ((seg->time - seg->time_delta) * seg->ref_stream->time_base.den ) / seg->ref_stream->time_base.num;
    MARM_INFO(
        seg->ctx,
        "using interval=%"PRId64" from time=%0.6f - time_delta=%0.6f w/ time_base=%"PRId64"/%"PRId64"",
        seg->interval,
        seg->time,
        seg->time_delta,
        seg->ref_stream->time_base.num, seg->ref_stream->time_base.den
    );

    goto cleanup;

error:
    segment_free(seg);

cleanup:

    return res;
}

static marm_result_t segment_open(segment_t *seg) {
    marm_result_t res = MARM_RESULT_OK;
    int ret = 0;

    // open out file
    if (snprintf(seg->file, seg->max_file_len, seg->tpl, seg->nb) >= seg->max_file_len) {
        MARM_ERROR(seg->ctx, "could not format file for \"%s\" w/ #%d", seg->tpl, seg->nb);
        res = MARM_RESULT_BAD_VALUE;
        goto cleanup;
    }
    MARM_INFO(seg->ctx, "opening segment #%d as \"%s\"", seg->nb, seg->file);
    ret = avio_open(&seg->ofctx->pb, seg->file, AVIO_FLAG_WRITE);
    if (ret < 0) {
        MARM_ERROR(seg->ctx, "could not open file \"%s\": %d - %s", seg->file, ret, av_err2str(ret));
        res = MARM_RESULT_BAD_VALUE;
        goto cleanup;
    }

    if (seg->nb == 0) {
        // write header
        ret = avformat_write_header(seg->ofctx, &seg->opts);
        if (ret < 0) {
            MARM_ERROR(seg->ctx, "could not write header: %d - %s", ret, av_err2str(ret));
            res = MARM_RESULT_WRITE_FAILED;
            goto cleanup;
        }

        // reset mpegts continuity counters
        if (seg->mpegts_ccs) {
            reset_mpegts_ccs(seg->ctx, seg->ofctx, seg->mpegts_ccs, seg->nb_mpegts_cc);
        }
    }

    seg->prev_pts = AV_NOPTS_VALUE;

cleanup:

    return res;
}

static marm_result_t segment_close(segment_t *seg, int last) {
    marm_result_t res = MARM_RESULT_OK;
    int ret = 0;

    MARM_INFO(seg->ctx, "closing segment #%d: last - %d", seg->nb, last);

    if (last) {
        // write trailer
        ret = av_write_trailer(seg->ofctx);
        if (ret != 0) {
            MARM_ERROR(seg->ctx, "could not write trailer: %d - %s", res, av_err2str(ret));
            res = -1;
            goto cleanup;
        }
    } else {
        // flush packets
        ret = av_interleaved_write_frame(seg->ofctx, NULL);
        if (ret < 0) {
            MARM_ERROR(seg->ctx, "could not flush interleave queues: %d - %s", res, av_err2str(ret));
            goto cleanup;
        }
    }

    // close file
    ret = avio_closep(&seg->ofctx->pb);
    if (ret != 0) {
        MARM_ERROR(seg->ctx, "could not close file: %d - %s", res, av_err2str(ret));
        res = -1;
        goto cleanup;
    }

    // next number
    seg->nb +=1;

cleanup:

    return res;
}

static int segment_at_split(segment_t *seg, AVPacket *pkt) {
    // not our reference
    if (pkt->stream_index != seg->ref_stream_index)
        return 0;

    // first one
    if (seg->prev_pts == AV_NOPTS_VALUE) {
        seg->prev_pts = pkt->pts;
        return 0;
    }

    // our reference is video and this is *not* a keyframe
    if (seg->ref_stream_is_video && !(pkt->flags & AV_PKT_FLAG_KEY))
        return 0;

    MARM_DEBUG(
        seg->ctx,
        "split check segment #%d at: pts=%"PRId64", prev_pts=%"PRId64", interval=%"PRId64"",
        seg->nb, pkt->pts, seg->prev_pts, seg->interval
    );

    return pkt->pts - seg->prev_pts >= seg->interval;
}

static marm_result_t segment_split(segment_t *seg, AVPacket *pkt) {
    marm_result_t res = MARM_RESULT_OK;

    MARM_INFO(
        seg->ctx,
        "splitting segment #%d at: pts=%"PRId64", prev_pts=%"PRId64", delta=%"PRId64", interval=%"PRId64"",
        seg->nb, pkt->pts, seg->prev_pts, seg->interval
    );

    res = segment_close(seg, 0);
    if (res != 0) {
        return res;
    }

    res = segment_open(seg);
    if (res != 0) {
        return res;
    }
    seg->prev_pts = pkt->pts;

    return res;
}

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
    AVDictionary *opts) {

    int ret = 0;
    marm_result_t res = MARM_RESULT_OK;
    AVPacket pkt;
    unsigned char *buffer = NULL;
    int buffer_len = 4096;
    segment_t seg = {0};
    AVFormatContext *ifctx = NULL;
    file_ctx_t ifilectx = { .ctx = ctx, .file = in_file };
    AVInputFormat *i_fmt = NULL;
    AVStream *ist, *ost;

    // in format context
    ifctx  = avformat_alloc_context();
    if (!ifctx) {
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
    ifctx->pb = avio_alloc_context(
        buffer,
        buffer_len,
        0,
        &ifilectx,
        file_read,
        NULL,
        file_seek
    );
    if (ifctx->pb == NULL) {
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
    ret = avformat_open_input(&ifctx, in_format_extension, i_fmt, NULL);
    if (ret < 0) {
        MARM_ERROR(ctx, "could not open input: %d - %s", ret, av_err2str(ret));
        res = -1;
        goto cleanup;
    }
    ret = avformat_find_stream_info(ifctx, 0);
    if (ret < 0) {
        MARM_ERROR(ctx, "could not find stream info: %d - %s", ret, av_err2str(ret));
        res = -1;
        goto cleanup;
    }

    // setup and open first segment
    seg.ctx = ctx;
    seg.ifctx = ifctx;
    seg.ref_stream_index = -1;
    seg.tpl = out_file_template;
    seg.time = time;
    seg.time_delta = time_delta;
    seg.format_name = out_format_name;
    seg.mpegts_ccs = mpegts_ccs;
    seg.nb_mpegts_cc = nb_mpegts_cc;
    res = segment_init(&seg, opts);
    if (res != 0) {
        goto cleanup;
    }
    res = segment_open(&seg);
    if (res != 0) {
        goto cleanup;
    }

    // segment ...
    while (1) {
        // read from in
        ret = av_read_frame(ifctx, &pkt);
        if (ret < 0)
            break;
        ret = av_dup_packet(&pkt);
        if (ret < 0) {
            MARM_ERROR(ctx, "failed to dup packet: %d - %s", ret, av_err2str(ret));
            res = -1;
            goto cleanup;
        }
        ist  = ifctx->streams[pkt.stream_index];
        ost = seg.ofctx->streams[pkt.stream_index];
        MARM_LOG_PACKET(ctx, MARM_LOG_LEVEL_DEBUG, "in ", &pkt, &ist->time_base);

        // prepare it for out
        pkt.pts = av_rescale_q_rnd(pkt.pts, ist->time_base, ost->time_base, AV_ROUND_NEAR_INF|AV_ROUND_PASS_MINMAX);
        pkt.dts = av_rescale_q_rnd(pkt.dts, ist->time_base, ost->time_base, AV_ROUND_NEAR_INF|AV_ROUND_PASS_MINMAX);
        pkt.duration = av_rescale_q(pkt.duration, ist->time_base, ost->time_base);
        pkt.pos = -1;
        MARM_LOG_PACKET(ctx, MARM_LOG_LEVEL_DEBUG, "out ", &pkt, &ist->time_base);

        // move to next segment
        if (segment_at_split(&seg, &pkt)) {
            res = segment_split(&seg, &pkt);
            if (res != 0) {
                goto cleanup;
            }
        }

        // write to out to current segment
        ret = av_interleaved_write_frame(seg.ofctx, &pkt);
        av_free_packet(&pkt);
        if (ret < 0) {
            MARM_ERROR(ctx, "failed to write frame: %d - %s", ret, av_err2str(ret));
            res = MARM_RESULT_WRITE_FAILED;
            goto cleanup;
        }
    }

    // finalize
    segment_close(&seg, 1);

cleanup:
    segment_free(&seg);
    if (buffer) {
        av_freep(&buffer);
    }
    if (ifctx) {
        avformat_close_input(&ifctx);
    }

    return res;
}
