#ifndef BSP_MDF_H
#define BSP_MDF_H
/* MDF1 filters 0..3 <- SITF0..3 (PB1/PD6/PE7/PE4), common PDM clock CCK0 on PE9,
   one GPDMA1 channel per filter in linked-list circular mode, synchronous start by MDF TRGO.
   Callbacks feed zs_pdm_capture (blocks) and zs_pps_sync (block marks). */
#include <stdbool.h>
#include "zs_pdm_capture.h"
#include "zs_pps_sync.h"
bool bsp_mdf_init(zs_pdm_capture_t *capture, zs_pps_sync_t *pps);
bool bsp_mdf_start(void);
void bsp_mdf_stop(void);
const int32_t *const *bsp_mdf_dma_buffers(void);
uint32_t bsp_mdf_dma_errors(void);
#endif
