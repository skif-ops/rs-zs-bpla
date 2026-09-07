from pathlib import Path
from fastapi.testclient import TestClient
from app import app
from station.router import store

client=TestClient(app)

def det(station_id,event_id,t_us,lat,lon,az):
    return {
      'schema_ver':1,'station_id':station_id,'seq_no':event_id,'boot_id':1,'event_id':event_id,'event_time_us':t_us,
      'station':{'lat_e7':int(lat*1e7),'lon_e7':int(lon*1e7),'alt_dm':1000},
      'gnss':{'fix_type':3,'satellites':12,'hdop_x100':80,'pps_ok':True,'expected_time_error_us':80},
      'classification':{'class_id':1,'label':'FP-1','confidence_u8':230,'unknown':False},
      'features':[0.0]*43,'doa':{'azimuth_cdeg':int(az*100),'elevation_cdeg':1000,'sigma_cdeg':500,'valid':True},
      'power':{'battery_pct':80,'battery_mv':13000,'solar_mv':17000,'temperature_c10':200},'route':{'transport':'TEST','hop_count':0}
    }

def test_warning_then_alert(tmp_path):
    # Unique IDs avoid collisions with persistent local DB from other tests.
    t=2_000_000_000_000_000
    a=client.post('/api/v1/stations/9001/detection',json=det(9001,9001001,t,55.0,37.0,45.0)); assert a.status_code==200; assert a.json()['event_type']=='AIR_WARNING'
    b=client.post('/api/v1/stations/9002/detection',json=det(9002,9002001,t+20000,55.0,37.02,315.0)); assert b.status_code==200; assert b.json()['event_type']=='AIR_ALERT'; assert b.json()['stations_used']>=2

def test_feature_count_validation():
    d=det(9003,9003001,2_100_000_000_000_000,55.1,37.1,0); d['features']=[1.0]
    r=client.post('/api/v1/stations/9003/detection',json=d); assert r.status_code==422

def test_feature_update_warms_up_without_hard_type_lock():
    payload={
        'schema_ver':1,'station_id':9010,'seq_no':1,'boot_id':1,'event_id':9010001,
        'event_time_us':2_200_000_000_000_000,'features':[0.0]*43,'detector_profile':'piston'
    }
    r=client.post('/api/v1/stations/9010/events/9010001/features',json=payload)
    assert r.status_code==200
    body=r.json()
    assert body['status']=='warming_up'
    assert body['type_lock_allowed'] is False
