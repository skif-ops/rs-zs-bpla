#include "bsp_mdf.h"

#include "app_config.h"
#include "bsp_tim2_pps.h"
#include "stm32u5xx_hal.h"

#include <string.h>

#define MDF_CHANNELS 4u
#define DMA_WORDS_PER_CHANNEL (2u * APP_AUDIO_BLOCK_SAMPLES)

static MDF_HandleTypeDef hmdf[MDF_CHANNELS];
static DMA_HandleTypeDef hdma[MDF_CHANNELS];
static DMA_QListTypeDef dma_queue[MDF_CHANNELS];
static DMA_NodeTypeDef dma_node[MDF_CHANNELS];
static int32_t dma_buffer[MDF_CHANNELS][DMA_WORDS_PER_CHANNEL] __attribute__((aligned(4)));
static const int32_t *const dma_buffer_ptr[MDF_CHANNELS] = {dma_buffer[0], dma_buffer[1], dma_buffer[2], dma_buffer[3]};
static zs_pdm_capture_t *g_capture;
static zs_pps_sync_t *g_pps;
static uint32_t g_dma_errors;
static uint8_t g_half_seen, g_full_seen;

static MDF_Filter_TypeDef *const filter_instance[MDF_CHANNELS] = {MDF1_Filter0, MDF1_Filter1, MDF1_Filter2, MDF1_Filter3};
static DMA_Channel_TypeDef *const dma_instance[MDF_CHANNELS] = {GPDMA1_Channel0, GPDMA1_Channel1, GPDMA1_Channel2, GPDMA1_Channel3};
static const uint32_t dma_request[MDF_CHANNELS] = {GPDMA1_REQUEST_MDF1_FLT0, GPDMA1_REQUEST_MDF1_FLT1, GPDMA1_REQUEST_MDF1_FLT2, GPDMA1_REQUEST_MDF1_FLT3};
static const uint32_t bitstream[MDF_CHANNELS] = {MDF_BITSTREAM0_RISING, MDF_BITSTREAM1_RISING, MDF_BITSTREAM2_RISING, MDF_BITSTREAM3_RISING};
static const IRQn_Type dma_irq[MDF_CHANNELS] = {GPDMA1_Channel0_IRQn, GPDMA1_Channel1_IRQn, GPDMA1_Channel2_IRQn, GPDMA1_Channel3_IRQn};

const int32_t *const *bsp_mdf_dma_buffers(void) { return dma_buffer_ptr; }
uint32_t bsp_mdf_dma_errors(void) { return g_dma_errors; }

