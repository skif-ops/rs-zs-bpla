#ifndef BSP_NOR_H
#define BSP_NOR_H
/* W25Q512JV on OCTOSPI1 (port 1: PE10 CLK, PE11 NCS, PE12..PE15 IO0..IO3, AF10), driven in indirect
   1-1-1 mode as the zs_nor_port_t command executor. Quad I/O comes with the archive work; the record
   stores of B3 only need single-line commands. */
#include "zs_nor.h"
#include <stdbool.h>

/* Initialises OCTOSPI1 and fills `nor` (geometry = W25Q512JV, 4-byte addressing). */
bool bsp_nor_init(zs_nor_t *nor);

#endif
