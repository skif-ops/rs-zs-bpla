"""FastAPI router for live ZS-BPLA station integration."""
from __future__ import annotations
import asyncio, json, os, time
from pathlib import Path
from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from station.schemas import DetectionMessage, HeartbeatMessage, SecurityEventMessage, AudioRequest, FeatureUpdateMessage, CommandKeyRotationRequest, FirmwareUpdateRequest, NetworkConfigRequest, RolloutRequest, RolloutReason, RevertRequest
from station.command_codec import validate_command_payload
from station.firmware_codec import ReleaseRepository, UPDATE_COMMAND
from station.model_codec import ModelRepository, parse_model
from station.network_config import NETWORK_COMMAND, next_version
from station.store import EventStore
from station.replay import ReplayError, build_replay, replay_sources
from station.geometry_coverage import coverage_grid
from fusion.bearing_fusion import MAX_RANGE_M
from fusion.geodesy import EnuFrame
from integration import dioneya_alert
from station.service import StationFusionService
from station.cbor_codec import decode_detection_cbor
from station.http_transport import require_insecure_station_http_bench
from station.online_type_service import OnlineTypeSessionService
from station.access_scope import LIVE_RECHECK_S, LiveScope, Scope, close_revoked, scope_of
from station import retention, rollout
from station.analysis_access import operator_of
from config import settings
from utils.build_info import current as current_build

BASE=Path(__file__).resolve().parents[1]
store=EventStore(BASE/'data'/'zs_bpla.sqlite3')
build=current_build(settings.app_version)     # shown by /api/v1/health next to the liveness
service=StationFusionService(store)
type_service=OnlineTypeSessionService()
router=APIRouter(prefix='/api/v1',tags=['ZS-BPLA stations'])
station_http_router=APIRouter(dependencies=[Depends(require_insecure_station_http_bench)])

@router.get('/health')
async def health():
    """Liveness, plus what fills the disk: the database and the audio files, free space, and the retention's last
    run (station/retention.py), so monitoring sees a full disk or a stuck cleanup without the logs."""
    return {'status':'ok','protocol':'1.5','service':'zs-bpla','version':build.version,'build':build.as_dict(),
            'storage':await asyncio.to_thread(store.storage_usage),
            'retention':retention.RUNNER.status() if retention.RUNNER else None,'rollouts':rollout_runner.status()}

@station_http_router.post('/stations/{station_id}/heartbeat')
async def heartbeat(station_id:int,msg:HeartbeatMessage):
    if station_id!=msg.station_id: raise HTTPException(400,'station_id mismatch')
    if msg.cellular is not None: raise HTTPException(400,'cellular identity is accepted only through mutual-TLS MQTT status')
    store.note_station_tenant(station_id,service.alerts.tenant)
    store.upsert_station(msg); service.bus.publish_nowait({'type':'station','data':msg.model_dump()}); return {'status':'ok'}

@station_http_router.post('/stations/{station_id}/detection')
async def detection(station_id:int,msg:DetectionMessage):
    if station_id!=msg.station_id: raise HTTPException(400,'station_id mismatch')
    store.note_station_tenant(station_id,service.alerts.tenant)
    return service.ingest(msg).model_dump()

@station_http_router.post('/stations/{station_id}/detection.cbor')
async def detection_cbor(station_id:int,request:Request):
    raw=await request.body()
    try: msg=decode_detection_cbor(raw)
    except Exception as exc: raise HTTPException(400,f'invalid CBOR: {exc}') from exc
    if station_id!=msg.station_id: raise HTTPException(400,'station_id mismatch')
    store.note_station_tenant(station_id,service.alerts.tenant)
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
    store.note_station_tenant(station_id,service.alerts.tenant)
    store.save_security(msg)
    event={'system_event_id':f'SECURITY-{msg.event_id:016x}-{msg.station_id}','event_type':'SECURITY_EVENT','created_time_us':msg.event_time_us,'source_event_ids':[msg.event_id],'source_station_ids':[msg.station_id],'classification_label':msg.reason,'confidence':1.0,'stations_used':1,'target':{},'route_summary':[f'{msg.route.transport}:{msg.route.hop_count}'],'status':'active'}
    service.bus.publish_nowait(event); return event

# What an operator account sees (station/access_scope.py): its stations and tenants; anything else answers 404.
def _visible_station(request:Request,station_id:int):
    if not scope_of(request,store).station(station_id): raise HTTPException(404,'station not found')

def _visible_event(request:Request,event_id:str)->dict:
    found=store.get_event(event_id)
    result=None if found is None else scope_of(request,store).event(found)
    if result is None: raise HTTPException(404,'event not found')
    return result

