#ifndef ZS_FFT_H
#define ZS_FFT_H
#include <stddef.h>
#include <stdbool.h>
typedef struct { float re; float im; } zs_complex_t;
bool zs_fft_radix2(zs_complex_t *x, size_t n);
bool zs_ifft_radix2(zs_complex_t *x, size_t n);
#endif
