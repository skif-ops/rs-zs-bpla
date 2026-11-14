#ifndef BSP_RNG_H
#define BSP_RNG_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
/* Hardware RNG (HSI48 kernel clock): nonces for the B.9 session-role challenge. */
bool bsp_rng_init(void);
bool bsp_rng_fill(uint8_t *out, size_t len);   /* false when the RNG is not initialised or reports an error */
#endif