@router.get('/stations')
async def stations(request:Request):
    scope=scope_of(request,store)
    return [s for s in store.list_stations() if scope.station(s.get('station_id'))]

@router.get('/events')
async def events(request:Request,limit:int=200):
    scope=scope_of(request,store)
    return [scope.event(e) for e in store.list_events(min(max(limit,1),2000),stations=scope.station_list)]

@router.get('/events/{event_id}')
async def event(request:Request,event_id:str):
    return _visible_event(request,event_id)

@router.get('/events/{event_id}/bearings')
async def event_bearings(request:Request,event_id:str,limit:int=5000):
    """Live bearings (ICD addendum H) of every station whose track belongs to this system event."""
    _visible_event(request,event_id)
    return store.list_bearings(system_event_id=event_id,limit=limit,stations=scope_of(request,store).station_list)

@router.get('/bearings')
async def bearings(request:Request,station_id:int|None=None,track_event_id:int|None=None,since_us:int|None=None,until_us:int|None=None,limit:int=5000):
    return store.list_bearings(station_id=station_id,track_event_id=track_event_id,since_us=since_us,until_us=until_us,limit=limit,
                               stations=scope_of(request,store).station_list)

@router.get('/events/{event_id}/tracks')
async def event_tracks(request:Request,event_id:str):
    """Fused tracks (bearings of two or more stations) that belong to this system event, with their points."""
    _visible_event(request,event_id)
    scope=scope_of(request,store)
    return [scope.track(store.get_track(t['track_id'])) for t in store.list_tracks(system_event_id=event_id,stations=scope.station_list)]

@router.get('/tracks')
async def tracks(request:Request,since_us:int|None=None,until_us:int|None=None,limit:int=200):
    """Fused target tracks overlapping the time range, newest first (summaries; points by /tracks/{track_id})."""
    scope=scope_of(request,store)
    return [scope.track(t) for t in store.list_tracks(since_us=since_us,until_us=until_us,limit=limit,stations=scope.station_list)]

@router.get('/tracks/{track_id}')
async def track(request:Request,track_id:str):
    result=scope_of(request,store).track(store.get_track(track_id))
    if result is None: raise HTTPException(404,'track not found')
    return result

@router.get('/replay')
async def replay(request:Request,track_id:str|None=None,system_event_id:str|None=None,since_us:int|None=None,until_us:int|None=None,
                 station_ids:str|None=None):
    """Everything the replay page draws for a time window (decision 3): stations, fused tracks, bearings, in metres
    east/north/up around the stations."""
    scope=scope_of(request,store)
    if station_ids is not None:
        try: ids=sorted({int(x.strip()) for x in station_ids.split(',') if x.strip()})
        except ValueError: raise HTTPException(422,'station_ids: comma-separated integers') from None
        if not ids or len(ids)>64: raise HTTPException(422,'station_ids: 1..64 stations')
        if any(not scope.station(s) for s in ids): raise HTTPException(404,'station not found')
        # Narrow the already-authorized station set; retain its tenant restriction.
        scope=Scope(scope.tenants, allowed=ids)
    try: return build_replay(store,track_id=track_id,system_event_id=system_event_id,since_us=since_us,until_us=until_us,
                             scope=scope,include_scoped_stations=station_ids is not None)
    except ReplayError as exc: raise HTTPException(404 if 'not found' in str(exc) else 400,str(exc)) from None

@router.get('/replay/sources')
async def replay_sources_list(request:Request,limit:int=50):
    return replay_sources(store,min(max(limit,1),200),scope=scope_of(request,store))

@router.get('/geometry/coverage')
async def geometry_coverage(request:Request,station_ids:str,range_m:float=Query(gt=0,le=MAX_RANGE_M),sigma_deg:float=Query(3.0,gt=0,le=45),
                            height_m:float=Query(150.0,ge=0,le=5000),origin_lat:float|None=None,origin_lon:float|None=None,
                            origin_alt:float|None=None):
    """Blind zones of the station geometry (decision 5): per grid cell around the stations whether a target at height_m
    gets a fused point and with which error; in metres east/north of the origin (default: the stations' mean), so the
    replay page lays it under its own frame."""
    try: ids=sorted({int(x) for x in station_ids.split(',') if x.strip()})
    except ValueError: raise HTTPException(422,'station_ids: comma-separated integers') from None
    if not ids or len(ids)>64: raise HTTPException(422,'station_ids: 1..64 stations')
    scope=scope_of(request,store)
    positions={s:(store.station_position(s) if scope.station(s) else None) for s in ids}
    missing=[s for s,p in positions.items() if p is None]
    if missing: raise HTTPException(404,f'no position for station(s) {missing}')
    if origin_lat is None or origin_lon is None:
        origin_lat=sum(p[0] for p in positions.values())/len(ids); origin_lon=sum(p[1] for p in positions.values())/len(ids)
        origin_alt=sum(p[2] for p in positions.values())/len(ids)
    frame=EnuFrame(origin_lat,origin_lon,origin_alt or 0.0)
    enu={s:[float(v) for v in frame.to_enu(*p)] for s,p in positions.items()}
    grid=coverage_grid([enu[s] for s in ids],range_m=range_m,sigma_deg=sigma_deg,height_m=height_m+sum(e[2] for e in enu.values())/len(ids))
    grid['height_m']=height_m
    return {**grid,'origin':{'lat':origin_lat,'lon':origin_lon,'alt_msl_m':origin_alt or 0.0},
            'stations':[{'station_id':s,'e':round(enu[s][0],1),'n':round(enu[s][1],1),'u':round(enu[s][2],1)} for s in ids]}

