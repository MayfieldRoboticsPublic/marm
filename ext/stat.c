#include "marm.h"

static int read_packet(void *opaque, uint8_t *buf, int buf_size) {
    marm_stat_t *ctx = (marm_stat_t *)opaque;
    return ctx->io.read(ctx->io.p, buf, buf_size);
}

static int64_t seek(void *opaque, int64_t offset, int whence) {
    /* seek-less files size not supported */
    if (whence == AVSEEK_SIZE)
        return -1;
    marm_stat_t *ctx = (marm_stat_t *)opaque;
    return ctx->io.seek(ctx->io.p, offset, whence);
}

int marm_stat(marm_stat_t *ctx) {
    int res = 0;
    unsigned char *buffer = NULL;
    int buffer_len = 4096;

    /* format */
    ctx->format = avformat_alloc_context();
    if (!ctx->format) {
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
    ctx->format->pb = avio_alloc_context(
        buffer,
        buffer_len,
        0,
        ctx,
        read_packet,
        NULL,
        seek
    );
    if (ctx->format->pb == NULL) {
        MARM_ERROR(ctx, "could not allocate i/o context");
        res = -1;
        goto cleanup;
    }
    buffer = NULL;
    MARM_INFO(ctx, "allocated io context");

    /* open as input */
    res = avformat_open_input(&ctx->format, ctx->format_extension, NULL, NULL);
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
        marm_stat_close(ctx);
    }

    return res;
}

void marm_stat_close(marm_stat_t *ctx) {
    if (ctx->format) {
        avformat_close_input(&ctx->format);
    }
}
