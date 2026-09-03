#include "zs_dsp.h"
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
int main(int argc,char**argv){if(argc!=3)return 2;FILE*f=fopen(argv[1],"rb");if(!f)return 3;int16_t*p=malloc(64000);fread(p,2,32000,f);fclose(f);float*m=malloc(16001*4);if(!zs_dsp_debug_global_magnitude(p,32000,m,16001))return 4;FILE*o=fopen(argv[2],"wb");fwrite(m,4,16001,o);fclose(o);return 0;}