def _alert_reader(scope,tenant:str|None):
    """read_alerts arguments for an account: its tenants, and what it may see of each message."""
    if scope.tenants and tenant is not None and tenant not in scope.tenants: return None
    return {'tenant':tenant,'tenants':sorted(scope.tenants) or None,'keep':None if scope.unrestricted else scope.alert}

@router.get('/alerts')
async def alerts(request:Request,after_seq:int=0,tenant:str|None=None,limit:int=500):
    """Output API dioneya.alert/1 (protocols/DIONEYA_ALERT_API_v1.md): messages after a seq, oldest first; continue
    with next_after_seq.  An operator account limited to tenants or stations gets only what they took part in."""
    reader=_alert_reader(scope_of(request,store),tenant)
    if reader is None: raise HTTPException(403,'tenant outside this account')
    messages,next_after=await asyncio.to_thread(store.read_alerts,max(after_seq,0),limit=min(max(limit,1),2000),**reader)
    return {'schema':dioneya_alert.SCHEMA,'messages':messages,'next_after_seq':next_after}

@router.get('/alerts/head')
async def alerts_head(request:Request):
    """Outbox cursor at page entry; the browser subscribes after it and cannot miss an alert during connection setup."""
    scope_of(request,store)
    return {'seq':await asyncio.to_thread(store.last_alert_seq)}

@router.websocket('/alerts/stream')
async def alert_stream(ws:WebSocket,after_seq:int|None=None,tenant:str|None=None,heartbeat_s:float=15.0):
    """dioneya.alert/1 live: the messages after after_seq (default: only new ones), then each new one; a heartbeat
    when the stream has been idle for heartbeat_s."""
    live=LiveScope(ws,store)
    if _alert_reader(live.scope,tenant) is None:
        await ws.close(code=4403); return
    await ws.accept()
    closed=asyncio.create_task(_until_disconnect(ws))
    cursor=await asyncio.to_thread(store.last_alert_seq) if after_seq is None else max(after_seq,0)
    heartbeat_us=int(max(heartbeat_s,1.0)*1e6); last_sent=int(time.time()*1e6)
    try:
        while not closed.done():
            scope=live.current()
            reader=None if scope is None else _alert_reader(scope,tenant)
            if reader is None: await close_revoked(ws); return
            messages,cursor_next=await asyncio.to_thread(store.read_alerts,cursor,limit=500,**reader)
            for m in messages: await ws.send_json(m)
            cursor=cursor_next; now=int(time.time()*1e6)
            if messages: last_sent=now
            elif now-last_sent>=heartbeat_us:
                await ws.send_json(dioneya_alert.heartbeat(cursor,now,tenant)); last_sent=now
            if len(messages)<500: await asyncio.wait({closed},timeout=0.5)
    except (WebSocketDisconnect,RuntimeError): pass
    finally: closed.cancel()

async def _until_disconnect(ws:WebSocket):
    while True:
        if (await ws.receive())['type']=='websocket.disconnect': return

@router.post('/stations/{station_id}/audio-request')
async def request_audio(request:Request,station_id:int,req:AudioRequest):
    _visible_station(request,station_id)
    payload=req.model_dump()
    if payload['event_time_us'] is None:              # the station may have lost its own record (a reboot): send the time
        try: payload['event_time_us']=store.detection_time_us(station_id,req.event_id)
        except ValueError: payload['event_time_us']=None
    if payload['event_time_us'] is None: payload.pop('event_time_us')
    try: command=store.create_command(station_id,'CMD_REQUEST_AUDIO',payload)
    except ValueError as exc: raise HTTPException(400,str(exc)) from None
    return command.model_dump()

