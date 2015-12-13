#include "mpegts.h"

// https://github.com/FFmpeg/FFmpeg/blob/6255bf3d0d2ee843ede8c0d74e4b35d2fd574b48/libavformat/mpegts.c

#define NB_PID_MAX 8192

typedef struct {
    int pid;
    int es_id;
    int last_cc;
    // ...
} MpegTSFilter;

typedef struct  {
    const AVClass *class;
    AVFormatContext *stream;
    int raw_packet_size;
    int size_stat[3];
    int size_stat_count;
    int64_t pos47_full;
    int auto_guess;
    int mpeg2ts_compute_pcr;
    int fix_teletext_pts;
    int64_t cur_pcr;
    int pcr_incr;
    int stop_parse;
    AVPacket *pkt;
    int64_t last_pos;
    int skip_changes;
    int skip_clear;
    int scan_all_pmts;
    int resync_size;
    unsigned int nb_prg;
    struct Program *prg;
    int8_t crc_validity[NB_PID_MAX];
    MpegTSFilter *pids[NB_PID_MAX];
    int current_pid;
} MpegTSContext;

void load_mpegts_ccs(
        marm_ctx_t *ctx,
        marm_mpegts_cc_t *ccs,
        int *nb_cc,
        int max_nb_cc,
        AVFormatContext *fctx) {
    // FIXME: uses private libav* data, is there a public way?
    int i, j;
    MpegTSContext *mpegts = fctx->priv_data;
    for (i = 0, j = 0; i < NB_PID_MAX; i += 1) {
        if (!mpegts->pids[i])
            continue;
        if (j >= max_nb_cc) {
            MARM_INFO(
                ctx,
                "skipping pid %d w/ last cc %d (%d >= %d)",
                mpegts->pids[i]->pid, mpegts->pids[i]->last_cc, j, max_nb_cc
            ) ;
        } else {
            MARM_DEBUG(
                ctx,
                "pid %d w/ last cc %d (%d/%d)",
                mpegts->pids[i]->pid, mpegts->pids[i]->last_cc, j, max_nb_cc
            );
            ccs[j].pid = mpegts->pids[i]->pid;
            ccs[j].cc = mpegts->pids[i]->last_cc;
        }
        j += 1;
    }
    *nb_cc = j < max_nb_cc ? j : max_nb_cc;
}

// https://github.com/FFmpeg/FFmpeg/blob/6e8d856ad6d3decfabad83bc169c2e7a16a16b55/libavformat/mpegtsenc.c

typedef struct MpegTSSection {
    int pid;
    int cc;
    void (*write_packet)(struct MpegTSSection *s, const uint8_t *packet);
    void *opaque;
} MpegTSSection;

typedef struct MpegTSService {
    MpegTSSection pmt; /* MPEG2 pmt table context */
} MpegTSService;

typedef struct MpegTSWrite {
    const AVClass *av_class;
    MpegTSSection pat;          /* MPEG2 pat table */
    MpegTSSection sdt;          /* MPEG2 sdt table context */
    MpegTSService **services;
    int sdt_packet_count;
    int sdt_packet_period;
    int pat_packet_count;
    int pat_packet_period;
    int nb_services;
    // ...
} MpegTSWrite;

typedef struct MpegTSWriteStream {
    void *service;
    int pid; /* stream associated pid */
    int cc;
    // ...
} MpegTSWriteStream;


void reset_mpegts_ccs(
        marm_ctx_t *ctx,
        AVFormatContext *fctx,
        marm_mpegts_cc_t *ccs,
        int nb_cc) {
    // FIXME: this uses private libav* data, add `avformat_write_header` options?
    int i, j;
    AVStream *st;
    MpegTSWrite *mpegts = fctx->priv_data;
    MpegTSService *mpegts_svc;
    MpegTSWriteStream *mpegts_st;
    for (i = 0; i < nb_cc; i += 1) {
        // pat
        if (ccs[i].pid == MARM_MPEGTS_PAT_PID) {
            MARM_INFO(ctx, "resetting pat (pid=%d) cc %d -> %d", ccs[i].pid, mpegts->pat.cc, ccs[i].cc);
            mpegts->pat.cc = ccs[i].cc;
            continue;
        }

        // sdt
        if (ccs[i].pid == MARM_MPEGTS_SDT_PID) {
            MARM_INFO(ctx, "resetting sdt (pid=%d) cc %d -> %d", ccs[i].pid, mpegts->pat.cc, ccs[i].cc);
            mpegts->sdt.cc = ccs[i].cc;
            continue;
        }

        // pmt
        for (j = 0; j < mpegts->nb_services; j++) {
            mpegts_svc = mpegts->services[j];
            if (mpegts_svc->pmt.pid == ccs[i].pid) {
                MARM_INFO(
                    ctx,
                    "resetting pmt (pid=%d) cc %d -> %d",
                    ccs[i].pid, mpegts_svc->pmt.cc, ccs[i].cc
                );
                mpegts_svc->pmt.cc = ccs[i].cc;
                break;
            }
        }

        // pes
        for (j = 0; j < fctx->nb_streams; j++) {
            st = fctx->streams[j];
            mpegts_st = st->priv_data;
            if (mpegts_st->pid == ccs[i].pid) {
                MARM_INFO(
                    ctx,
                    "resetting pes (pid=%d) cc %d -> %d",
                    ccs[i].pid, mpegts_st->cc, ccs[i].cc
                );
                mpegts_st->cc = ccs[i].cc;
                break;
            }
        }
    }
}
