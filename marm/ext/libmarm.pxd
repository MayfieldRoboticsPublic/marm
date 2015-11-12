from libc.stdint cimport int64_t, uint64_t

cimport libavcodec
cimport libavformat
cimport libavutil

cdef extern from 'marm.h':

    # results

    ctypedef int marm_result_t

    int MARM_RESULT_OK
    int MARM_RESULT_ABORTED
    int MARM_RESULT_WRITE_FAILED

    # logging

    int MARM_LOG_LEVEL_DEBUG
    int MARM_LOG_LEVEL_INFO
    int MARM_LOG_LEVEL_WARN
    int MARM_LOG_LEVEL_ERROR

    # platform

    ctypedef void (*marm_log_t)(marm_ctx_s *ctx, int level, const char *format, ...) except *

    ctypedef int (*marm_abort_t)(marm_ctx_s *ctx) except *

    ctypedef long (*marm_read_t)(marm_ctx_s *ctx, void *file, void *data, size_t size) except? - 1

    ctypedef int (*marm_write_t)(marm_ctx_s *ctx, void *file, const void *data, size_t size) except? - 1

    ctypedef long (*marm_seek_t)(marm_ctx_s *ctx, void *file, long offset, int whence) except? - 1

    ctypedef int (*marm_next_packet_t)(marm_ctx_s *ctx, void *packets, libavcodec.AVPacket *packet) except? - 1

    int MARM_PACKET_FILTER_KEEP
    int MARM_PACKET_FILTER_DROP
    int MARM_PACKET_FILTER_KEEP_ALL
    int MARM_PACKET_FILTER_DROP_ALL

    ctypedef int (*marm_filter_packet_t)(marm_ctx_s *ctx, void *filter, libavcodec.AVPacket *packet) except? - 1

    struct marm_ctx_s:

        marm_log_t log
        marm_abort_t abort
        marm_read_t read
        marm_write_t write
        marm_seek_t seek
        marm_next_packet_t next_packet
        marm_filter_packet_t filter_packet
        void *err

    ctypedef marm_ctx_s marm_ctx_t

    # mpegts

    struct marm_mpegts_cc_s:

        int pid
        int cc

    ctypedef marm_mpegts_cc_s marm_mpegts_cc_t

    # gen

    struct marm_gen_v_s:

        marm_ctx_t *ctx
        void *file
        const char *encoder_name
        libavutil.AVPixelFormat pix_fmt
        int width
        int height
        int bit_rate
        int frame_rate

    ctypedef marm_gen_v_s marm_gen_v_t

    marm_result_t marm_gen_v_open(marm_gen_v_t *v)

    marm_result_t marm_gen_v_header(marm_gen_v_t *v)

    void marm_gen_v_close(marm_gen_v_t *v)

    marm_result_t marm_gen_v(marm_gen_v_t *v, int dur, int raw)

    struct marm_gen_a_s:

        const char *encoder_name;
        int bit_rate;
        int sample_rate;
        uint64_t channel_layout;
        libavutil.AVRational time_base;

    ctypedef marm_gen_a_s marm_gen_a_t

    marm_result_t marm_gen_a_open(marm_ctx_t *ctx, marm_gen_a_t *p)

    marm_result_t marm_gen_a_header(
        marm_ctx_t *ctx,
        void *file,
        marm_gen_a_t *p)

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
        int raw)

    void marm_gen_a_close(marm_gen_a_t *a)

    # mux

    struct marm_mux_v_s:

        marm_ctx_t *ctx
        void *packets
        const char *encoder_name
        libavutil.AVPixelFormat pix_fmt
        int width
        int height
        int bit_rate
        int frame_rate
        libavutil.AVRational time_base

    ctypedef marm_mux_v_s marm_mux_v_t

    marm_result_t marm_mux_v_open(marm_mux_v_t *v)

    void marm_mux_v_close(marm_mux_v_t *v)

    struct marm_mux_a_s:

        marm_ctx_t *ctx
        void *packets
        const char *encoder_name
        int bit_rate
        int sample_rate
        uint64_t channel_layout
        int initial_padding
        libavutil.AVRational time_base

    ctypedef marm_mux_a_s marm_mux_a_t

    marm_result_t marm_mux_a_open(marm_mux_a_t *a)

    void marm_mux_a_close(marm_mux_a_t *a)

    int MARM_MUX_FLAG_MONOTONIC_FILTER

    marm_result_t marm_mux(
        marm_ctx_t *ctx,
        void *file,
        int flags,
        const char *format_name,
        const char *format_extension,
        marm_mux_v_t *v,
        marm_mux_a_t *a) except *

    # remux

    marm_result_t marm_remux(
        marm_ctx_t *ctx,
        void *out_file,
        const char *out_format_name,
        const char *out_format_extension,
        void *in_file,
        const char *in_format_name,
        const char *in_format_extension,
        void *filter,
        marm_mpegts_cc_t *mpegts_ccs,
        int nb_mpegts_ccs,
        int64_t *offset_pts,
        int nb_offset_pts,
        marm_mpegts_cc_t *mpegts_next_ccs,
        int *nb_mpegts_next_cc,
        int max_nb_mpegts_next_cc,
        libavutil.AVDictionary *opts) except *

    # scan

    marm_result_t marm_scan(
        marm_ctx_t *ctx,
        void *in_file,
        const char *in_format_name,
        const char *in_format_extension,
        marm_mpegts_cc_t *mpegts_ccs,
        int *nb_mpegts_cc,
        int max_nb_mpegts_cc) except *

    # segment
    
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
        libavutil.AVDictionary *opts_arg) except *
