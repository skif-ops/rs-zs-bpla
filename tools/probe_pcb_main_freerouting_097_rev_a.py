#!/usr/bin/env python3
"""Measurement-only Freerouting session on locked candidate 096 copper.

Only the 17 still-open signal nets retain pins in the DSN. All accepted
tracks/vias are exported as fixed obstacles; the native candidate is untouched.
"""
from __future__ import annotations
import hashlib,json,re,subprocess,sys,time,urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'hardware/kicad/candidates/PCB-ROUTING-P2-AUTOROUTE-097-PROBE'
DSN=OUT/'PROBE.dsn';INPUT=OUT/'PROBE_INPUT.dsn';SES=OUT/'PROBE.ses';LOG=OUT/'AUTOROUTE.json'
JAR=Path('/tmp/freerouting-2.4.1.jar')
JAR_URL='https://github.com/freerouting/freerouting/releases/download/v2.4.1/freerouting-2.4.1.jar'
JAR_SHA='251101c3eeac22d7e7dfcf6796603279e5d1000283eb82d8f093780f7afc6aa9'
OPEN={'AAD_CFG','ACCEL_INT','CELL_PWRKEY_CMD','CELL_RI_U16','CELL_STATUS_U16',
      'GNSS_TX_U1','LORA_SCK_U1','LSE_IN','PDM_DATA2','PWR_FAULT','REV_STRAP1',
      'SD_CK_U1','SD_D0_U1','SD_D1_U1','SIM2_DET','TEST_UART_RX_TP','USB_VBUS_SENSE'}

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def input_dsn():
    text=DSN.read_text()
    fixed=text.count('(type fix)')
    assert fixed>1000 and '(type route)' not in text
    for layer in ('In1.Cu','In2.Cu','In4.Cu'):
        old=f'    (layer {layer}\n      (type signal)'
        assert text.count(old)==1,layer
        text=text.replace(old,f'    (layer {layer}\n      (type power)')
    old='''      (circuit
        (use_via "Via[0-5]_600:300_um")
      )
      (rule
        (width 200)
        (clearance 200)
      )'''
    new='''      (circuit
        (use_via "Via[0-5]_250:150_um")
        (use_layer F.Cu In3.Cu B.Cu)
      )
      (rule
        (width 150)
        (clearance 200)
      )'''
    assert text.count(old)==1
    text=text.replace(old,new)
    a=text.index('  (network\n');b=text.index('  (wiring\n',a)
    network=text[a:b]
    pattern=re.compile(r'    \(net ([^\s()]+)\n      \(pins[^)]*\)\n    \)')
    found=set();removed=0
    def strip(match):
        nonlocal removed
        name=match.group(1);found.add(name)
        if name in OPEN:return match.group(0)
        removed+=1
        return f'    (net {name}\n      (pins)\n    )'
    network=pattern.sub(strip,network)
    assert OPEN<=found and removed>100,(OPEN-found,removed)
    text=text[:a]+network+text[b:]
    INPUT.write_text(text)
    return {'fixed_copper_items':fixed,'routed_nets':sorted(OPEN),'other_nets_without_pins':removed,
            'dsn_sha256':sha(DSN),'input_sha256':sha(INPUT)}

def main():
    prep=input_dsn()
    if not JAR.is_file():urllib.request.urlretrieve(JAR_URL,JAR)
    assert sha(JAR)==JAR_SHA
    started=time.monotonic()
    cmd=['java','-Xmx6g','-jar',str(JAR),'-de',str(INPUT),'-do',str(SES),'-mp','6',
         '--gui.enabled=false','--router.fanout.enabled=true','--router.optimizer.enabled=false',
         '--usage_and_diagnostic_data.disable_analytics=true']
    try:
        done=subprocess.run(cmd,capture_output=True,text=True,timeout=2400)
        rc=done.returncode;output=done.stdout+done.stderr
    except subprocess.TimeoutExpired as exc:
        rc='timeout';output=((exc.stdout or b'').decode(errors='replace')+
                             (exc.stderr or b'').decode(errors='replace'))
    (OUT/'FREEROUTING.log').write_text(output)
    info={'schema':'dioneya-pcb-main-autoroute-097-probe-v1','measurement_only':True,
          'base_candidate':96,'prep':prep,'router':'Freerouting 2.4.1','passes':6,
          'runtime_seconds':round(time.monotonic()-started,1),'rc':rc,
          'session_sha256':sha(SES) if SES.is_file() else None,
          'log_tail':[line[:240] for line in output.splitlines() if re.search(r'pass|unrouted|error|exception|stage',line,re.I)][-30:]}
    LOG.write_text(json.dumps(info,indent=2)+'\n')
    print(json.dumps({k:info[k] for k in ('rc','runtime_seconds','session_sha256','log_tail')},indent=2),flush=True)
    return 0 if SES.is_file() else 1
if __name__=='__main__':raise SystemExit(main())