@router.post('/stations/{station_id}/command-key-rotation')
async def rotate_command_key(request:Request,station_id:int,req:CommandKeyRotationRequest):
    """ICD addendum E: queue CMD_ROTATE_COMMAND_KEY with the bridge's next public key (--command-next-signing-key,
    printed at its start).  The station trusts both keys after its OK; the first command signed by the next key
    promotes it there."""
    _visible_station(request,station_id)
    payload={'public_key':req.public_key.lower()}
    try:
        validate_command_payload('CMD_ROTATE_COMMAND_KEY',payload)
        command=store.create_command(station_id,'CMD_ROTATE_COMMAND_KEY',payload)
    except ValueError as exc: raise HTTPException(400,str(exc)) from None
    return command.model_dump()

@router.post('/stations/{station_id}/network-config')
async def set_network_config(request:Request,station_id:int,req:NetworkConfigRequest):
    """ICD addendum G: queue CMD_SET_NETWORK_CONFIG (server host, ports, pin, tenant, topic prefix, SIM, APNs).  The
    station tries it on its next bring-up and keeps it only when a session comes online with it; the outcome is in its
    heartbeat (detector.net_config_version / net_state / net_failed_version).  The version defaults to the one the
    station reported + 1."""
    _visible_station(request,station_id)
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
async def update_firmware(request:Request,station_id:int,req:FirmwareUpdateRequest):
    """ICD addendum F: queue CMD_UPDATE_FIRMWARE with the manifest and the offline release signature of a release in
    the repository (python -m pki.cli fw-sign).  The station fetches the image over fwreq/fw from the bridge."""
    _visible_station(request,station_id)
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

# ---- firmware rollouts (station/rollout.py, docs/SERVER_OTA_ROLLOUT_2026-10-03.md): canary, waves, pause, revert ----
rollout_runner=rollout.RolloutRunner(rollout.RolloutSettings.from_env())   # ticked by the app lifespan (app.py)

def _actor(request:Request)->str:
    op=operator_of(request); return str(op.get('name') or '') if op else ''

def _rollout_call(fn,*args,**kwargs):
    try: return fn(*args,**kwargs)
    except rollout.RolloutError as exc:
        raise HTTPException(404 if str(exc)=='rollout not found' else 409,str(exc)) from None

def _visible_rollout(request:Request,rollout_id:str)->dict:
    """A limited account sees a rollout only when it touches one of its stations."""
    found=_rollout_call(rollout_runner.get,store,rollout_id)
    if not scope_of(request,store).any_station(s['station_id'] for s in found['stations']): raise HTTPException(404,'rollout not found')
    return found

@router.get('/firmware/rollouts')
async def firmware_rollouts(request:Request):
    return rollout_runner.list(store,scope_of(request,store).station_list)

@router.post('/firmware/rollouts')
async def create_rollout(request:Request,req:RolloutRequest):
    """A rollout of a repository release to stations: the canary stations first, the rest after they confirmed it;
    at most max_in_flight stations commanded at a time; max_failures failures pause it.  The runner commands the
    stations on its next tick (ZS_ROLLOUT_TICK_S)."""
    scope=scope_of(request,store)
    for s in req.stations:
        if not scope.station(s): raise HTTPException(404,f'station {s} not found')
    return _rollout_call(rollout_runner.create,store,firmware_repository(),version=req.version,stations=req.stations,canary=req.canary,
                         canary_count=req.canary_count,max_failures=req.max_failures,max_in_flight=req.max_in_flight,actor=_actor(request))

@router.get('/firmware/rollouts/{rollout_id}')
async def get_rollout(request:Request,rollout_id:str):
    return _visible_rollout(request,rollout_id)

@router.post('/firmware/rollouts/{rollout_id}/pause')
async def pause_rollout(request:Request,rollout_id:str,req:RolloutReason=Body(default=None)):
    _visible_rollout(request,rollout_id)
    return _rollout_call(rollout_runner.pause,store,rollout_id,actor=_actor(request),reason=req.reason if req else '')

@router.post('/firmware/rollouts/{rollout_id}/resume')
async def resume_rollout(request:Request,rollout_id:str):
    _visible_rollout(request,rollout_id)
    return _rollout_call(rollout_runner.resume,store,rollout_id,actor=_actor(request))

@router.post('/firmware/rollouts/{rollout_id}/cancel')
async def cancel_rollout(request:Request,rollout_id:str,req:RolloutReason=Body(default=None)):
    _visible_rollout(request,rollout_id)
    return _rollout_call(rollout_runner.cancel,store,rollout_id,actor=_actor(request),reason=req.reason if req else '')

