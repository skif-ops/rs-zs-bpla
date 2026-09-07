"""MQTT/TLS bridge with topic-to-payload station binding."""
from __future__ import annotations
import argparse, os, sys
import paho.mqtt.client as mqtt
from station.router import service
from station.schemas import DetectionMessage, HeartbeatMessage
from station.cbor_codec import decode_cbor, decode_detection_obj

def station_id_from_topic(topic: str, tenant: str) -> tuple[int, str]:
    parts=topic.split('/')
    if len(parts)!=5 or parts[0]!='zs' or parts[1]!='v1' or parts[2]!=tenant or parts[4] not in {'up','status'}:
        raise ValueError(f'unexpected topic: {topic}')
    return int(parts[3]),parts[4]

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--host',default=os.getenv('ZS_MQTT_HOST','localhost')); ap.add_argument('--port',type=int,default=int(os.getenv('ZS_MQTT_PORT','8883'))); ap.add_argument('--tenant',default=os.getenv('ZS_TENANT','default')); ap.add_argument('--ca',default=os.getenv('ZS_MQTT_CA')); ap.add_argument('--cert',default=os.getenv('ZS_MQTT_CERT')); ap.add_argument('--key',default=os.getenv('ZS_MQTT_KEY')); args=ap.parse_args()
    client=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    if args.ca: client.tls_set(ca_certs=args.ca,certfile=args.cert,keyfile=args.key)
    def on_connect(c,u,f,rc,p=None): c.subscribe(f'zs/v1/{args.tenant}/+/up',qos=1); c.subscribe(f'zs/v1/{args.tenant}/+/status',qos=1)
    def on_message(c,u,m):
        try:
            topic_station_id,kind=station_id_from_topic(m.topic,args.tenant)
            obj=decode_cbor(m.payload)
            if kind=='status':
                heartbeat=HeartbeatMessage.model_validate(obj)
                if heartbeat.station_id!=topic_station_id: raise ValueError('station_id mismatch between topic and heartbeat')
                from station.router import store; store.upsert_station(heartbeat)
            else:
                detection=decode_detection_obj(obj)
                if detection.station_id!=topic_station_id: raise ValueError('station_id mismatch between topic and detection')
                service.ingest(detection)
        except Exception as e: print(f'MQTT decode error: {e}',file=sys.stderr)
    client.on_connect=on_connect; client.on_message=on_message; client.connect(args.host,args.port,60); client.loop_forever()
if __name__=='__main__': main()