static bool dma_channel_init(unsigned i) {
  DMA_NodeConfTypeDef node = {0};
  DMA_HandleTypeDef *h = &hdma[i];
  h->Instance = dma_instance[i];
  h->InitLinkedList.Priority = DMA_HIGH_PRIORITY;
  h->InitLinkedList.LinkStepMode = DMA_LSM_FULL_EXECUTION;
  h->InitLinkedList.LinkAllocatedPort = DMA_LINK_ALLOCATED_PORT0;
  h->InitLinkedList.TransferEventMode = DMA_TCEM_BLOCK_TRANSFER;
  h->InitLinkedList.LinkedListMode = DMA_LINKEDLIST_CIRCULAR;
  if (HAL_DMAEx_List_Init(h) != HAL_OK) return false;

  node.NodeType = DMA_GPDMA_LINEAR_NODE;
  node.Init.Request = dma_request[i];
  node.Init.BlkHWRequest = DMA_BREQ_SINGLE_BURST;
  node.Init.Direction = DMA_PERIPH_TO_MEMORY;
  node.Init.SrcInc = DMA_SINC_FIXED;
  node.Init.DestInc = DMA_DINC_INCREMENTED;
  node.Init.SrcDataWidth = DMA_SRC_DATAWIDTH_WORD;
  node.Init.DestDataWidth = DMA_DEST_DATAWIDTH_WORD;
  node.Init.SrcBurstLength = 1;
  node.Init.DestBurstLength = 1;
  node.Init.TransferAllocatedPort = DMA_SRC_ALLOCATED_PORT1 | DMA_DEST_ALLOCATED_PORT0;
  node.Init.TransferEventMode = DMA_TCEM_BLOCK_TRANSFER;
  node.Init.Mode = DMA_NORMAL;
  node.DataHandlingConfig.DataExchange = DMA_EXCHANGE_NONE;
  node.DataHandlingConfig.DataAlignment = DMA_DATA_RIGHTALIGN_ZEROPADDED;
  node.TriggerConfig.TriggerPolarity = DMA_TRIG_POLARITY_MASKED;
  node.RepeatBlockConfig.RepeatCount = 1;
  node.SrcAddress = (uint32_t)&filter_instance[i]->DFLTDR;   /* overwritten by HAL_MDF_AcqStart_DMA */
  node.DstAddress = (uint32_t)dma_buffer[i];
  node.DataSize = sizeof(dma_buffer[i]);
  if (HAL_DMAEx_List_BuildNode(&node, &dma_node[i]) != HAL_OK) return false;
  if (HAL_DMAEx_List_InsertNode_Tail(&dma_queue[i], &dma_node[i]) != HAL_OK) return false;
  if (HAL_DMAEx_List_SetCircularMode(&dma_queue[i]) != HAL_OK) return false;
  if (HAL_DMAEx_List_LinkQ(h, &dma_queue[i]) != HAL_OK) return false;
  __HAL_LINKDMA(&hmdf[i], hdma, hdma[i]);
  HAL_NVIC_SetPriority(dma_irq[i], APP_IRQ_PRIO_GPDMA_MDF, 0);
  HAL_NVIC_EnableIRQ(dma_irq[i]);
  return true;
}

bool bsp_mdf_init(zs_pdm_capture_t *capture, zs_pps_sync_t *pps) {
  g_capture = capture;
  g_pps = pps;
  __HAL_RCC_GPDMA1_CLK_ENABLE();
  for (unsigned i = 0u; i < MDF_CHANNELS; i++) {
    MDF_HandleTypeDef *h = &hmdf[i];
    h->Instance = filter_instance[i];
    /* Common parameters are applied by the first filter init; identical copies on the others. */
    h->Init.CommonParam.InterleavedFilters = 0;
    h->Init.CommonParam.ProcClockDivider = 1;                     /* kernel = PLL1P 3.2 MHz */
    h->Init.CommonParam.OutputClock.Activation = ENABLE;
    h->Init.CommonParam.OutputClock.Pins = MDF_OUTPUT_CLOCK_0;    /* CCK0 on PE9 */
    h->Init.CommonParam.OutputClock.Divider = 1;                  /* 3.2 MHz PDM clock */
    h->Init.CommonParam.OutputClock.Trigger.Activation = DISABLE;
    h->Init.SerialInterface.Activation = ENABLE;
    h->Init.SerialInterface.Mode = MDF_SITF_NORMAL_SPI_MODE;
    h->Init.SerialInterface.ClockSource = MDF_SITF_CCK0_SOURCE;
    h->Init.SerialInterface.Threshold = 31;
    h->Init.FilterBistream = bitstream[i];
    if (HAL_MDF_Init(h) != HAL_OK) return false;
    if (!dma_channel_init(i)) return false;
  }
  return true;
}

