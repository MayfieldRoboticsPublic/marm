cdef extern from 'libswresample/swresample.h':

    struct SwrContext:
    
        pass
    
    SwrContext *swr_alloc(void)
    
    void swr_free(SwrContext **s)

    void swr_close(SwrContext *s)
