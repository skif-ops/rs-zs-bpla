#include "zs_cbor.h"
#include <string.h>

static void put(zs_cbor_t*c,const void*d,size_t n){if(c->error||c->len+n>c->cap){c->error=true;return;}memcpy(c->buf+c->len,d,n);c->len+=n;}
static void major(zs_cbor_t*c,uint8_t m,uint64_t v){uint8_t b;if(v<24){b=(uint8_t)((m<<5)|v);put(c,&b,1);}else if(v<=0xff){uint8_t a[2]={(uint8_t)((m<<5)|24),(uint8_t)v};put(c,a,2);}else if(v<=0xffff){uint8_t a[3]={(uint8_t)((m<<5)|25),(uint8_t)(v>>8),(uint8_t)v};put(c,a,3);}else if(v<=0xffffffffu){uint8_t a[5]={(uint8_t)((m<<5)|26),(uint8_t)(v>>24),(uint8_t)(v>>16),(uint8_t)(v>>8),(uint8_t)v};put(c,a,5);}else{uint8_t a[9]={(uint8_t)((m<<5)|27),(uint8_t)(v>>56),(uint8_t)(v>>48),(uint8_t)(v>>40),(uint8_t)(v>>32),(uint8_t)(v>>24),(uint8_t)(v>>16),(uint8_t)(v>>8),(uint8_t)v};put(c,a,9);}}
void zs_cbor_init(zs_cbor_t*c,uint8_t*b,size_t cap){c->buf=b;c->cap=cap;c->len=0;c->error=false;}
void zs_cbor_map(zs_cbor_t*c,uint32_t count){major(c,5,count);}
void zs_cbor_uint(zs_cbor_t*c,uint64_t v){major(c,0,v);}
void zs_cbor_int(zs_cbor_t*c,int64_t v){if(v>=0)major(c,0,(uint64_t)v);else major(c,1,(uint64_t)(-1-v));}
void zs_cbor_bool(zs_cbor_t*c,bool v){uint8_t b=(uint8_t)(v?0xf5:0xf4);put(c,&b,1);}
void zs_cbor_bytes(zs_cbor_t*c,const void*d,size_t n){major(c,2,n);put(c,d,n);}
void zs_cbor_text(zs_cbor_t*c,const char*text){size_t n;if(!text){c->error=true;return;}n=strlen(text);major(c,3,n);put(c,text,n);}
