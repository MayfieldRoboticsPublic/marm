#ifndef MPEGTS_H
#define MPEGTS_H

#include "marm.h"

void load_mpegts_ccs(
        marm_ctx_t *ctx,
        marm_mpegts_cc_t *ccs,
        int *nb_cc,
        int max_nb_cc,
        AVFormatContext *fmtctx);

void reset_mpegts_ccs(
        marm_ctx_t *ctx,
        AVFormatContext *fmtctx,
        marm_mpegts_cc_t *ccs,
        int nb_cc);

#endif
