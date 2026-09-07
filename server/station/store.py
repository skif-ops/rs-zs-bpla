"""SQLite persistence for stations, detections, events and commands."""
from __future__ import annotations
import json, sqlite3, threading, time, uuid
from pathlib import Path
from typing import Any
from station.schemas import DetectionMessage, HeartbeatMessage, SecurityEventMessage, StationCommand, SystemEvent

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS stations(station_id INTEGER PRIMARY KEY, updated_us INTEGER NOT NULL, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS detections(event_id INTEGER PRIMARY KEY, station_id INTEGER NOT NULL, event_time_us INTEGER NOT NULL, class_label TEXT NOT NULL, payload TEXT NOT NULL, system_event_id TEXT);
CREATE INDEX IF NOT EXISTS idx_det_time ON detections(event_time_us);
CREATE TABLE IF NOT EXISTS system_events(system_event_id TEXT PRIMARY KEY, created_us INTEGER NOT NULL, event_type TEXT NOT NULL, payload TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_evt_time ON system_events(created_us);
CREATE TABLE IF NOT EXISTS security_events(event_id INTEGER PRIMARY KEY, station_id INTEGER NOT NULL, created_us INTEGER NOT NULL, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS commands(command_id TEXT PRIMARY KEY, station_id INTEGER NOT NULL, created_us INTEGER NOT NULL, command TEXT NOT NULL, payload TEXT NOT NULL, delivered INTEGER NOT NULL DEFAULT 0, acked INTEGER NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS idx_cmd_station ON commands(station_id, delivered, acked);
CREATE TABLE IF NOT EXISTS audio(event_id INTEGER NOT NULL, station_id INTEGER NOT NULL, segment TEXT NOT NULL, path TEXT NOT NULL, codec TEXT, sample_rate INTEGER, created_us INTEGER NOT NULL, PRIMARY KEY(event_id, station_id, segment));
"""

class EventStore:
    def __init__(self, path: Path):
        self.path=path; path.parent.mkdir(parents=True,exist_ok=True); self.lock=threading.RLock()
        with self._conn() as c: c.executescript(SCHEMA)
    def _conn(self):
        c=sqlite3.connect(self.path,timeout=10); c.row_factory=sqlite3.Row; return c
    def upsert_station(self, hb: HeartbeatMessage):
        payload=hb.model_dump_json()
        with self.lock,self._conn() as c: c.execute("INSERT OR REPLACE INTO stations VALUES(?,?,?)",(hb.station_id,hb.time_us,payload))
    def save_detection(self,d:DetectionMessage):
        with self.lock,self._conn() as c:
            c.execute("INSERT OR IGNORE INTO detections(event_id,station_id,event_time_us,class_label,payload) VALUES(?,?,?,?,?)",(d.event_id,d.station_id,d.event_time_us,d.classification.label,d.model_dump_json()))
    def recent_detections(self,center_us:int,window_us:int=3_000_000)->list[DetectionMessage]:
        with self._conn() as c:
            rows=c.execute("SELECT payload FROM detections WHERE event_time_us BETWEEN ? AND ? ORDER BY event_time_us",(center_us-window_us,center_us+window_us)).fetchall()
        return [DetectionMessage.model_validate_json(r['payload']) for r in rows]
    def link_detections(self,event_ids:list[int],system_event_id:str):
        with self.lock,self._conn() as c: c.executemany("UPDATE detections SET system_event_id=? WHERE event_id=?",[(system_event_id,e) for e in event_ids])
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
        return [json.loads(r['payload']) for r in rows]
    def create_command(self,station_id:int,command:str,payload:dict)->StationCommand:
        now=int(time.time()*1e6); cmd=StationCommand(command_id=str(uuid.uuid4()),station_id=station_id,command=command,payload=payload,created_time_us=now)
        with self.lock,self._conn() as c: c.execute("INSERT INTO commands(command_id,station_id,created_us,command,payload) VALUES(?,?,?,?,?)",(cmd.command_id,station_id,now,command,json.dumps(payload,ensure_ascii=False)))
        return cmd
    def poll_commands(self,station_id:int,limit:int=10)->list[StationCommand]:
        with self.lock,self._conn() as c:
            rows=c.execute("SELECT * FROM commands WHERE station_id=? AND delivered=0 ORDER BY created_us LIMIT ?",(station_id,limit)).fetchall()
            c.executemany("UPDATE commands SET delivered=1 WHERE command_id=?",[(r['command_id'],) for r in rows])
        return [StationCommand(command_id=r['command_id'],station_id=r['station_id'],command=r['command'],payload=json.loads(r['payload']),created_time_us=r['created_us']) for r in rows]
    def ack_command(self,command_id:str):
        with self.lock,self._conn() as c: c.execute("UPDATE commands SET acked=1 WHERE command_id=?",(command_id,))
    def cleanup(self,retention_days:int=365):
        cutoff=int((time.time()-retention_days*86400)*1e6)
        with self.lock,self._conn() as c:
            c.execute("DELETE FROM system_events WHERE created_us<?",(cutoff,)); c.execute("DELETE FROM detections WHERE event_time_us<?",(cutoff,)); c.execute("DELETE FROM security_events WHERE created_us<?",(cutoff,))
