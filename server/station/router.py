"""FastAPI router for live ZS-BPLA station integration."""
from __future__ import annotations
import json, time
from pathlib import Path
from fastapi import APIRouter, Body, File, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from station.schemas import DetectionMessage, HeartbeatMessage, SecurityEventMessage, AudioRequest, FeatureUpdateMessage
from station.store import EventStore
from station.service import StationFusionService
from station.cbor_codec import decode_detection_cbor
from station.online_type_service import OnlineTypeSessionService

BASE=Path(__file__).resolve().parents[1]
store=EventStore(BASE/'data'/'zs_bpla.sqlite3')
service=StationFusionService(store)
type_service=OnlineTypeSessionService()
router=APIRouter(prefix='/api/v1',tags=['ZS-BPLA stations'])

@router.get('/health')
async def health(): return {'status':'ok','protocol':'1.5','service':'zs-bpla'}

@router.post('/stations/{station_id}/heartbeat')
async def heartbeat(station_id:int,msg:HeartbeatMessage):
    if station_id!=msg.station_id: raise HTTPException(400,'station_id mismatch')
    if msg.cellular is not None: raise HTTPException(400,'cellular identity is accepted only through mutual-TLS MQTT status')
    store.upsert_station(msg); service.bus.publish_nowait({'type':'station','data':msg.model_dump()}); return {'status':'ok'}

@router.post('/stations/{station_id}/detection')
async def detection(station_id:int,msg:DetectionMessage):
    if station_id!=msg.station_id: raise HTTPException(400,'station_id mismatch')
    return service.ingest(msg).model_dump()

@router.post('/stations/{station_id}/detection.cbor')
async def detection_cbor(station_id:int,request:Request):
    raw=await request.body()
    try: msg=decode_detection_cbor(raw)
    except Exception as exc: raise HTTPException(400,f'invalid CBOR: {exc}') from exc
    if station_id!=msg.station_id: raise HTTPException(400,'station_id mismatch')
    event=service.ingest(msg)
    return JSONResponse(event.model_dump())

@router.post('/stations/{station_id}/events/{event_id}/features')
async def feature_update(station_id:int,event_id:int,msg:FeatureUpdateMessage):
    if station_id!=msg.station_id: raise HTTPException(400,'station_id mismatch')
    if event_id!=msg.event_id: raise HTTPException(400,'event_id mismatch')
    status=type_service.ingest(msg)
    service.bus.publish_nowait({'type':'type_update','data':status.model_dump()})
    return status.model_dump()

@router.post('/stations/{station_id}/security')
async def security(station_id:int,msg:SecurityEventMessage):
    if station_id!=msg.station_id: raise HTTPException(400,'station_id mismatch')
    store.save_security(msg)
    event={'system_event_id':f'SECURITY-{msg.event_id:016x}','event_type':'SECURITY_EVENT','created_time_us':msg.event_time_us,'source_event_ids':[msg.event_id],'source_station_ids':[msg.station_id],'classification_label':msg.reason,'confidence':1.0,'stations_used':1,'target':{},'route_summary':[f'{msg.route.transport}:{msg.route.hop_count}'],'status':'active'}
    service.bus.publish_nowait(event); return event

@router.get('/stations')
async def stations(): return store.list_stations()

@router.get('/events')
async def events(limit:int=200): return store.list_events(min(max(limit,1),2000))

@router.get('/events/{event_id}')
async def event(event_id:str):
    result=store.get_event(event_id)
    if result is None: raise HTTPException(404,'event not found')
    return result

@router.post('/stations/{station_id}/audio-request')
async def request_audio(station_id:int,req:AudioRequest):
    return store.create_command(station_id,'CMD_REQUEST_AUDIO',req.model_dump()).model_dump()

@router.get('/stations/{station_id}/commands/poll')
async def poll_commands(station_id:int): return [x.model_dump() for x in store.poll_commands(station_id)]

@router.post('/stations/{station_id}/commands/{command_id}/ack')
async def command_ack(station_id:int,command_id:str): store.ack_command(command_id); return {'status':'ok'}

@router.post('/stations/{station_id}/events/{event_id}/audio')
async def upload_audio(station_id:int,event_id:int,segment:str='pre',sample_rate:int=32000,codec:str='pcm16',audio:UploadFile=File(...)):
    if segment not in ('pre','post'): raise HTTPException(400,'segment must be pre or post')
    root=BASE/'data'/'audio'/str(station_id)/str(event_id); root.mkdir(parents=True,exist_ok=True)
    suffix=Path(audio.filename or 'audio.bin').suffix or '.bin'; path=root/f'{segment}{suffix}'
    path.write_bytes(await audio.read())
    with store.lock,store._conn() as c:
        c.execute('INSERT OR REPLACE INTO audio VALUES(?,?,?,?,?,?,?)',(event_id,station_id,segment,str(path),codec,sample_rate,int(time.time()*1e6)))
    return {'status':'ok','path':str(path),'bytes':path.stat().st_size}

@router.websocket('/stream')
async def stream(ws:WebSocket):
    await ws.accept(); q=service.bus.subscribe()
    try:
        while True: await ws.send_json(await q.get())
    except WebSocketDisconnect: pass
    finally: service.bus.unsubscribe(q)
