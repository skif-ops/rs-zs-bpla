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
    obj={0:1,1:2,2:station_id,3:17,4:4,5:event_id,6:1_780_000_000_000_000,7:0,
         8:{0:557550000,1:376150000,2:1800,3:True,4:1,5:230,6:3,7:18,8:85,9:80,10:1,11:32000},
         9:struct.pack('<'+'e'*43,*feats),10:{0:77,1:12600,2:18800,3:-55,4:0,5:0,6:-71,7:95,8:0},11:{0:1234,1:550,2:900,3:True},
         12:{0:1,1:3,2:80},14:{0:1234,1:550,2:900,3:1200,4:15,5:True}}
    return enc(obj)

def test_compact_decoder_roundtrip_fields():
    msg=decode_detection_cbor(compact_packet())
    assert msg.station_id==7001 and msg.station.alt_m==180.0 and msg.gnss.pps_ok
    assert msg.classification.class_id==1 and msg.classification.confidence_u8==230
    assert len(msg.features)==43 and abs(msg.features[42]-4.2)<0.01
    assert msg.route.transport=='LTE' and msg.power.temperature_c==-5.5 and msg.doa.valid
    assert msg.time_status.tdoa_allowed and msg.spatial.mic_health_mask==15 and msg.spatial.valid

def test_compact_cbor_http_ingress():
    client=TestClient(app); r=client.post('/api/v1/stations/7011/detection.cbor',content=compact_packet(7011,0x55667788),headers={'content-type':'application/cbor'})
    assert r.status_code==200,r.text; assert r.json()['event_type'] in ('AIR_WARNING','AIR_ALERT')

def test_health():
    client=TestClient(app); r=client.get('/api/v1/health'); assert r.status_code==200 and r.json()['status']=='ok'
