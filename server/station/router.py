"""FastAPI router for live ZS-BPLA station integration."""
from __future__ import annotations
import json, os, time
from pathlib import Path
from fastapi import APIRouter, Body, Depends, File, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from station.schemas import DetectionMessage, HeartbeatMessage, SecurityEventMessage, AudioRequest, FeatureUpdateMessage, CommandKeyRotationRequest, FirmwareUpdateRequest, NetworkConfigRequest
from station.command_codec import validate_command_payload
from station.firmware_codec import ReleaseRepository, UPDATE_COMMAND
from station.network_config import NETWORK_COMMAND, next_version
from station.store import EventStore
from station.replay import ReplayError, build_replay, replay_sources
from station.service import StationFusionService
from station.cbor_codec import decode_detection_cbor
from station.http_transport import require_insecure_station_http_bench
from station.online_type_service import OnlineTypeSessionService

BASE=Path(__file__).resolve().parents[1]
store=EventStore(BASE/'data'/'zs_bpla.sqlite3')
service=StationFusionService(store)
type_service=OnlineTypeSessionService()
router=APIRouter(prefix='/api/v1',tags=['ZS-BPLA stations'])
station_http_router=APIRouter(dependencies=[Depends(require_insecure_station_http_bench)])

@router.get('/health')
async def health(): return {'status':'ok','protocol':'1.5','service':'zs-bpla'}

@station_http_router.post('/stations/{station_id}/heartbeat')
async def heartbeat(station_id:int,msg:HeartbeatMessage):
    if station_id!=msg.station_id: raise HTTPException(400,'station_id mismatch')
    if msg.cellular is not None: raise HTTPException(400,'cellular identity is accepted only through mutual-TLS MQTT status')
    store.upsert_station(msg); service.bus.publish_nowait({'type':'station','data':msg.model_dump()}); return {'status':'ok'}

@station_http_router.post('/stations/{station_id}/detection')
async def detection(station_id:int,msg:DetectionMessage):
    if station_id!=msg.station_id: raise HTTPException(400,'station_id mismatch')
    return service.ingest(msg).model_dump()

@station_http_router.post('/stations/{station_id}/detection.cbor')
async def detection_cbor(station_id:int,request:Request):
    raw=await request.body()
    try: msg=decode_detection_cbor(raw)
    except Exception as exc: raise HTTPException(400,f'invalid CBOR: {exc}') from exc
    if station_id!=msg.station_id: raise HTTPException(400,'station_id mismatch')
    event=service.ingest(msg)
    return JSONResponse(event.model_dump())

@station_http_router.post('/stations/{station_id}/events/{event_id}/features')
async def feature_update(station_id:int,event_id:int,msg:FeatureUpdateMessage):
    if station_id!=msg.station_id: raise HTTPException(400,'station_id mismatch')
    if event_id!=msg.event_id: raise HTTPException(400,'event_id mismatch')
    status=type_service.ingest(msg)
    service.bus.publish_nowait({'type':'type_update','data':status.model_dump()})
    return status.model_dump()

@station_http_router.post('/stations/{station_id}/security')
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

@router.get('/events/{event_id}/bearings')
async def event_bearings(event_id:str,limit:int=5000):
    """Live bearings (ICD addendum H) of every station whose track belongs to this system event."""
    if store.get_event(event_id) is None: raise HTTPException(404,'event not found')
    return store.list_bearings(system_event_id=event_id,limit=limit)

@router.get('/bearings')
async def bearings(station_id:int|None=None,track_event_id:int|None=None,since_us:int|None=None,until_us:int|None=None,limit:int=5000):
    return store.list_bearings(station_id=station_id,track_event_id=track_event_id,since_us=since_us,until_us=until_us,limit=limit)

@router.get('/events/{event_id}/tracks')
async def event_tracks(event_id:str):
    """Fused tracks (bearings of two or more stations) that belong to this system event, with their points."""
    if store.get_event(event_id) is None: raise HTTPException(404,'event not found')
    return [store.get_track(t['track_id']) for t in store.list_tracks(system_event_id=event_id)]

