"""SQLite persistence for stations, detections, events and commands."""
from __future__ import annotations
import json, os, sqlite3, threading, time, uuid
from pathlib import Path
from typing import Any
from station.schemas import DetectionMessage, HeartbeatMessage, SecurityEventMessage, StationCommand, SystemEvent

COMMAND_TTL_US = 15 * 60 * 1_000_000
ALERT_OUTBOX_DAYS = 30             # consumers catch up from the outbox within this time (dioneya.alert/1)

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS stations(station_id INTEGER PRIMARY KEY, updated_us INTEGER NOT NULL, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS detections(event_id INTEGER NOT NULL, station_id INTEGER NOT NULL, event_time_us INTEGER NOT NULL, class_label TEXT NOT NULL, payload TEXT NOT NULL, system_event_id TEXT, PRIMARY KEY(station_id, event_id));
CREATE INDEX IF NOT EXISTS idx_det_time ON detections(event_time_us);
CREATE INDEX IF NOT EXISTS idx_det_station ON detections(station_id, event_time_us);
CREATE TABLE IF NOT EXISTS system_events(system_event_id TEXT PRIMARY KEY, created_us INTEGER NOT NULL, event_type TEXT NOT NULL, payload TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_evt_time ON system_events(created_us);
CREATE TABLE IF NOT EXISTS security_events(event_id INTEGER NOT NULL, station_id INTEGER NOT NULL, created_us INTEGER NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(station_id, event_id));
CREATE TABLE IF NOT EXISTS mqtt_detection_ingress(event_key BLOB NOT NULL, station_id INTEGER NOT NULL, boot_id INTEGER NOT NULL, seq_no INTEGER NOT NULL, event_time_us INTEGER NOT NULL, wire_sha256 BLOB NOT NULL, processed INTEGER NOT NULL DEFAULT 0 CHECK(processed IN (0,1)), PRIMARY KEY(station_id, event_key));
CREATE TABLE IF NOT EXISTS commands(command_id TEXT PRIMARY KEY, station_id INTEGER NOT NULL, created_us INTEGER NOT NULL, expires_us INTEGER NOT NULL, command TEXT NOT NULL, payload TEXT NOT NULL, delivered INTEGER NOT NULL DEFAULT 0, acked INTEGER NOT NULL DEFAULT 0, last_publish_us INTEGER NOT NULL DEFAULT 0, publish_count INTEGER NOT NULL DEFAULT 0, ack_result INTEGER, ack_detail INTEGER, completed_us INTEGER);
CREATE INDEX IF NOT EXISTS idx_cmd_station ON commands(station_id, delivered, acked);
CREATE TABLE IF NOT EXISTS audio(event_id INTEGER NOT NULL, station_id INTEGER NOT NULL, segment TEXT NOT NULL, path TEXT NOT NULL, codec TEXT, sample_rate INTEGER, created_us INTEGER NOT NULL, PRIMARY KEY(event_id, station_id, segment));
CREATE TABLE IF NOT EXISTS bearings(station_id INTEGER NOT NULL, track_event_id INTEGER NOT NULL, time_us INTEGER NOT NULL, azimuth_cdeg INTEGER NOT NULL, elevation_cdeg INTEGER NOT NULL, sigma_cdeg INTEGER NOT NULL, confidence REAL NOT NULL, frames INTEGER NOT NULL, time_trust TEXT NOT NULL, received_us INTEGER NOT NULL, f0_dhz INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(station_id, track_event_id, time_us, f0_dhz));
CREATE INDEX IF NOT EXISTS idx_bearing_time ON bearings(time_us);
CREATE TABLE IF NOT EXISTS fused_tracks(track_id TEXT PRIMARY KEY, system_event_id TEXT, first_time_us INTEGER, last_time_us INTEGER, stations TEXT NOT NULL, points INTEGER NOT NULL, updated_us INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS idx_track_last ON fused_tracks(last_time_us);
CREATE TABLE IF NOT EXISTS track_members(station_id INTEGER NOT NULL, track_event_id INTEGER NOT NULL, track_id TEXT NOT NULL, segment_us INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(station_id, track_event_id, segment_us));
CREATE INDEX IF NOT EXISTS idx_member_track ON track_members(track_id);
CREATE TABLE IF NOT EXISTS track_points(track_id TEXT NOT NULL, time_us INTEGER NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(track_id, time_us));
CREATE TABLE IF NOT EXISTS alert_outbox(seq INTEGER PRIMARY KEY AUTOINCREMENT, msg_id TEXT NOT NULL UNIQUE, tenant TEXT NOT NULL, type TEXT NOT NULL, created_us INTEGER NOT NULL, message TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS alert_episodes(alert_id TEXT PRIMARY KEY, tenant TEXT NOT NULL, started_us INTEGER NOT NULL, last_activity_us INTEGER NOT NULL, level TEXT NOT NULL, stations TEXT NOT NULL, class TEXT NOT NULL, ended_us INTEGER);
CREATE INDEX IF NOT EXISTS idx_episode_open ON alert_episodes(tenant, ended_us);
CREATE TABLE IF NOT EXISTS alert_tracks(track_id TEXT PRIMARY KEY, alert_id TEXT NOT NULL, last_point_us INTEGER NOT NULL, ended_us INTEGER);
CREATE TABLE IF NOT EXISTS alert_cursors(consumer TEXT PRIMARY KEY, seq INTEGER NOT NULL, updated_us INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS station_tenants(station_id INTEGER PRIMARY KEY, tenant TEXT NOT NULL, updated_us INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS fusion_state(name TEXT PRIMARY KEY, value TEXT NOT NULL, updated_us INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS audio_parts(station_id INTEGER NOT NULL, command_id TEXT NOT NULL, segment INTEGER NOT NULL, chunk_index INTEGER NOT NULL, event_id INTEGER NOT NULL, chunk_count INTEGER NOT NULL, sample_rate INTEGER NOT NULL, start_time_us INTEGER NOT NULL, sha256 BLOB NOT NULL, data BLOB NOT NULL, received_us INTEGER NOT NULL, PRIMARY KEY(station_id, command_id, segment, chunk_index));
"""

class EventStore:
    def __init__(self, path: Path):
        self.path=path; path.parent.mkdir(parents=True,exist_ok=True); self.lock=threading.RLock(); self._tenant_seen={}
        with self._conn() as c:
            self._migrate_station_event_keys(c)
            self._migrate_track_segments(c)
            self._migrate_bearing_sources(c)
            c.executescript(SCHEMA)
            self._migrate_commands(c)
            self._migrate_audio(c)
        self.audio_root=path.parent/'audio'     # assembled segments: {audio_root}/{station}/{event}/{segment}.wav
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
    # event_id = boot_id<<32 | seq_no is unique within one station only (ICD): two stations with the same boot counter
    # and sequence number send equal event_id, so every table of station events is keyed by (station_id, event_id).
    _STATION_EVENT_TABLES={
        'detections':('event_id, station_id, event_time_us, class_label, payload, system_event_id',
                      ['CREATE INDEX IF NOT EXISTS idx_det_time ON detections(event_time_us)',
                       'CREATE INDEX IF NOT EXISTS idx_det_station ON detections(station_id, event_time_us)']),
        'security_events':('event_id, station_id, created_us, payload',[]),
        'mqtt_detection_ingress':('event_key, station_id, boot_id, seq_no, event_time_us, wire_sha256, processed',[]),
    }
    def _migrate_station_event_keys(self,c):
        """A database made before the per-station key had event_id (event_key) alone as the primary key; its rows are
        unique by event_id and therefore by (station_id, event_id) too, so they move into the new table as they are.
        All three tables move in one transaction (SQLite DDL is transactional): an interrupted migration leaves the old
        database as it was, and BEGIN IMMEDIATE keeps a second process from migrating at the same time."""
        def pending(table):
            info=c.execute(f"PRAGMA table_info({table})").fetchall()
            key='event_key' if table=='mqtt_detection_ingress' else 'event_id'
            return bool(info) and sorted(r['name'] for r in info if r['pk'])==[key]
        if not any(pending(t) for t in self._STATION_EVENT_TABLES): return
        level=c.isolation_level
        c.isolation_level=None                               # explicit transaction control
        try:
            c.execute("BEGIN IMMEDIATE")
            for table,(columns,indexes) in self._STATION_EVENT_TABLES.items():
                if not pending(table): continue              # re-checked inside the transaction
                definition=next(line for line in SCHEMA.splitlines() if line.startswith(f"CREATE TABLE IF NOT EXISTS {table}("))
                c.execute(f"ALTER TABLE {table} RENAME TO {table}_before_station_key")
                c.execute(definition.rstrip(';'))
                c.execute(f"INSERT INTO {table}({columns}) SELECT {columns} FROM {table}_before_station_key")
                c.execute(f"DROP TABLE {table}_before_station_key")
                for index in indexes: c.execute(index)
            c.execute("COMMIT")
        except BaseException:
            if c.in_transaction: c.execute("ROLLBACK")
            raise
        finally:
            c.isolation_level=level
    def _migrate_track_segments(self,c):
        """Fused tracks made before station tracks were split into segments (station/track_segments.py) had whole
        station tracks as members; such a member is the first segment of its track (segment_us 0), so its rows move as
        they are, in one transaction as above."""
        def pending():
            names={r['name'] for r in c.execute("PRAGMA table_info(track_members)")}
            return bool(names) and 'segment_us' not in names
        if not pending(): return
        level=c.isolation_level
        c.isolation_level=None
        try:
            c.execute("BEGIN IMMEDIATE")
            if pending():
                definition=next(line for line in SCHEMA.splitlines() if line.startswith("CREATE TABLE IF NOT EXISTS track_members("))
                c.execute("ALTER TABLE track_members RENAME TO track_members_before_segments")
                c.execute("DROP INDEX IF EXISTS idx_member_track")
                c.execute(definition.rstrip(';'))
                c.execute("INSERT INTO track_members(station_id,track_event_id,track_id,segment_us) "
                          "SELECT station_id,track_event_id,track_id,0 FROM track_members_before_segments")
                c.execute("DROP TABLE track_members_before_segments")
                c.execute("CREATE INDEX IF NOT EXISTS idx_member_track ON track_members(track_id)")
            c.execute("COMMIT")
        except BaseException:
            if c.in_transaction: c.execute("ROLLBACK")
            raise
        finally:
            c.isolation_level=level
    def _migrate_bearing_sources(self,c):
        """Bearings stored before a station could follow several sources at once (bearing batch schema 2) had one bearing
        per station track and time; the source's fundamental (f0_dhz, 0 = not known) joins the key, so the rows move as
        they are with f0_dhz 0, in one transaction as above."""
        def pending():
            names={r['name'] for r in c.execute("PRAGMA table_info(bearings)")}
            return bool(names) and 'f0_dhz' not in names
        if not pending(): return
        level=c.isolation_level
        c.isolation_level=None
        try:
            c.execute("BEGIN IMMEDIATE")
            if pending():
                definition=next(line for line in SCHEMA.splitlines() if line.startswith("CREATE TABLE IF NOT EXISTS bearings("))
                c.execute("ALTER TABLE bearings RENAME TO bearings_before_sources")
                c.execute("DROP INDEX IF EXISTS idx_bearing_time")
                c.execute(definition.rstrip(';'))
                cols="station_id,track_event_id,time_us,azimuth_cdeg,elevation_cdeg,sigma_cdeg,confidence,frames,time_trust,received_us"
                c.execute(f"INSERT INTO bearings({cols},f0_dhz) SELECT {cols},0 FROM bearings_before_sources")
                c.execute("DROP TABLE bearings_before_sources")
                c.execute("CREATE INDEX IF NOT EXISTS idx_bearing_time ON bearings(time_us)")
            c.execute("COMMIT")
        except BaseException:
            if c.in_transaction: c.execute("ROLLBACK")
            raise
        finally:
            c.isolation_level=level
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
    def _migrate_audio(self,c):
        columns={row['name'] for row in c.execute("PRAGMA table_info(audio)")}
        for name,definition in {'start_time_us':'INTEGER','sha256':'BLOB','command_id':'TEXT','duration_ms':'INTEGER'}.items():
            if name not in columns: c.execute(f"ALTER TABLE audio ADD COLUMN {name} {definition}")
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
    def note_station_tenant(self,station_id:int,tenant:str):
        """The tenant a station's messages came through (its MQTT bridge, or the HTTP bench): what a tenant-limited
        operator account may see (station/access_scope.py).  Written when it changes, not with every message."""
        if self._tenant_seen.get(station_id)==tenant: return
        with self.lock,self._conn() as c:
            c.execute("INSERT INTO station_tenants VALUES(?,?,?) ON CONFLICT(station_id) DO UPDATE SET tenant=excluded.tenant,"
                      "updated_us=excluded.updated_us WHERE tenant<>excluded.tenant",(station_id,tenant,int(time.time()*1e6)))
        self._tenant_seen[station_id]=tenant
    def station_tenants(self)->dict[int,str]:
        with self._conn() as c: return {r['station_id']:r['tenant'] for r in c.execute("SELECT station_id,tenant FROM station_tenants")}
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
            row=c.execute("SELECT station_id,boot_id,seq_no,event_time_us,wire_sha256,processed FROM mqtt_detection_ingress WHERE station_id=? AND event_key=?",(d.station_id,event_key)).fetchone()
            if row is not None:
                exact=(row['station_id']==d.station_id and row['boot_id']==d.boot_id and row['seq_no']==d.seq_no and row['event_time_us']==d.event_time_us and bytes(row['wire_sha256'])==wire_sha256)
                if not exact: return 'conflict'
                return 'duplicate' if row['processed'] else 'resume'
            existing=c.execute("SELECT 1 FROM detections WHERE station_id=? AND event_id=?",(d.station_id,self._sqlite_event_id(d.event_id))).fetchone()
            if existing is not None: return 'conflict'
            c.execute("INSERT INTO mqtt_detection_ingress(event_key,station_id,boot_id,seq_no,event_time_us,wire_sha256) VALUES(?,?,?,?,?,?)",(event_key,d.station_id,d.boot_id,d.seq_no,d.event_time_us,wire_sha256))
        return 'new'
    def complete_mqtt_detection(self,d:DetectionMessage,wire_sha256:bytes)->bool:
        event_key=self._event_key(d.event_id)
        with self.lock,self._conn() as c:
            result=c.execute("UPDATE mqtt_detection_ingress SET processed=1 WHERE station_id=? AND event_key=? AND boot_id=? AND seq_no=? AND event_time_us=? AND wire_sha256=?",(d.station_id,event_key,d.boot_id,d.seq_no,d.event_time_us,wire_sha256))
        return result.rowcount==1
    def recent_detections(self,center_us:int,window_us:int=3_000_000)->list[DetectionMessage]:
        with self._conn() as c:
            rows=c.execute("SELECT payload FROM detections WHERE event_time_us BETWEEN ? AND ? ORDER BY event_time_us",(center_us-window_us,center_us+window_us)).fetchall()
        return [DetectionMessage.model_validate_json(r['payload']) for r in rows]
    def detection_time_us(self,station_id:int,event_id:int)->int|None:
        with self._conn() as c:
            row=c.execute("SELECT event_time_us FROM detections WHERE event_id=? AND station_id=?",(self._sqlite_event_id(event_id),station_id)).fetchone()
        return row['event_time_us'] if row else None
    def link_detections(self,members:list[tuple[int,int]],system_event_id:str):
        """Link detections, given as (station_id, event_id) pairs, to a system event."""
        with self.lock,self._conn() as c: c.executemany("UPDATE detections SET system_event_id=? WHERE station_id=? AND event_id=?",[(system_event_id,s,self._sqlite_event_id(e)) for s,e in members])
    def save_system_event(self,e:SystemEvent):
        with self.lock,self._conn() as c: c.execute("INSERT OR REPLACE INTO system_events VALUES(?,?,?,?)",(e.system_event_id,e.created_time_us,e.event_type,e.model_dump_json()))
    def save_security(self,e:SecurityEventMessage):
        with self.lock,self._conn() as c: c.execute("INSERT OR REPLACE INTO security_events VALUES(?,?,?,?)",(e.event_id,e.station_id,e.event_time_us,e.model_dump_json()))
    # ``stations`` (a list, or None for all) limits a listing to what these stations took part in (access_scope.py)
    _IN_STATIONS="(SELECT value FROM json_each(?))"
    def list_events(self,limit:int=200,*,stations:list[int]|None=None)->list[dict[str,Any]]:
        where,args="",[]
        if stations is not None:
            where=f" WHERE EXISTS(SELECT 1 FROM json_each(payload,'$.source_station_ids') j WHERE j.value IN {self._IN_STATIONS})"
            args.append(json.dumps(stations))
        with self._conn() as c: rows=c.execute("SELECT payload FROM system_events"+where+" ORDER BY created_us DESC LIMIT ?",(*args,limit)).fetchall()
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
    # ---- bearing stream while tracking (ICD addendum H): live samples, idempotent on broker redelivery ----
    def save_bearings(self,batch,now_us:int|None=None)->int:
        """Stores the samples of a decoded BearingBatch; returns how many were new (a redelivered batch adds none)."""
        when=int(time.time()*1e6) if now_us is None else now_us
        track=self._sqlite_event_id(batch.track_event_id)
        rows=[(batch.station_id,track,s.time_us,round(s.azimuth_deg*100),round(s.elevation_deg*100),round(s.sigma_deg*100),s.confidence,s.frames,batch.time_trust,when,
               round(s.f0_hz*10) if s.f0_hz else 0)
              for s in batch.samples]
        with self.lock,self._conn() as c:
            before=c.total_changes
            c.executemany("INSERT OR IGNORE INTO bearings(station_id,track_event_id,time_us,azimuth_cdeg,elevation_cdeg,sigma_cdeg,confidence,frames,"
                          "time_trust,received_us,f0_dhz) VALUES(?,?,?,?,?,?,?,?,?,?,?)",rows)
            return c.total_changes-before
    def list_bearings(self,*,station_id:int|None=None,track_event_id:int|None=None,system_event_id:str|None=None,
                      since_us:int|None=None,until_us:int|None=None,limit:int=5000,stations:list[int]|None=None)->list[dict[str,Any]]:
        """Samples in time order with the system event their track's detection belongs to (None until correlated)."""
        where,args=[],[]
        if stations is not None: where.append(f"b.station_id IN {self._IN_STATIONS}"); args.append(json.dumps(stations))
        if station_id is not None: where.append("b.station_id=?"); args.append(station_id)
        if track_event_id is not None: where.append("b.track_event_id=?"); args.append(self._sqlite_event_id(track_event_id))
        if system_event_id is not None: where.append("d.system_event_id=?"); args.append(system_event_id)
        if since_us is not None: where.append("b.time_us>=?"); args.append(since_us)
        if until_us is not None: where.append("b.time_us<=?"); args.append(until_us)
        sql=("SELECT b.*,d.system_event_id FROM bearings b LEFT JOIN detections d ON d.event_id=b.track_event_id AND d.station_id=b.station_id"
             +(" WHERE "+" AND ".join(where) if where else "")+" ORDER BY b.time_us,b.station_id,b.f0_dhz LIMIT ?")
        with self._conn() as c: rows=c.execute(sql,(*args,max(1,min(limit,50000)))).fetchall()
        return [{'station_id':r['station_id'],'track_event_id':r['track_event_id']&0xFFFFFFFFFFFFFFFF,'system_event_id':r['system_event_id'],
                 'time_us':r['time_us'],'azimuth_deg':r['azimuth_cdeg']/100,'elevation_deg':r['elevation_cdeg']/100,'sigma_deg':r['sigma_cdeg']/100,
                 'confidence':r['confidence'],'frames':r['frames'],'time_trust':r['time_trust'],
                 'f0_hz':r['f0_dhz']/10 if r['f0_dhz'] else None} for r in rows]
    def get_detection(self,station_id:int,event_id:int)->DetectionMessage|None:
        with self._conn() as c:
            row=c.execute("SELECT payload FROM detections WHERE event_id=? AND station_id=?",(self._sqlite_event_id(event_id),station_id)).fetchone()
        return DetectionMessage.model_validate_json(row['payload']) if row else None
    def station_detections(self,station_id:int,since_us:int,until_us:int)->list[DetectionMessage]:
        with self._conn() as c:
            rows=c.execute("SELECT payload FROM detections WHERE station_id=? AND event_time_us BETWEEN ? AND ? ORDER BY event_time_us",(station_id,since_us,until_us)).fetchall()
        return [DetectionMessage.model_validate_json(r['payload']) for r in rows]
    def bearing_span(self,station_id:int,track_event_id:int)->tuple[int,int]|None:
        with self._conn() as c:
            row=c.execute("SELECT MIN(time_us) AS a,MAX(time_us) AS b FROM bearings WHERE station_id=? AND track_event_id=? AND time_us>0",(station_id,self._sqlite_event_id(track_event_id))).fetchone()
        return (row['a'],row['b']) if row and row['a'] is not None else None
    def system_event_of_detection(self,station_id:int,event_id:int)->str|None:
        with self._conn() as c:
            row=c.execute("SELECT system_event_id FROM detections WHERE event_id=? AND station_id=?",(self._sqlite_event_id(event_id),station_id)).fetchone()
        return row['system_event_id'] if row else None
    def bearing_tracks(self,since_us:int,until_us:int,trusted:tuple[str,...]=('GNSS_TIME_TRUSTED','HOLDOVER'))->list[dict[str,Any]]:
        """Station tracks with trusted-time bearings overlapping [since_us, until_us] (their segments and the fused
        tracks of the segments: station/track_hypotheses.py)."""
        marks=','.join('?'*len(trusted))
        with self._conn() as c:
            rows=c.execute(f"SELECT b.station_id,b.track_event_id,MIN(b.time_us) AS first_us,MAX(b.time_us) AS last_us,COUNT(*) AS samples "
                           f"FROM bearings b WHERE b.time_trust IN ({marks}) GROUP BY b.station_id,b.track_event_id "
                           f"HAVING MAX(b.time_us)>=? AND MIN(b.time_us)<=? ORDER BY first_us",(*trusted,since_us,until_us)).fetchall()
        return [{'station_id':r['station_id'],'track_event_id':r['track_event_id']&0xFFFFFFFFFFFFFFFF,'first_us':r['first_us'],'last_us':r['last_us'],
                 'samples':r['samples']} for r in rows]
    def latest_bearing_times(self,since_us:int,trusted:tuple[str,...]=('GNSS_TIME_TRUSTED','HOLDOVER'))->dict[int,int]:
        """The latest trusted bearing time of every station with bearings since since_us: {station_id: time_us}."""
        q=",".join("?"*len(trusted))
        with self._conn() as c:
            rows=c.execute(f"SELECT station_id,MAX(time_us) t FROM bearings WHERE time_us>=? AND time_trust IN ({q}) GROUP BY station_id",
                           (since_us,*trusted)).fetchall()
        return {r['station_id']:r['t'] for r in rows}
    def station_position(self,station_id:int,event_id:int|None=None)->tuple[float,float,float]|None:
        """(lat, lon, alt MSL) of a station: the (position-guarded) detection of the track, else its last heartbeat, else
        its latest detection."""
        if event_id is not None:
            with self._conn() as c:
                row=c.execute("SELECT payload FROM detections WHERE event_id=? AND station_id=?",(self._sqlite_event_id(event_id),station_id)).fetchone()
            if row is not None:
                st=DetectionMessage.model_validate_json(row['payload']).station
                if st.lat_e7 or st.lon_e7: return st.lat,st.lon,st.alt_m
        hb=self.get_station_heartbeat(station_id)
        if hb is not None and (hb.station.lat_e7 or hb.station.lon_e7): return hb.station.lat,hb.station.lon,hb.station.alt_m
        with self._conn() as c:        # no heartbeat yet: the station's latest detection
            row=c.execute("SELECT payload FROM detections WHERE station_id=? ORDER BY event_time_us DESC LIMIT 1",(station_id,)).fetchone()
        if row is not None:
            st=DetectionMessage.model_validate_json(row['payload']).station
            if st.lat_e7 or st.lon_e7: return st.lat,st.lon,st.alt_m
        return None
    # ---- fused tracks (bearing fusion of several stations, fusion/bearing_fusion.py) ----
    # A member of a fused track is a segment of a station track (station/track_segments.py): station, track event id
    # and the segment's key (0 for the first segment, else the time of its first bearing).
    def track_of_member(self,station_id:int,track_event_id:int,segment_us:int=0)->str|None:
        with self._conn() as c:
            row=c.execute("SELECT track_id FROM track_members WHERE station_id=? AND track_event_id=? AND segment_us=?",
                          (station_id,self._sqlite_event_id(track_event_id),segment_us)).fetchone()
        return row['track_id'] if row else None
    def segment_tracks(self,station_id:int,track_event_id:int)->dict[int,str]:
        """The fused track of every associated segment of a station track: {segment_us: track_id}."""
        with self._conn() as c:
            rows=c.execute("SELECT segment_us,track_id FROM track_members WHERE station_id=? AND track_event_id=?",
                           (station_id,self._sqlite_event_id(track_event_id))).fetchall()
        return {r['segment_us']:r['track_id'] for r in rows}
    def track_members(self,track_id:str)->list[tuple[int,int,int]]:
        with self._conn() as c:
            rows=c.execute("SELECT station_id,track_event_id,segment_us FROM track_members WHERE track_id=? ORDER BY station_id,track_event_id,segment_us",(track_id,)).fetchall()
        return [(r['station_id'],r['track_event_id']&0xFFFFFFFFFFFFFFFF,r['segment_us']) for r in rows]
    def add_track_member(self,track_id:str,station_id:int,track_event_id:int,segment_us:int=0):
        with self.lock,self._conn() as c:
            c.execute("INSERT OR IGNORE INTO track_members(station_id,track_event_id,track_id,segment_us) VALUES(?,?,?,?)",
                      (station_id,self._sqlite_event_id(track_event_id),track_id,segment_us))
    def remove_track_member(self,track_id:str,station_id:int,track_event_id:int,segment_us:int):
        with self.lock,self._conn() as c:
            c.execute("DELETE FROM track_members WHERE track_id=? AND station_id=? AND track_event_id=? AND segment_us=?",
                      (track_id,station_id,self._sqlite_event_id(track_event_id),segment_us))
    def replace_track(self,track_id:str,members:list[tuple[int,int,int]],system_event_id:str|None,points:list[dict],now_us:int|None=None):
        """Members are added (never moved); the points of the track are replaced by the fresh fusion result."""
        when=int(time.time()*1e6) if now_us is None else now_us
        stations=sorted({m[0] for m in members})
        with self.lock,self._conn() as c:
            c.executemany("INSERT OR IGNORE INTO track_members(station_id,track_event_id,track_id,segment_us) VALUES(?,?,?,?)",
                          [(s,self._sqlite_event_id(t),track_id,g) for s,t,g in members])
            c.execute("DELETE FROM track_points WHERE track_id=?",(track_id,))
            c.executemany("INSERT INTO track_points VALUES(?,?,?)",[(track_id,p['time_us'],json.dumps(p)) for p in points])
            c.execute("INSERT OR REPLACE INTO fused_tracks VALUES(?,?,?,?,?,?,?)",(track_id,system_event_id,points[0]['time_us'] if points else None,
                      points[-1]['time_us'] if points else None,json.dumps(stations),len(points),when))
    def set_track_members(self,track_id:str,members:list[tuple[int,int,int]]):
        """The track's members are these segments now: each is taken from any other track (a segment is in one track
        at a time); members it had before and not listed leave it."""
        with self.lock,self._conn() as c:
            c.execute("DELETE FROM track_members WHERE track_id=?",(track_id,))
            c.executemany("INSERT OR REPLACE INTO track_members(station_id,track_event_id,track_id,segment_us) VALUES(?,?,?,?)",
                          [(s,self._sqlite_event_id(t),track_id,g) for s,t,g in members])
    def append_track_points(self,track_id:str,system_event_id:str|None,points:list[dict],now_us:int|None=None):
        """New points of a track (a point of the same time replaces the stored one); the summary follows all points."""
        when=int(time.time()*1e6) if now_us is None else now_us
        with self.lock,self._conn() as c:
            c.executemany("INSERT OR REPLACE INTO track_points VALUES(?,?,?)",[(track_id,p['time_us'],json.dumps(p)) for p in points])
            row=c.execute("SELECT MIN(time_us) a,MAX(time_us) b,COUNT(*) n FROM track_points WHERE track_id=?",(track_id,)).fetchone()
            stations=sorted({s for (pl,) in c.execute("SELECT payload FROM track_points WHERE track_id=?",(track_id,))
                             for s in json.loads(pl).get('stations',[])})
            old=c.execute("SELECT system_event_id FROM fused_tracks WHERE track_id=?",(track_id,)).fetchone()
            sid=system_event_id or (old['system_event_id'] if old else None)
            c.execute("INSERT OR REPLACE INTO fused_tracks VALUES(?,?,?,?,?,?,?)",(track_id,sid,row['a'],row['b'],json.dumps(stations),row['n'],when))
    def fusion_state(self,name:str)->dict[str,Any]|None:
        with self._conn() as c:
            row=c.execute("SELECT value FROM fusion_state WHERE name=?",(name,)).fetchone()
        return json.loads(row['value']) if row else None
    def save_fusion_state(self,name:str,value:dict[str,Any]):
        with self.lock,self._conn() as c:
            c.execute("INSERT OR REPLACE INTO fusion_state VALUES(?,?,?)",(name,json.dumps(value),int(time.time()*1e6)))
    def _track_summary(self,r)->dict[str,Any]:
        return {'track_id':r['track_id'],'system_event_id':r['system_event_id'],'first_time_us':r['first_time_us'],'last_time_us':r['last_time_us'],
                'stations':json.loads(r['stations']),'points':r['points'],'updated_us':r['updated_us']}
    def list_tracks(self,*,since_us:int|None=None,until_us:int|None=None,system_event_id:str|None=None,limit:int=200,
                    stations:list[int]|None=None)->list[dict[str,Any]]:
        where,args=[],[]
        if stations is not None:
            where.append(f"EXISTS(SELECT 1 FROM json_each(fused_tracks.stations) j WHERE j.value IN {self._IN_STATIONS})"); args.append(json.dumps(stations))
        if since_us is not None: where.append("last_time_us>=?"); args.append(since_us)
        if until_us is not None: where.append("first_time_us<=?"); args.append(until_us)
        if system_event_id is not None: where.append("system_event_id=?"); args.append(system_event_id)
        sql="SELECT * FROM fused_tracks"+(" WHERE "+" AND ".join(where) if where else "")+" ORDER BY first_time_us DESC LIMIT ?"
        with self._conn() as c: rows=c.execute(sql,(*args,max(1,min(limit,2000)))).fetchall()
        return [self._track_summary(r) for r in rows]
    def get_track(self,track_id:str)->dict[str,Any]|None:
        with self._conn() as c:
            row=c.execute("SELECT * FROM fused_tracks WHERE track_id=?",(track_id,)).fetchone()
            if row is None: return None
            pts=c.execute("SELECT payload FROM track_points WHERE track_id=? ORDER BY time_us",(track_id,)).fetchall()
        out=self._track_summary(row)
        out['members']=[{'station_id':s,'track_event_id':t,'segment_us':g} for s,t,g in self.track_members(track_id)]
        out['track_points']=[json.loads(p['payload']) for p in pts]
        return out
    # ---- output API dioneya.alert/1 (integration/): the outbox every consumer reads by seq, alert episodes, tracks ----
    def append_alert(self,msg_id:str,tenant:str,msg_type:str,created_us:int,message:dict)->int|None:
        """Append a message once (msg_id is unique): its seq, or None when it was appended before."""
        with self.lock,self._conn() as c:
            cur=c.execute("INSERT OR IGNORE INTO alert_outbox(msg_id,tenant,type,created_us,message) VALUES(?,?,?,?,?)",
                          (msg_id,tenant,msg_type,created_us,json.dumps(message,ensure_ascii=False,separators=(',',':'))))
            return cur.lastrowid if cur.rowcount else None
    def list_alerts(self,after_seq:int=0,*,tenant:str|None=None,limit:int=500,until_seq:int|None=None,
                    tenants:list[str]|None=None)->list[dict[str,Any]]:
        """Messages after a seq (up to until_seq), oldest first, with their seq (``tenants``: only of these)."""
        where,args=["seq>?"],[after_seq]
        if until_seq is not None: where.append("seq<=?"); args.append(until_seq)
        if tenant: where.append("tenant=?"); args.append(tenant)
        if tenants is not None: where.append("tenant IN (SELECT value FROM json_each(?))"); args.append(json.dumps(tenants))
        with self._conn() as c:
            rows=c.execute("SELECT seq,message FROM alert_outbox WHERE "+" AND ".join(where)+" ORDER BY seq LIMIT ?",(*args,limit)).fetchall()
        return [{**json.loads(r['message']),'seq':r['seq']} for r in rows]
    def read_alerts(self,after_seq:int,*,tenant:str|None=None,limit:int=500,tenants:list[str]|None=None,
                    keep=None)->tuple[list[dict[str,Any]],int]:
        """A page of messages and the seq to continue after: past every message this read could see, also those of
        other tenants (the outbox's last seq is read first, so nothing appended meanwhile is skipped).  ``keep`` (a
        message -> message or None) is what an operator account may see of each (access_scope.py): the page is
        filled up from later messages, and the cursor still passes the ones it dropped."""
        upto=self.last_alert_seq()
        out,cursor=[],max(after_seq,0)
        while len(out)<limit and cursor<upto:
            page=self.list_alerts(cursor,tenant=tenant,limit=limit,until_seq=upto,tenants=tenants)
            if not page: cursor=upto; break
            for m in page:
                cursor=m['seq']
                kept=m if keep is None else keep(m)
                if kept is not None:
                    out.append(kept)
                    if len(out)>=limit: break
            if len(page)<limit and len(out)<limit: cursor=upto
        return out,(cursor if len(out)>=limit else max(upto,after_seq))
    def last_alert_seq(self)->int:
        with self._conn() as c: row=c.execute("SELECT MAX(seq) FROM alert_outbox").fetchone()
        return row[0] or 0
    def open_episode(self,tenant:str)->dict[str,Any]|None:
        with self._conn() as c:
            row=c.execute("SELECT * FROM alert_episodes WHERE tenant=? AND ended_us IS NULL ORDER BY started_us DESC LIMIT 1",(tenant,)).fetchone()
        return self._episode(row) if row else None
    def get_episode(self,alert_id:str)->dict[str,Any]|None:
        with self._conn() as c: row=c.execute("SELECT * FROM alert_episodes WHERE alert_id=?",(alert_id,)).fetchone()
        return self._episode(row) if row else None
    @staticmethod
    def _episode(r)->dict[str,Any]:
        return {'alert_id':r['alert_id'],'tenant':r['tenant'],'started_us':r['started_us'],'last_activity_us':r['last_activity_us'],
                'level':r['level'],'stations':json.loads(r['stations']),'class':json.loads(r['class']),'ended_us':r['ended_us']}
    def save_episode(self,e:dict[str,Any]):
        with self.lock,self._conn() as c:
            c.execute("INSERT OR REPLACE INTO alert_episodes VALUES(?,?,?,?,?,?,?,?)",(e['alert_id'],e['tenant'],e['started_us'],e['last_activity_us'],
                      e['level'],json.dumps(e['stations']),json.dumps(e['class']),e['ended_us']))
    def alert_track(self,track_id:str)->dict[str,Any]|None:
        with self._conn() as c: row=c.execute("SELECT * FROM alert_tracks WHERE track_id=?",(track_id,)).fetchone()
        return dict(row) if row else None
    def save_alert_track(self,track_id:str,alert_id:str,last_point_us:int,ended_us:int|None=None):
        with self.lock,self._conn() as c: c.execute("INSERT OR REPLACE INTO alert_tracks VALUES(?,?,?,?)",(track_id,alert_id,last_point_us,ended_us))
    def open_alert_tracks(self,alert_id:str)->list[dict[str,Any]]:
        """Tracks of an alert not ended yet, with the wall time their fusion was last updated."""
        with self._conn() as c:
            rows=c.execute("SELECT a.track_id,a.alert_id,a.last_point_us,a.ended_us,t.updated_us FROM alert_tracks a JOIN fused_tracks t ON t.track_id=a.track_id "
                           "WHERE a.alert_id=? AND a.ended_us IS NULL",(alert_id,)).fetchall()
        return [dict(r) for r in rows]
    def alert_tracks_of(self,alert_id:str)->list[str]:
        with self._conn() as c: rows=c.execute("SELECT track_id FROM alert_tracks WHERE alert_id=? ORDER BY track_id",(alert_id,)).fetchall()
        return [r['track_id'] for r in rows]
    def alert_cursor(self,consumer:str)->int|None:
        with self._conn() as c: row=c.execute("SELECT seq FROM alert_cursors WHERE consumer=?",(consumer,)).fetchone()
        return row['seq'] if row else None
    def set_alert_cursor(self,consumer:str,seq:int,now_us:int|None=None):
        with self.lock,self._conn() as c:
            c.execute("INSERT OR REPLACE INTO alert_cursors VALUES(?,?,?)",(consumer,seq,int(time.time()*1e6) if now_us is None else now_us))
    # ---- audio upload over MQTT (ICD addendum B): chunks stay here until their segment is complete ----
    def command_record(self,command_id:str)->dict[str,Any]|None:
        with self._conn() as c:
            row=c.execute("SELECT station_id,command,payload,acked,ack_result,ack_detail,created_us FROM commands WHERE command_id=?",(command_id,)).fetchone()
        if row is None: return None
        return {'station_id':row['station_id'],'command':row['command'],'payload':json.loads(row['payload']),'acked':bool(row['acked']),
                'ack_result':row['ack_result'],'ack_detail':row['ack_detail'],'created_us':row['created_us']}
    def acked_key_rotation(self,station_id:int)->tuple[str,int]|None:
        """The newest CMD_ROTATE_COMMAND_KEY the station acknowledged OK: (public key hex, completed time, station clock)."""
        with self._conn() as c:
            row=c.execute("SELECT payload,completed_us FROM commands WHERE station_id=? AND command='CMD_ROTATE_COMMAND_KEY' AND acked=1 AND ack_result=0 ORDER BY completed_us DESC LIMIT 1",(station_id,)).fetchone()
        return (json.loads(row['payload'])['public_key'],row['completed_us']) if row else None
    def last_command_us(self,station_id:int,command:str)->int|None:
        with self._conn() as c:
            row=c.execute("SELECT MAX(created_us) AS t FROM commands WHERE station_id=? AND command=?",(station_id,command)).fetchone()
        return row['t'] if row and row['t'] is not None else None
    def add_audio_part(self,*,station_id:int,command_id:str,segment:int,segment_name:str,chunk_index:int,chunk_count:int,event_id:int,
                       sample_rate:int,start_time_us:int,sha256:bytes,data:bytes,now_us:int,max_pending_parts:int)->tuple[str,list[bytes]|None]:
        """'already' (segment stored before), 'duplicate' (part seen), 'stored', or 'complete' with the parts in order.
        Parts whose segment metadata changed (the station selected the segment again after a lost session) replace
        the old ones."""
        eid=self._sqlite_event_id(event_id)
        meta=(eid,chunk_count,sample_rate,start_time_us,sha256)
        with self.lock,self._conn() as c:
            done=c.execute("SELECT sha256 FROM audio WHERE event_id=? AND station_id=? AND segment=?",(eid,station_id,segment_name)).fetchone()
            if done is not None and done['sha256']==sha256: return 'already',None
            key=(station_id,command_id,segment)
            first=c.execute("SELECT event_id,chunk_count,sample_rate,start_time_us,sha256 FROM audio_parts WHERE station_id=? AND command_id=? AND segment=? LIMIT 1",key).fetchone()
            if first is not None and tuple(first)!=meta:
                c.execute("DELETE FROM audio_parts WHERE station_id=? AND command_id=? AND segment=?",key)
            pending=c.execute("SELECT COUNT(*) FROM audio_parts WHERE station_id=?",(station_id,)).fetchone()[0]
            if pending>=max_pending_parts: raise ValueError('too many pending audio parts for the station')
            inserted=c.execute("INSERT OR IGNORE INTO audio_parts VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                               (station_id,command_id,segment,chunk_index,eid,chunk_count,sample_rate,start_time_us,sha256,data,now_us)).rowcount
            if not inserted: return 'duplicate',None
            rows=c.execute("SELECT data FROM audio_parts WHERE station_id=? AND command_id=? AND segment=? ORDER BY chunk_index",key).fetchall()
        if len(rows)<chunk_count: return 'stored',None
        return 'complete',[bytes(r['data']) for r in rows]
    def drop_audio_parts(self,station_id:int,command_id:str,segment:int):
        with self.lock,self._conn() as c: c.execute("DELETE FROM audio_parts WHERE station_id=? AND command_id=? AND segment=?",(station_id,command_id,segment))
    def complete_audio_segment(self,*,station_id:int,command_id:str,segment:int,segment_name:str,event_id:int,path:str,sample_rate:int,
                               start_time_us:int,sha256:bytes,duration_ms:int,now_us:int):
        """The WAV is on disk: record it and drop the parts in one transaction (a crash before this replays the last part)."""
        with self.lock,self._conn() as c:
            c.execute("INSERT OR REPLACE INTO audio(event_id,station_id,segment,path,codec,sample_rate,created_us,start_time_us,sha256,command_id,duration_ms) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                      (self._sqlite_event_id(event_id),station_id,segment_name,path,'pcm16-wav',sample_rate,now_us,start_time_us,sha256,command_id,duration_ms))
            c.execute("DELETE FROM audio_parts WHERE station_id=? AND command_id=? AND segment=?",(station_id,command_id,segment))
    def list_audio(self,station_id:int,event_id:int)->list[dict[str,Any]]:
        with self._conn() as c:
            rows=c.execute("SELECT segment,path,codec,sample_rate,created_us,start_time_us,duration_ms,command_id FROM audio WHERE station_id=? AND event_id=? ORDER BY segment DESC",
                           (station_id,self._sqlite_event_id(event_id))).fetchall()
        return [dict(r) for r in rows]
    def audio_upload_progress(self,station_id:int,command_id:str)->dict[int,tuple[int,int]]:
        """segment -> (parts received, chunk_count) of an unfinished upload."""
        with self._conn() as c:
            rows=c.execute("SELECT segment,COUNT(*) AS n,MAX(chunk_count) AS total FROM audio_parts WHERE station_id=? AND command_id=? GROUP BY segment",(station_id,command_id)).fetchall()
        return {r['segment']:(r['n'],r['total']) for r in rows}
    def cleanup(self,retention_days:int=365):
        cutoff=int((time.time()-retention_days*86400)*1e6)
        with self.lock,self._conn() as c:
            c.execute("DELETE FROM audio_parts WHERE received_us<?",(int((time.time()-2*86400)*1e6),))   # abandoned uploads
            c.execute("DELETE FROM bearings WHERE time_us<?",(cutoff,))
            c.execute("DELETE FROM track_points WHERE time_us<?",(cutoff,)); c.execute("DELETE FROM fused_tracks WHERE last_time_us<?",(cutoff,))
            c.execute("DELETE FROM track_members WHERE track_id NOT IN (SELECT track_id FROM fused_tracks)")
            c.execute("DELETE FROM alert_outbox WHERE created_us<?",(int((time.time()-ALERT_OUTBOX_DAYS*86400)*1e6),))
            c.execute("DELETE FROM alert_tracks WHERE track_id NOT IN (SELECT track_id FROM fused_tracks)")
            c.execute("DELETE FROM alert_episodes WHERE ended_us<?",(cutoff,))
            c.execute("DELETE FROM system_events WHERE created_us<?",(cutoff,)); c.execute("DELETE FROM detections WHERE event_time_us<?",(cutoff,)); c.execute("DELETE FROM security_events WHERE created_us<?",(cutoff,))
