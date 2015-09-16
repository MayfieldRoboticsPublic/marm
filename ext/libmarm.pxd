cimport libavcodec
cimport libavformat
cimport libavutil

cdef extern from 'marm.h':

    # errors

    int MARM_RESULT_OK
    
    # logging
    
    ctypedef void (*marm_log_t)(void *p, int level, const char *format, ...);
    
    int MARM_LOG_LEVEL_DEBUG
    int MARM_LOG_LEVEL_INFO
    int MARM_LOG_LEVEL_WARN
    int MARM_LOG_LEVEL_ERROR
    
    # io

    ctypedef size_t (*marm_read_t)(void *p, void *data, size_t size)
        
    ctypedef void (*marm_write_t)(void *p, const void *data, size_t size)
    
    ctypedef long (*marm_seek_t)(void *p, long offset, int whence)
    
    struct marm_io_s:
    
        void *p
        marm_read_t read
        marm_write_t write
        marm_seek_t seek
    
    # gen
    
    struct marm_gen_v_s:
    
        marm_log_t log
        void *log_p
        marm_io_s io
        const char *encoder_name
        libavutil.AVPixelFormat pix_fmt
        int width
        int height
        int bit_rate
        int frame_rate
    
    int marm_gen_v_open(marm_gen_v_s *ctx)
    
    void marm_gen_v_header(marm_gen_v_s *ctx)
    
    void marm_gen_v_close(marm_gen_v_s *ctx)
    
    int marm_gen_v(marm_gen_v_s *ctx, int dur, int raw)
    
    struct marm_gen_a_s:
    
        marm_log_t log
        void *log_p
        marm_io_s io
        const char *encoder_name
        int bit_rate
        int sample_rate

    int marm_gen_a_open(marm_gen_a_s *ctx)
    
    void marm_gen_a_header(marm_gen_a_s *ctx)
    
    int marm_gen_a(marm_gen_a_s *ctx, int dur, int raw)
    
    void marm_gen_a_close(marm_gen_a_s *ctx)
    
    # mux
    
    struct marm_mux_v_s:
    
        marm_log_t log
        void *read_packet_p
        const char *encoder_name
        libavutil.AVPixelFormat pix_fmt
        int width
        int height
        int bit_rate
        int frame_rate
        libavutil.AVRational time_base

    int marm_mux_v_open(marm_mux_v_s *v)
    
    void marm_mux_v_close(marm_mux_v_s *v)

    struct marm_mux_a_s:
    
        marm_log_t log
        void *read_packet_p
        const char *encoder_name
        int bit_rate
        int sample_rate
        libavutil.AVRational time_base
    
    int marm_mux_a_open(marm_mux_a_s *a)

    void marm_mux_a_close(marm_mux_a_s *a)
    
    ctypedef int (*marm_read_packet_t)(void *p, libavcodec.AVPacket *packet)
    
    struct marm_mux_s:
        
        marm_log_t log
        void *log_p
        marm_io_s io
        marm_read_packet_t read_packet
        const char *format_name
        const char *format_extension
    
    int marm_mux(marm_mux_s *ctx, marm_mux_v_s *v, marm_mux_a_s *a)
    
    # mux
    
    struct marm_stat_s:
    
        marm_log_t log
        void *log_p
        marm_io_s io
        const char *format_name
        const char *format_extension
        libavformat.AVFormatContext *format

    int marm_stat(marm_stat_s *ctx)

    void marm_stat_close(marm_stat_s *ctx)