@router.get('/tracks')
async def tracks(since_us:int|None=None,until_us:int|None=None,limit:int=200):
    """Fused target tracks overlapping the time range, newest first (summaries; points by /tracks/{track_id})."""
    return store.list_tracks(since_us=since_us,until_us=until_us,limit=limit)

@router.get('/tracks/{track_id}')
async def track(track_id:str):
    result=store.get_track(track_id)
    if result is None: raise HTTPException(404,'track not found')
    return result

@router.get('/replay')
async def replay(track_id:str|None=None,system_event_id:str|None=None,since_us:int|None=None,until_us:int|None=None):
    """Everything the replay page draws for a time window (decision 3): stations, fused tracks, bearings, in metres
    east/north/up around the stations."""
    try: return build_replay(store,track_id=track_id,system_event_id=system_event_id,since_us=since_us,until_us=until_us)
    except ReplayError as exc: raise HTTPException(404 if 'not found' in str(exc) else 400,str(exc)) from None

@router.get('/replay/sources')
async def replay_sources_list(limit:int=50):
    return replay_sources(store,min(max(limit,1),200))

@router.post('/stations/{station_id}/audio-request')
async def request_audio(station_id:int,req:AudioRequest):
    payload=req.model_dump()
    if payload['event_time_us'] is None:              # the station may have lost its own record (a reboot): send the time
        try: payload['event_time_us']=store.detection_time_us(station_id,req.event_id)
        except ValueError: payload['event_time_us']=None
    if payload['event_time_us'] is None: payload.pop('event_time_us')
    try: command=store.create_command(station_id,'CMD_REQUEST_AUDIO',payload)
    except ValueError as exc: raise HTTPException(400,str(exc)) from None
    return command.model_dump()

@router.post('/stations/{station_id}/command-key-rotation')
async def rotate_command_key(station_id:int,req:CommandKeyRotationRequest):
    """ICD addendum E: queue CMD_ROTATE_COMMAND_KEY with the bridge's next public key (--command-next-signing-key,
    printed at its start).  The station trusts both keys after its OK; the first command signed by the next key
    promotes it there."""
    payload={'public_key':req.public_key.lower()}
    try:
        validate_command_payload('CMD_ROTATE_COMMAND_KEY',payload)
        command=store.create_command(station_id,'CMD_ROTATE_COMMAND_KEY',payload)
    except ValueError as exc: raise HTTPException(400,str(exc)) from None
    return command.model_dump()

@router.post('/stations/{station_id}/network-config')
async def set_network_config(station_id:int,req:NetworkConfigRequest):
    """ICD addendum G: queue CMD_SET_NETWORK_CONFIG (server host, ports, pin, tenant, topic prefix, SIM, APNs).  The
    station tries it on its next bring-up and keeps it only when a session comes online with it; the outcome is in its
    heartbeat (detector.net_config_version / net_state / net_failed_version).  The version defaults to the one the
    station reported + 1."""
    payload={k:v for k,v in req.model_dump().items() if v is not None}
    try:
        if 'version' not in payload: payload['version']=next_version(store.get_station_heartbeat(station_id))
    except ValueError as exc: raise HTTPException(409,str(exc)) from None
    try:
        validate_command_payload(NETWORK_COMMAND,payload)
        command=store.create_command(station_id,NETWORK_COMMAND,payload)
    except ValueError as exc: raise HTTPException(400,str(exc)) from None
    return command.model_dump()

def firmware_repository()->ReleaseRepository:
    """The same release repository the MQTT bridge serves from (ZS_FIRMWARE_DIR, default server/data/firmware)."""
    return ReleaseRepository(os.environ.get('ZS_FIRMWARE_DIR') or BASE/'data'/'firmware')

@router.post('/stations/{station_id}/firmware-update')
async def update_firmware(station_id:int,req:FirmwareUpdateRequest):
    """ICD addendum F: queue CMD_UPDATE_FIRMWARE with the manifest and the offline release signature of a release in
    the repository (python -m pki.cli fw-sign).  The station fetches the image over fwreq/fw from the bridge."""
    try: release=firmware_repository().get(req.version)
    except ValueError as exc: raise HTTPException(409,str(exc)) from None
    if release is None: raise HTTPException(404,f'release {req.version} is not in the firmware repository')
    try:
        payload=release.command_payload()
        validate_command_payload(UPDATE_COMMAND,payload)
        command=store.create_command(station_id,UPDATE_COMMAND,payload)
    except ValueError as exc: raise HTTPException(400,str(exc)) from None
    return {**command.model_dump(),'release':{'version':release.manifest.version,'size':release.manifest.size,'sha256':release.manifest.sha256.hex()}}

