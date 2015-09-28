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
    
    ctypedef long (*marm_read_t)(marm_ctx_s *ctx, void *file, void *data, size_t size) except? -1
        
    ctypedef int (*marm_write_t)(marm_ctx_s *ctx, void *file, const void *data, size_t size) except? -1
    
    ctypedef long (*marm_seek_t)(marm_ctx_s *ctx, void *file, long offset, int whence)  except? -1
    
    ctypedef int (*marm_next_packet_t)(marm_ctx_s *ctx, void *packets, libavcodec.AVPacket *packet)  except? -1
    
    struct marm_ctx_s:
    
        marm_log_t log
        marm_abort_t abort
        marm_read_t read
        marm_write_t write
        marm_seek_t seek
        marm_next_packet_t next_packet
        void *err
    
    ctypedef marm_ctx_s marm_ctx_t
    
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
    
        marm_ctx_t *ctx
        void *file
        const char *encoder_name
        int bit_rate
        int sample_rate

    ctypedef marm_gen_a_s marm_gen_a_t

    marm_result_t marm_gen_a_open(marm_gen_a_t *a)
    
    marm_result_t marm_gen_a_header(marm_gen_a_t *a)
    
    marm_result_t marm_gen_a(marm_gen_a_t *a, int dur, int raw)
    
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
        libavutil.AVRational time_base
    
    ctypedef marm_mux_a_s marm_mux_a_t
    
    marm_result_t marm_mux_a_open(marm_mux_a_t *a)

    void marm_mux_a_close(marm_mux_a_t *a)
    
    int MARM_MUX_FLAG_MONOTONIC_FILTER
    
    struct marm_mux_s:
        
        marm_ctx_t *ctx
        void *file
        int flags
        const char *format_name
        const char *format_extension
    
    ctypedef marm_mux_s marm_mux_t
    
    marm_result_t marm_mux(marm_mux_t *m, marm_mux_v_t *v, marm_mux_a_t *a) except *
    
    # stat
    
    struct marm_stat_s:
    
        marm_ctx_t *ctx
        void *file
        const char *format_name
        const char *format_extension
        libavformat.AVFormatContext *format
    
    ctypedef marm_stat_s marm_stat_t

    marm_result_t marm_stat(marm_stat_t *s)

    void marm_stat_close(marm_stat_t *s)
