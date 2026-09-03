#include "zs_gnss.h"
#include <string.h>
#include <stdlib.h>
#include <math.h>
static bool checksum_ok(const char*s){if(!s||*s!='$')return false;const char*star=strchr(s,'*');if(!star)return true;unsigned x=0;for(const char*p=s+1;p<star;p++)x^=(unsigned char)*p;unsigned got=strtoul(star+1,0,16);return (x&255u)==(got&255u);}
static int split(char*b,char*v[],int max){int n=0;char*p=b;while(n<max){v[n++]=p;char*c=strchr(p,',');if(!c)break;*c=0;p=c+1;}return n;}
static int32_t coord_e7(const char*s,char hemi){if(!s||!*s)return 0;double v=strtod(s,0),deg=floor(v/100.0),min=v-deg*100.0,x=deg+min/60.0;if(hemi=='S'||hemi=='W')x=-x;return (int32_t)llround(x*1e7);}
void zs_gnss_nmea_init(zs_gnss_nmea_t*g){if(g)memset(g,0,sizeof(*g));}
bool zs_gnss_parse_line(zs_gnss_nmea_t *g,const char *line){if(!g||!line||!checksum_ok(line))return false;char b[160];const size_t n=strlen(line);if(n>=sizeof(b))return false;memcpy(b,line,n+1);char *star=strchr(b,'*');if(star)*star=0;char *v[24];const int c=split(b,v,24);if(c<2)return false;if(strstr(v[0],"GGA")){if(c<10)return false;strncpy(g->utc_hhmmss,v[1],sizeof(g->utc_hhmmss)-1);const int fix=atoi(v[6]);g->satellites=(uint8_t)atoi(v[7]);g->hdop_x100=(uint16_t)lround(strtod(v[8],0)*100.0);g->valid_fix=fix>0;if(g->valid_fix){g->position.lat_e7=coord_e7(v[2],v[3][0]);g->position.lon_e7=coord_e7(v[4],v[5][0]);g->position.alt_dm=(int32_t)lround(strtod(v[9],0)*10.0);g->position.altitude_source=1;}return true;}if(strstr(v[0],"RMC")){if(c<9)return false;g->rmc_valid=v[2][0]=='A';if(g->rmc_valid){g->position.lat_e7=coord_e7(v[3],v[4][0]);g->position.lon_e7=coord_e7(v[5],v[6][0]);const double knots=strtod(v[7],0);g->speed_cms=(uint16_t)lround(knots*0.514444*100.0);g->course_cdeg=(uint16_t)lround(strtod(v[8],0)*100.0);}return true;}return false;}
