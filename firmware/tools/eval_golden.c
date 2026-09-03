#include "zs_dsp.h"
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
int main(int argc,char**argv){if(argc!=2)return 2;FILE*f=fopen(argv[1],"rb");if(!f)return 3;int16_t*pcm=malloc(32000*sizeof(int16_t));if(!pcm)return 4;size_t n=fread(pcm,sizeof(int16_t),32000,f);fclose(f);if(n!=32000){free(pcm);return 5;}zs_dsp_ctx_t ctx;zs_dsp_init(&ctx);float v[ZS_FEATURE_COUNT];if(!zs_dsp_extract_1s(&ctx,pcm,32000,v)){free(pcm);return 6;}for(unsigned i=0;i<ZS_FEATURE_COUNT;i++)printf(i?",%.9g":"%.9g",v[i]);printf("\n");free(pcm);return 0;}