@router.post('/firmware/rollouts/{rollout_id}/revert')
async def revert_rollout(request:Request,rollout_id:str,req:RevertRequest):
    """Cancels the rollout and commands the revert release (a version above the reverted one: a station refuses a
    version that is not newer) to every station the rollout commanded; answers the new rollout."""
    _visible_rollout(request,rollout_id)
    return _rollout_call(rollout_runner.revert,store,rollout_id,firmware_repository(),revert_version=req.version,actor=_actor(request),reason=req.reason)

@router.post('/firmware/rollouts/{rollout_id}/stations/{station_id}/skip')
async def skip_rollout_station(request:Request,rollout_id:str,station_id:int,req:RolloutReason=Body(default=None)):
    _visible_rollout(request,rollout_id); _visible_station(request,station_id)
    return _rollout_call(rollout_runner.skip,store,rollout_id,station_id,actor=_actor(request),reason=req.reason if req else '')

def model_repository()->ModelRepository:
    """The model package repository the MQTT bridge serves from (ZS_MODEL_DIR, default server/data/models)."""
    return ModelRepository(os.environ.get('ZS_MODEL_DIR') or BASE/'data'/'models')

@router.post('/stations/{station_id}/model-update')
async def update_model(request:Request,station_id:int,req:FirmwareUpdateRequest):
    """ICD addendum I: queue CMD_UPDATE_FIRMWARE with the manifest (target 3) and release signature of a model package
    in the repository (python -m pki.cli model-sign).  The station loads it after the download, without a reset;
    its heartbeat model text becomes m<version>."""
    _visible_station(request,station_id)
    try: release=model_repository().get(req.version)
    except ValueError as exc: raise HTTPException(409,str(exc)) from None
    if release is None: raise HTTPException(404,f'model {req.version} is not in the model repository')
    try:
        payload=release.command_payload()
        validate_command_payload(UPDATE_COMMAND,payload)
        command=store.create_command(station_id,UPDATE_COMMAND,payload)
    except ValueError as exc: raise HTTPException(400,str(exc)) from None
    return {**command.model_dump(),'model':{'version':release.manifest.version,'size':release.manifest.size,'sha256':release.manifest.sha256.hex()}}

@router.get('/models/releases')
async def model_releases():
    repo=model_repository(); out=[]
    for v in repo.versions():
        try: r=repo.get(v)
        except ValueError: out.append({'version':v,'error':'inconsistent'}); continue
        if r is None: continue
        try: classes=parse_model(r.image).class_count
        except ValueError: out.append({'version':v,'error':'inconsistent'}); continue
        out.append({'version':v,'target':r.manifest.target,'size':r.manifest.size,'classes':classes,'sha256':r.manifest.sha256.hex(),'release_key_id':r.key_id.hex()})
    return out

@router.get('/stations/{station_id}/events/{event_id}/audio')
async def event_audio(request:Request,station_id:int,event_id:int):
    """Assembled audio segments of an event (MQTT upload, addendum B); the WAV is served by the route below."""
    _visible_station(request,station_id)
    try: rows=store.list_audio(station_id,event_id)
    except ValueError as exc: raise HTTPException(400,str(exc)) from None
    return [{'segment':r['segment'],'codec':r['codec'],'sample_rate':r['sample_rate'],'start_time_us':r['start_time_us'],
             'duration_ms':r['duration_ms'],'created_us':r['created_us'],'command_id':r['command_id'],
             'url':f"/api/v1/stations/{station_id}/events/{event_id}/audio/{r['segment']}.wav"} for r in rows if r['codec']=='pcm16-wav']

@router.get('/stations/{station_id}/events/{event_id}/audio/{segment}.wav')
async def event_audio_file(request:Request,station_id:int,event_id:int,segment:str):
    _visible_station(request,station_id)
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
    """The live bus (events, stations, bearings, tracks); an operator account limited to tenants or stations gets
    what they took part in, re-checked every few seconds (station/access_scope.py)."""
    live=LiveScope(ws,store)
    await ws.accept(); q=service.bus.subscribe()
    closed=asyncio.create_task(_until_disconnect(ws))
    try:
        while not closed.done():
            try: item=await asyncio.wait_for(q.get(),timeout=LIVE_RECHECK_S)
            except asyncio.TimeoutError: item=None
            scope=live.current()
            if scope is None: await close_revoked(ws); return
            item=None if item is None else scope.live(item)
            if item is not None: await ws.send_json(item)
    except (WebSocketDisconnect,RuntimeError): pass
    finally: closed.cancel(); service.bus.unsubscribe(q)


router.include_router(station_http_router)
