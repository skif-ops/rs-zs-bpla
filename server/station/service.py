"""Ingestion, correlation and tracking service."""
from __future__ import annotations
import math, time, uuid, asyncio
from collections import defaultdict
import numpy as np
from station.schemas import DetectionMessage, SystemEvent, TargetEstimate
from station.store import EventStore
from fusion.solver import solve_target
from fusion.geodesy import EnuFrame
from fusion.kalman import ConstantVelocityKalman3D

class EventBus:
    def __init__(self): self._queues:set[asyncio.Queue]=set()
    def subscribe(self):
        q=asyncio.Queue(maxsize=100); self._queues.add(q); return q
    def unsubscribe(self,q): self._queues.discard(q)
    def publish_nowait(self,item):
        for q in list(self._queues):
            try: q.put_nowait(item)
            except asyncio.QueueFull:
                try: q.get_nowait(); q.put_nowait(item)
                except Exception: pass

class StationFusionService:
    def __init__(self,store:EventStore,correlation_window_s:float=3.0):
        self.store=store; self.window_us=int(correlation_window_s*1e6); self.bus=EventBus(); self.track_filters={}; self.track_frames={}
    @staticmethod
    def _compatible(a:DetectionMessage,b:DetectionMessage)->bool:
        if a.classification.unknown or b.classification.unknown: return True
        if a.classification.class_id==b.classification.class_id: return True
        # Both UAV families may correlate during uncertain first-stage classification.
        return a.classification.class_id in (1,2,3) and b.classification.class_id in (1,2,3)
    def ingest(self,d:DetectionMessage)->SystemEvent:
        self.store.save_detection(d)
        candidates=[x for x in self.store.recent_detections(d.event_time_us,self.window_us) if self._compatible(d,x)]
        # One best detection per station, closest to current event time.
        by_station={}
        for x in candidates:
            old=by_station.get(x.station_id)
            if old is None or abs(x.event_time_us-d.event_time_us)<abs(old.event_time_us-d.event_time_us): by_station[x.station_id]=x
        grouped=list(by_station.values())
        is_alert=len(grouped)>=2
        target=solve_target(grouped) if is_alert else TargetEstimate()
        conf=float(np.mean([x.classification.confidence for x in grouped])) if grouped else d.classification.confidence
        event_type='AIR_ALERT' if is_alert else 'AIR_WARNING'
        sid=f"{event_type}-{min(x.event_id for x in grouped):016x}" if grouped else f"{event_type}-{d.event_id:016x}"
        if is_alert and target.lat is not None:
            target=self._track(sid,target,grouped)
        e=SystemEvent(system_event_id=sid,event_type=event_type,created_time_us=max(x.event_time_us for x in grouped),source_event_ids=[x.event_id for x in grouped],source_station_ids=[x.station_id for x in grouped],classification_label=self._label(grouped),confidence=conf,stations_used=len(grouped),target=target,route_summary=[f"{x.station_id}:{x.route.transport}:{x.route.hop_count}" for x in grouped])
        self.store.save_system_event(e); self.store.link_detections(e.source_event_ids,sid); self.bus.publish_nowait(e.model_dump())
        return e
    @staticmethod
    def _label(dets):
        if not dets:return 'UNKNOWN'
        return max(dets,key=lambda x:x.classification.confidence).classification.label
    def _track(self,key:str,target:TargetEstimate,dets:list[DetectionMessage])->TargetEstimate:
        # Association key is broad class + local area, not system event ID.
        cls=self._label(dets); station0=dets[0].station; track_key=f"{cls}:{round(station0.lat,2)}:{round(station0.lon,2)}"
        frame=self.track_frames.get(track_key)
        if frame is None:
            frame=EnuFrame(target.lat,target.lon,target.alt_msl_m or 0.0); self.track_frames[track_key]=frame; self.track_filters[track_key]=ConstantVelocityKalman3D()
        pos=frame.to_enu(target.lat,target.lon,target.alt_msl_m or frame.alt0)
        state=self.track_filters[track_key].update(pos,max(d.event_time_us for d in dets)*1e-6,target.horizontal_error_m or 100.0)
        lat,lon,alt=frame.to_geodetic(*state[:3]); vx,vy,vz=state[3:]
        speed=float(math.hypot(vx,vy)); course=(math.degrees(math.atan2(vx,vy))+360.0)%360.0 if speed>0.05 else 0.0
        return target.model_copy(update={'lat':lat,'lon':lon,'alt_msl_m':alt,'vx_east_mps':float(vx),'vy_north_mps':float(vy),'vz_up_mps':float(vz),'speed_mps':speed,'course_deg':course})
