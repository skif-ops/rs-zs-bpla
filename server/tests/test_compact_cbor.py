import struct
from fastapi.testclient import TestClient
from app import app
from station.cbor_codec import decode_detection_cbor

def head(major,v):
    if v<24:return bytes([(major<<5)|v])
    if v<=255:return bytes([(major<<5)|24,v])
    if v<=65535:return bytes([(major<<5)|25])+v.to_bytes(2,'big')
    if v<=0xffffffff:return bytes([(major<<5)|26])+v.to_bytes(4,'big')
    return bytes([(major<<5)|27])+v.to_bytes(8,'big')
def enc(v):
    if isinstance(v,bool): return b'\xf5' if v else b'\xf4'
    if isinstance(v,int): return head(0,v) if v>=0 else head(1,-1-v)
    if isinstance(v,bytes): return head(2,len(v))+v
    if isinstance(v,dict): return head(5,len(v))+b''.join(enc(k)+enc(x) for k,x in v.items())
    raise TypeError(type(v))

def compact_packet(station_id=7001,event_id=0x11223344):
    feats=[float(i)/10.0 for i in range(43)]
    # flags: configured position active + position warning
    obj={0:3,1:2,2:station_id,3:17,4:4,5:event_id,6:1_780_000_000_000_000,7:0x0c,
         8:{0:557550000,1:376150000,2:1800,3:True,4:1,5:230,6:3,7:18,8:85,9:80,10:1,11:32000,12:41,13:2,14:1,15:5},
         9:struct.pack('<'+'e'*43,*feats),10:{0:77,1:12600,2:18800,3:-55,4:0,5:0,6:-71,7:95,8:0},11:{0:1234,1:550,2:900,3:True},
         12:{0:1,1:220,2:0,3:0,4:2,5:0},
         13:{0:0,1:0,2:0,3:0,4:0,5:0,6:0},
         14:{0:-120,1:45,2:-310,3:6,4:210,5:1,6:3}}
    return enc(obj)

def legacy_packet():
    return enc({0:1,1:2,2:7002,3:1,4:1,5:2,6:3,7:0,
                8:{0:557550000,1:376150000,2:1800,3:True,4:0,5:0,6:3,7:12,8:100,9:100,10:0,11:32000},
                10:{0:50,1:12500,2:0,3:200,4:5,5:0,6:0,7:0,8:0},
                12:{0:0,1:0,2:0,3:0,4:0,5:0},13:{0:0,1:0,2:0,3:0,4:0,5:0,6:0},14:{0:0,1:0,2:0,3:0,4:0,5:1,6:0}})

def test_compact_decoder_roundtrip_fields():
    msg=decode_detection_cbor(compact_packet())
    assert msg.station_id==7001 and msg.station.alt_m==180.0 and msg.gnss.pps_ok
    assert msg.station.position_source=='configured_install' and msg.station.pos_accuracy_m==5
    assert msg.gnss.position_delta_m==41 and msg.gnss.position_warn
    assert msg.gnss.position_trust=='CONFIGURED_WARN' and msg.gnss.time_trust=='GNSS_TIME_TRUSTED'
    assert msg.classification.class_id==1 and msg.classification.confidence_u8==230
    assert len(msg.features)==43 and abs(msg.features[42]-4.2)<0.01
    assert msg.route.transport=='LTE' and msg.power.temperature_c==-5.5 and msg.doa.valid
    assert msg.hierarchy.family_label=='PROP_PISTON'
    assert msg.spatial.tdoa_valid and msg.spatial.direction_valid
    assert msg.spatial.geometry_id==1 and msg.spatial.tdoa14_us==-310
    assert msg.spatial.pair_tdoas_us['tdoa24_us']==-190

def test_legacy_packet_remains_decodable():
    msg=decode_detection_cbor(legacy_packet())
    assert msg.station.position_source=='gnss_live'
    assert msg.gnss.position_trust=='UNCONFIGURED'

def test_compact_cbor_http_ingress():
    client=TestClient(app); r=client.post('/api/v1/stations/7011/detection.cbor',content=compact_packet(7011,0x55667788),headers={'content-type':'application/cbor'})
    assert r.status_code==200,r.text; assert r.json()['event_type'] in ('AIR_WARNING','AIR_ALERT')

def test_health():
    client=TestClient(app); r=client.get('/api/v1/health'); assert r.status_code==200 and r.json()['status']=='ok'
