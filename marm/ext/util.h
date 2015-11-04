#ifndef UTIL_H
#define UTIL_H

#include "marm.h"

typedef struct file_ctx_s {
    marm_ctx_t *ctx;
    void *file;
} file_ctx_t;

int file_read(void *opaque, uint8_t *buf, int buf_size);

int file_write(void *opaque, uint8_t *buf, int buf_size);

int64_t file_seek(void *opaque, int64_t offset, int whence);

#endif
