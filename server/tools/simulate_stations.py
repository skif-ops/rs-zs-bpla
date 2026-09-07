"""Send two synthetic station detections to a running local server."""
from __future__ import annotations
import json, time, urllib.request

def message(station_id,event_id,lat,lon,az,t_us):
    return {'schema_ver':1,'station_id':station_id,'seq_no':event_id,'boot_id':1,'event_id':event_id,'event_time_us':t_us,
      'station':{'lat_e7':int(lat*1e7),'lon_e7':int(lon*1e7),'alt_dm':1200,'pos_accuracy_m':5},
      'gnss':{'fix_type':3,'satellites':14,'hdop_x100':80,'pps_ok':True,'expected_time_error_us':80},
      'classification':{'class_id':1,'label':'FP-1','confidence_u8':230,'unknown':False},'features':[0.0]*43,
      'doa':{'azimuth_cdeg':int(az*100),'elevation_cdeg':800,'sigma_cdeg':500,'valid':True},
      'power':{'battery_pct':82,'battery_mv':12900,'solar_mv':17000,'temperature_c10':200},'route':{'transport':'TEST','hop_count':0}}
def post(station_id,m):
    req=urllib.request.Request(f'http://127.0.0.1:8000/api/v1/stations/{station_id}/detection',data=json.dumps(m).encode(),headers={'Content-Type':'application/json'},method='POST')
    with urllib.request.urlopen(req) as r: print(json.dumps(json.load(r),ensure_ascii=False,indent=2))
if __name__=='__main__':
    t=int(time.time()*1e6); post(1001,message(1001,10010001,55.0000,37.0000,45,t)); post(1002,message(1002,10020001,55.0000,37.0200,315,t+20000))
