#include "marm.h"

static int read(void *opaque, uint8_t *buf, int buf_size) {
    marm_stat_t *s = (marm_stat_t *)opaque;
    return s->ctx->read(s->ctx, s->file, buf, buf_size);
}

static int64_t seek(void *opaque, int64_t offset, int whence) {
    /* seek-less files size not supported */
    if (whence == AVSEEK_SIZE)
        return -1;
    marm_stat_t *s = (marm_stat_t *)opaque;
    return s->ctx->seek(s->ctx, s->file, offset, whence);
}

marm_result_t marm_stat(marm_stat_t *s) {
    int res = 0;
    unsigned char *buffer = NULL;
    int buffer_len = 4096;
    marm_ctx_t *ctx = s->ctx;

    /* format */
    s->format = avformat_alloc_context();
    if (!s->format) {
        MARM_ERROR(ctx, "could not allocate %s format context", buffer_len);
        res = -1;
        goto cleanup;
    }
    MARM_INFO(ctx, "allocated format context");

    /* i/o */
    buffer = av_malloc(buffer_len);
    if (buffer == NULL) {
        MARM_ERROR(ctx, "could not allocate %s i/o buffer", buffer_len);
        res = -1;
        goto cleanup;
    }
    MARM_INFO(ctx, "allocated buffer");
    s->format->pb = avio_alloc_context(
        buffer,
        buffer_len,
        0,
        s,
        read,
        NULL,
        seek
    );
    if (s->format->pb == NULL) {
        MARM_ERROR(ctx, "could not allocate i/o context");
        res = -1;
        goto cleanup;
    }
    buffer = NULL;
    MARM_INFO(ctx, "allocated io context");

    /* open as input */
    res = avformat_open_input(&s->format, s->format_extension, NULL, NULL);
    if (res != 0) {
        MARM_ERROR(ctx, "could not open format as input: %s", av_err2str(res));
        res = -1;
        goto cleanup;
    }
    MARM_INFO(ctx, "opened input");

cleanup:
    if  (buffer) {
        av_free(buffer);
        buffer = NULL;
    }

    if (res != MARM_RESULT_OK) {
        marm_stat_close(s);
    }

    return res;
}

void marm_stat_close(marm_stat_t *s) {
    AVIOContext *io_ctx = NULL;
    if (s->format) {
        io_ctx = s->format->pb;
        avformat_close_input(&s->format);
    }
    if (io_ctx) {
        av_freep(&io_ctx->buffer);
        av_freep(&io_ctx);
    }
}
