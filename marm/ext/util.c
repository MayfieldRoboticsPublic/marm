#include "util.h"


int file_read(void *opaque, uint8_t *buf, int buf_size) {
    file_ctx_t *f = (file_ctx_t *)opaque;
    return f->ctx->read(f->ctx, f->file, buf, buf_size);
}

int file_write(void *opaque, uint8_t *buf, int buf_size) {
    file_ctx_t *f = (file_ctx_t *)opaque;
    return f->ctx->write(f->ctx, f->file, buf, buf_size);
}

int64_t file_seek(void *opaque, int64_t offset, int whence) {
    /* seek-less files size not supported */
    if (whence == AVSEEK_SIZE)
        return -1;
    file_ctx_t *f = (file_ctx_t *)opaque;
    return f->ctx->seek(f->ctx, f->file, offset, whence);
}