@router.get('/firmware/releases')
async def firmware_releases():
    repo=firmware_repository(); out=[]
    for v in repo.versions():
        try: r=repo.get(v)
        except ValueError: out.append({'version':v,'error':'inconsistent'}); continue
        if r is not None: out.append({'version':v,'target':r.manifest.target,'size':r.manifest.size,'sha256':r.manifest.sha256.hex(),'release_key_id':r.key_id.hex()})
    return out

@router.get('/stations/{station_id}/events/{event_id}/audio')
async def event_audio(station_id:int,event_id:int):
    """Assembled audio segments of an event (MQTT upload, addendum B); the WAV is served by the route below."""
    try: rows=store.list_audio(station_id,event_id)
    except ValueError as exc: raise HTTPException(400,str(exc)) from None
    return [{'segment':r['segment'],'codec':r['codec'],'sample_rate':r['sample_rate'],'start_time_us':r['start_time_us'],
             'duration_ms':r['duration_ms'],'created_us':r['created_us'],'command_id':r['command_id'],
             'url':f"/api/v1/stations/{station_id}/events/{event_id}/audio/{r['segment']}.wav"} for r in rows if r['codec']=='pcm16-wav']

@router.get('/stations/{station_id}/events/{event_id}/audio/{segment}.wav')
async def event_audio_file(station_id:int,event_id:int,segment:str):
    if segment not in ('pre','post'): raise HTTPException(404,'no such segment')
    try: rows=[r for r in store.list_audio(station_id,event_id) if r['segment']==segment and r['codec']=='pcm16-wav']
    except ValueError as exc: raise HTTPException(400,str(exc)) from None
    if not rows: raise HTTPException(404,'audio not uploaded')
    path=Path(rows[0]['path']).resolve()
    if not path.is_relative_to(store.audio_root.resolve()) or not path.is_file(): raise HTTPException(404,'audio file missing')
    return FileResponse(path,media_type='audio/wav',filename=f'station{station_id}_event{event_id}_{segment}.wav')

@station_http_router.get('/stations/{station_id}/commands/poll')
async def poll_commands(station_id:int): return [x.model_dump() for x in store.poll_commands(station_id)]

@station_http_router.post('/stations/{station_id}/commands/{command_id}/ack')
async def command_ack(station_id:int,command_id:str):
    status=store.ack_command(station_id,command_id)
    if status=='unknown': raise HTTPException(404,'command not found')
    if status=='station_mismatch': raise HTTPException(409,'command does not belong to station')
    return {'status':status}

@station_http_router.post('/stations/{station_id}/events/{event_id}/audio')
async def upload_audio(station_id:int,event_id:int,segment:str='pre',sample_rate:int=32000,codec:str='pcm16',audio:UploadFile=File(...)):
    if segment not in ('pre','post'): raise HTTPException(400,'segment must be pre or post')
    root=BASE/'data'/'audio'/str(station_id)/str(event_id); root.mkdir(parents=True,exist_ok=True)
    suffix=Path(audio.filename or 'audio.bin').suffix or '.bin'; path=root/f'{segment}{suffix}'
    path.write_bytes(await audio.read())
    with store.lock,store._conn() as c:
        c.execute('INSERT OR REPLACE INTO audio(event_id,station_id,segment,path,codec,sample_rate,created_us) VALUES(?,?,?,?,?,?,?)',(store._sqlite_event_id(event_id),station_id,segment,str(path),codec,sample_rate,int(time.time()*1e6)))
    return {'status':'ok','path':str(path),'bytes':path.stat().st_size}

@router.websocket('/stream')
async def stream(ws:WebSocket):
    await ws.accept(); q=service.bus.subscribe()
    try:
        while True: await ws.send_json(await q.get())
    except WebSocketDisconnect: pass
    finally: service.bus.unsubscribe(q)


router.include_router(station_http_router)
