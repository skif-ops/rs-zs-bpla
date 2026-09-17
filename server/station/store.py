"""SQLite persistence for stations, detections, events and commands."""
from __future__ import annotations
import json, os, sqlite3, threading, time, uuid
from pathlib import Path
from typing import Any
from station.schemas import DetectionMessage, HeartbeatMessage, SecurityEventMessage, StationCommand, SystemEvent

COMMAND_TTL_US = 15 * 60 * 1_000_000

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS stations(station_id INTEGER PRIMARY KEY, updated_us INTEGER NOT NULL, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS detections(event_id INTEGER PRIMARY KEY, station_id INTEGER NOT NULL, event_time_us INTEGER NOT NULL, class_label TEXT NOT NULL, payload TEXT NOT NULL, system_event_id TEXT);
CREATE INDEX IF NOT EXISTS idx_det_time ON detections(event_time_us);
CREATE TABLE IF NOT EXISTS system_events(system_event_id TEXT PRIMARY KEY, created_us INTEGER NOT NULL, event_type TEXT NOT NULL, payload TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_evt_time ON system_events(created_us);
CREATE TABLE IF NOT EXISTS security_events(event_id INTEGER PRIMARY KEY, station_id INTEGER NOT NULL, created_us INTEGER NOT NULL, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS mqtt_detection_ingress(event_key BLOB PRIMARY KEY, station_id INTEGER NOT NULL, boot_id INTEGER NOT NULL, seq_no INTEGER NOT NULL, event_time_us INTEGER NOT NULL, wire_sha256 BLOB NOT NULL, processed INTEGER NOT NULL DEFAULT 0 CHECK(processed IN (0,1)));
CREATE TABLE IF NOT EXISTS commands(command_id TEXT PRIMARY KEY, station_id INTEGER NOT NULL, created_us INTEGER NOT NULL, expires_us INTEGER NOT NULL, command TEXT NOT NULL, payload TEXT NOT NULL, delivered INTEGER NOT NULL DEFAULT 0, acked INTEGER NOT NULL DEFAULT 0, last_publish_us INTEGER NOT NULL DEFAULT 0, publish_count INTEGER NOT NULL DEFAULT 0, ack_result INTEGER, ack_detail INTEGER, completed_us INTEGER);
CREATE INDEX IF NOT EXISTS idx_cmd_station ON commands(station_id, delivered, acked);
CREATE TABLE IF NOT EXISTS audio(event_id INTEGER NOT NULL, station_id INTEGER NOT NULL, segment TEXT NOT NULL, path TEXT NOT NULL, codec TEXT, sample_rate INTEGER, created_us INTEGER NOT NULL, PRIMARY KEY(event_id, station_id, segment));
"""

class EventStore:
    def __init__(self, path: Path):
        self.path=path; path.parent.mkdir(parents=True,exist_ok=True); self.lock=threading.RLock()
        with self._conn() as c:
            c.executescript(SCHEMA)
            self._migrate_commands(c)
        try: os.chmod(path, 0o600)
        except OSError: pass
    def _conn(self):
        c=sqlite3.connect(self.path,timeout=10); c.row_factory=sqlite3.Row; return c
    @staticmethod
    def _event_key(event_id:int)->bytes:
        if type(event_id) is not int or not 0<event_id<=0xFFFFFFFFFFFFFFFF: raise ValueError('event_id is outside uint64 range')
        return event_id.to_bytes(8,'big')
    @staticmethod
    def _sqlite_event_id(event_id:int)->int:
        EventStore._event_key(event_id)
        return event_id if event_id<=0x7FFFFFFFFFFFFFFF else event_id-0x10000000000000000
    def _migrate_commands(self,c):
        columns={row['name'] for row in c.execute("PRAGMA table_info(commands)")}
        additions={
            'expires_us':'INTEGER NOT NULL DEFAULT 0',
            'last_publish_us':'INTEGER NOT NULL DEFAULT 0',
            'publish_count':'INTEGER NOT NULL DEFAULT 0',
            'ack_result':'INTEGER',
            'ack_detail':'INTEGER',
            'completed_us':'INTEGER',
        }
        for name,definition in additions.items():
            if name not in columns: c.execute(f"ALTER TABLE commands ADD COLUMN {name} {definition}")
        c.execute("UPDATE commands SET expires_us=created_us+? WHERE expires_us=0",(COMMAND_TTL_US,))
        c.execute("CREATE INDEX IF NOT EXISTS idx_cmd_due ON commands(acked,expires_us,last_publish_us,created_us)")
    def get_station_heartbeat(self,station_id:int)->HeartbeatMessage|None:
        with self._conn() as c:
            row=c.execute("SELECT payload FROM stations WHERE station_id=?",(station_id,)).fetchone()
        return HeartbeatMessage.model_validate_json(row['payload']) if row else None
    def upsert_station(self, hb: HeartbeatMessage):
        existing=self.get_station_heartbeat(hb.station_id)
        if existing is not None and existing.cellular is not None and hb.cellular is None:
            hb=hb.model_copy(update={'cellular':existing.cellular})
        # Once a configured installation position is known, a later live-GNSS-only
        # heartbeat must not silently move the server-side station geometry.
        if existing is not None and existing.station.position_source=='configured_install' and hb.station.position_source!='configured_install':
            hb=hb.model_copy(update={'gnss_observed':hb.station,'station':existing.station})
        payload=hb.model_dump_json()
        with self.lock,self._conn() as c: c.execute("INSERT OR REPLACE INTO stations VALUES(?,?,?)",(hb.station_id,hb.time_us,payload))
    def save_detection(self,d:DetectionMessage):
        database_event_id=self._sqlite_event_id(d.event_id)
        with self.lock,self._conn() as c:
            c.execute("INSERT OR IGNORE INTO detections(event_id,station_id,event_time_us,class_label,payload) VALUES(?,?,?,?,?)",(database_event_id,d.station_id,d.event_time_us,d.classification.label,d.model_dump_json()))
    def begin_mqtt_detection(self,d:DetectionMessage,wire_sha256:bytes)->str:
        if type(d.station_id) is not int or not 0<d.station_id<=0xFFFFFFFF: raise ValueError('station_id is outside uint32 range')
        if type(d.boot_id) is not int or not 0<=d.boot_id<=0xFFFFFFFF: raise ValueError('boot_id is outside uint32 range')
        if type(d.seq_no) is not int or not 0<=d.seq_no<=0xFFFFFFFF: raise ValueError('seq_no is outside uint32 range')
        if type(d.event_time_us) is not int or not 0<d.event_time_us<=0x7FFFFFFFFFFFFFFF: raise ValueError('event_time_us is outside positive int64 range')
        if not isinstance(wire_sha256,bytes) or len(wire_sha256)!=32: raise ValueError('wire SHA-256 must contain 32 bytes')
        event_key=self._event_key(d.event_id)
        with self.lock,self._conn() as c:
            row=c.execute("SELECT station_id,boot_id,seq_no,event_time_us,wire_sha256,processed FROM mqtt_detection_ingress WHERE event_key=?",(event_key,)).fetchone()
            if row is not None:
                exact=(row['station_id']==d.station_id and row['boot_id']==d.boot_id and row['seq_no']==d.seq_no and row['event_time_us']==d.event_time_us and bytes(row['wire_sha256'])==wire_sha256)
                if not exact: return 'conflict'
                return 'duplicate' if row['processed'] else 'resume'
            existing=c.execute("SELECT 1 FROM detections WHERE event_id=?",(self._sqlite_event_id(d.event_id),)).fetchone()
            if existing is not None: return 'conflict'
            c.execute("INSERT INTO mqtt_detection_ingress(event_key,station_id,boot_id,seq_no,event_time_us,wire_sha256) VALUES(?,?,?,?,?,?)",(event_key,d.station_id,d.boot_id,d.seq_no,d.event_time_us,wire_sha256))
        return 'new'
    def complete_mqtt_detection(self,d:DetectionMessage,wire_sha256:bytes)->bool:
        event_key=self._event_key(d.event_id)
        with self.lock,self._conn() as c:
            result=c.execute("UPDATE mqtt_detection_ingress SET processed=1 WHERE event_key=? AND station_id=? AND boot_id=? AND seq_no=? AND event_time_us=? AND wire_sha256=?",(event_key,d.station_id,d.boot_id,d.seq_no,d.event_time_us,wire_sha256))
        return result.rowcount==1
    def recent_detections(self,center_us:int,window_us:int=3_000_000)->list[DetectionMessage]:
        with self._conn() as c:
            rows=c.execute("SELECT payload FROM detections WHERE event_time_us BETWEEN ? AND ? ORDER BY event_time_us",(center_us-window_us,center_us+window_us)).fetchall()
        return [DetectionMessage.model_validate_json(r['payload']) for r in rows]
    def link_detections(self,event_ids:list[int],system_event_id:str):
        with self.lock,self._conn() as c: c.executemany("UPDATE detections SET system_event_id=? WHERE event_id=?",[(system_event_id,self._sqlite_event_id(e)) for e in event_ids])
    def save_system_event(self,e:SystemEvent):
        with self.lock,self._conn() as c: c.execute("INSERT OR REPLACE INTO system_events VALUES(?,?,?,?)",(e.system_event_id,e.created_time_us,e.event_type,e.model_dump_json()))
    def save_security(self,e:SecurityEventMessage):
        with self.lock,self._conn() as c: c.execute("INSERT OR REPLACE INTO security_events VALUES(?,?,?,?)",(e.event_id,e.station_id,e.event_time_us,e.model_dump_json()))
    def list_events(self,limit:int=200)->list[dict[str,Any]]:
        with self._conn() as c: rows=c.execute("SELECT payload FROM system_events ORDER BY created_us DESC LIMIT ?",(limit,)).fetchall()
        return [json.loads(r['payload']) for r in rows]
    def get_event(self,event_id:str)->dict[str,Any]|None:
        with self._conn() as c: r=c.execute("SELECT payload FROM system_events WHERE system_event_id=?",(event_id,)).fetchone()
        return json.loads(r['payload']) if r else None
    def list_stations(self)->list[dict[str,Any]]:
        with self._conn() as c: rows=c.execute("SELECT payload FROM stations ORDER BY station_id").fetchall()
        payloads=[json.loads(r['payload']) for r in rows]
        for payload in payloads:
            cellular=payload.get('cellular')
            if cellular:
                imsi=cellular.pop('imsi','')
                iccid=cellular.pop('iccid','')
                cellular['imsi_redacted']=f'{imsi[:3]}...{imsi[-4:]}' if len(imsi)>=7 else '***'
                cellular['iccid_redacted']=f'{iccid[:4]}...{iccid[-4:]}' if len(iccid)>=8 else '***'
        return payloads
    def _command_from_row(self,row)->StationCommand:
        return StationCommand(command_id=row['command_id'],station_id=row['station_id'],command=row['command'],payload=json.loads(row['payload']),created_time_us=row['created_us'],expires_time_us=row['expires_us'],publish_count=row['publish_count'])
    def create_command(self,station_id:int,command:str,payload:dict,ttl_us:int=COMMAND_TTL_US)->StationCommand:
        if type(station_id) is not int or not 0<station_id<=0xFFFFFFFF: raise ValueError('station_id is outside uint32 range')
        if type(ttl_us) is not int or not 0<ttl_us<=COMMAND_TTL_US: raise ValueError('command TTL must be 1..15 minutes')
        now=int(time.time()*1e6); expires=now+ttl_us
        cmd=StationCommand(command_id=str(uuid.uuid4()),station_id=station_id,command=command,payload=payload,created_time_us=now,expires_time_us=expires)
        with self.lock,self._conn() as c: c.execute("INSERT INTO commands(command_id,station_id,created_us,expires_us,command,payload) VALUES(?,?,?,?,?,?)",(cmd.command_id,station_id,now,expires,command,json.dumps(payload,ensure_ascii=False)))
        return cmd
    def poll_commands(self,station_id:int,limit:int=10)->list[StationCommand]:
        now=int(time.time()*1e6)
        with self.lock,self._conn() as c:
            rows=c.execute("SELECT * FROM commands WHERE station_id=? AND delivered=0 AND acked=0 AND expires_us>? ORDER BY created_us LIMIT ?",(station_id,now,limit)).fetchall()
            c.executemany("UPDATE commands SET delivered=1,last_publish_us=?,publish_count=publish_count+1 WHERE command_id=?",[(now,r['command_id']) for r in rows])
        return [self._command_from_row(r).model_copy(update={'publish_count':r['publish_count']+1}) for r in rows]
    def due_commands(self,now_us:int,retry_after_us:int,limit:int=50)->list[StationCommand]:
        cutoff=now_us-retry_after_us
        with self._conn() as c:
            rows=c.execute("SELECT * FROM commands WHERE acked=0 AND expires_us>? AND (last_publish_us=0 OR last_publish_us<=?) ORDER BY created_us LIMIT ?",(now_us,cutoff,limit)).fetchall()
        return [self._command_from_row(r) for r in rows]
    def mark_command_published(self,station_id:int,command_id:str,published_us:int)->bool:
        with self.lock,self._conn() as c:
            result=c.execute("UPDATE commands SET delivered=1,last_publish_us=?,publish_count=publish_count+1 WHERE command_id=? AND station_id=? AND acked=0",(published_us,command_id,station_id))
        return result.rowcount==1
    def ack_command(self,station_id:int,command_id:str,result_code:int=0,detail_code:int=0,completed_us:int|None=None)->str:
        when=int(time.time()*1e6) if completed_us is None else completed_us
        with self.lock,self._conn() as c:
            row=c.execute("SELECT station_id,acked FROM commands WHERE command_id=?",(command_id,)).fetchone()
            if row is None: return 'unknown'
            if row['station_id']!=station_id: return 'station_mismatch'
            if row['acked']: return 'duplicate'
            c.execute("UPDATE commands SET acked=1,ack_result=?,ack_detail=?,completed_us=? WHERE command_id=? AND station_id=?",(result_code,detail_code,when,command_id,station_id))
        return 'acked'
    def cleanup(self,retention_days:int=365):
        cutoff=int((time.time()-retention_days*86400)*1e6)
        with self.lock,self._conn() as c:
            c.execute("DELETE FROM system_events WHERE created_us<?",(cutoff,)); c.execute("DELETE FROM detections WHERE event_time_us<?",(cutoff,)); c.execute("DELETE FROM security_events WHERE created_us<?",(cutoff,))