bool bsp_mdf_start(void) {
  MDF_FilterConfigTypeDef f = {0};
  MDF_DmaConfigTypeDef d = {0};
  f.DataSource = MDF_DATA_SOURCE_BSMX;
  f.Delay = 0;
  f.CicMode = MDF_ONE_FILTER_SINC5;
  f.DecimationRatio = APP_MDF_DECIMATION;             /* 3.2 MHz / 100 = 32 kHz */
  f.Offset = 0;
  f.Gain = 0;                                         /* 0 dB; tune after the SPL calibration on the bench */
  f.ReshapeFilter.Activation = ENABLE;
  f.ReshapeFilter.DecimationRatio = MDF_RSF_DECIMATION_RATIO_4;
  f.HighPassFilter.Activation = DISABLE;              /* DC removed in zs_pdm_capture */
  f.Integrator.Activation = DISABLE;
  f.SoundActivity.Activation = DISABLE;
  f.AcquisitionMode = MDF_MODE_SYNC_CONT;             /* all four start on the same trigger */
  f.FifoThreshold = MDF_FIFO_THRESHOLD_NOT_EMPTY;
  f.DiscardSamples = 4;
  f.Trigger.Source = MDF_FILTER_TRIG_TRGO;
  f.Trigger.Edge = MDF_FILTER_TRIG_RISING_EDGE;
  g_half_seen = 0u;
  g_full_seen = 0u;
  for (unsigned i = 0u; i < MDF_CHANNELS; i++) {
    d.Address = (uint32_t)dma_buffer[i];
    d.DataLength = sizeof(dma_buffer[i]);
    d.MsbOnly = DISABLE;
    if (HAL_MDF_AcqStart_DMA(&hmdf[i], &f, &d) != HAL_OK) return false;
  }
  /* Single software trigger starts the four filters within one PDM clock: sample 0 is common. */
  return HAL_MDF_GenerateTrgo(&hmdf[0]) == HAL_OK;
}

void bsp_mdf_stop(void) {
  for (unsigned i = 0u; i < MDF_CHANNELS; i++) (void)HAL_MDF_AcqStop_DMA(&hmdf[i]);
}

/* The four channels finish their halves within one sample period of each other; the block is
   reported once, when the last channel's callback arrives. */
static void block_ready(uint8_t *seen, MDF_HandleTypeDef *h, bool half) {
  for (unsigned i = 0u; i < MDF_CHANNELS; i++) if (h == &hmdf[i]) *seen |= (uint8_t)(1u << i);
  if (*seen != 0x0Fu) return;
  *seen = 0u;
  if (g_pps && g_capture) {
    uint32_t ticks = bsp_tim2_pps_now();
    uint64_t samples = zs_pdm_capture_sample_counter(g_capture) +
                       (uint64_t)APP_AUDIO_BLOCK_SAMPLES * (uint64_t)(zs_pdm_capture_pending(g_capture) ? 2u : 1u);
    zs_pps_sync_on_block(g_pps, ticks, samples);
  }
  if (g_capture) {
    if (half) zs_pdm_capture_on_dma_half(g_capture); else zs_pdm_capture_on_dma_full(g_capture);
  }
  extern void app_audio_block_notify_from_isr(void);
  app_audio_block_notify_from_isr();
}

void HAL_MDF_AcqHalfCpltCallback(MDF_HandleTypeDef *h) { block_ready(&g_half_seen, h, true); }
void HAL_MDF_AcqCpltCallback(MDF_HandleTypeDef *h) { block_ready(&g_full_seen, h, false); }
void HAL_MDF_ErrorCallback(MDF_HandleTypeDef *h) { (void)h; g_dma_errors++; }

void MDF1_FLT0_IRQHandler(void) { HAL_MDF_IRQHandler(&hmdf[0]); }
void MDF1_FLT1_IRQHandler(void) { HAL_MDF_IRQHandler(&hmdf[1]); }
void MDF1_FLT2_IRQHandler(void) { HAL_MDF_IRQHandler(&hmdf[2]); }
void MDF1_FLT3_IRQHandler(void) { HAL_MDF_IRQHandler(&hmdf[3]); }
void GPDMA1_Channel0_IRQHandler(void) { HAL_DMA_IRQHandler(&hdma[0]); }
void GPDMA1_Channel1_IRQHandler(void) { HAL_DMA_IRQHandler(&hdma[1]); }
void GPDMA1_Channel2_IRQHandler(void) { HAL_DMA_IRQHandler(&hdma[2]); }
void GPDMA1_Channel3_IRQHandler(void) { HAL_DMA_IRQHandler(&hdma[3]); }
