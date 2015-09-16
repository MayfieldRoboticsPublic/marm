from libc.stdio cimport FILE


cdef extern from 'stdarg.h' nogil:

    ctypedef struct va_list:
    
        pass
    
    void va_start(va_list, void* arg)
    
    void va_copy(va_list dest, va_list src);
    
    void va_end(va_list)


cdef extern from 'stdio.h' nogil:
    
    int vsnprintf(char *str, size_t size, const char *format, va_list ap)
