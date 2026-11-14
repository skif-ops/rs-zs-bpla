"""Guard the production/bench storage boundary in the Ubuntu deployment."""
from pathlib import Path
import re


COMPOSE = Path(__file__).resolve().parents[1] / "deploy" / "compose.ubuntu.yml"


def service(name: str) -> str:
    text = COMPOSE.read_text(encoding="utf-8")
    match = re.search(rf"^  {re.escape(name)}:[ \t]*(?:#[^\n]*)?\n(.*?)(?=^  [a-z][a-z0-9_]*:|^volumes:|\Z)",
                      text, re.MULTILINE | re.DOTALL)
    assert match, f"missing compose service {name}"
    return match.group(1)


def test_bench_has_its_own_data_and_local_only_web_port():
    for name in ("bench_server", "mqtt_bridge_bench", "mqtt_alerts_bench"):
        block = service(name)
        assert 'profiles: ["bench"]' in block
        assert "- ../bench-data:/app/data" in block
        assert "- ../data:/app/data" not in block
        assert "bridge-bench.crt.pem" in block and "bridge-bench.key.pem" in block
        assert "- ./tls:/run/tls:ro" not in block
        assert "/run/tls/bridge.crt.pem" not in block
    for name in ("server", "mqtt_bridge_pilot1", "mqtt_bridge_pilot2", "mqtt_alerts"):
        assert "- ../data:/app/data" in service(name)
    assert '127.0.0.1:8001:8000' in service("bench_server")
    assert "- ../bench-output:/app/output" in service("bench_server")
    assert '"--tenants", "bench"' in service("mqtt_alerts_bench")
    assert '"--exclude-tenants", "bench"' in service("mqtt_alerts")
    assert '"--client-id", "dioneya-alerts-bench"' in service("mqtt_alerts_bench")
    assert "command-signing-bench.key" in service("mqtt_bridge_bench")
    assert "/run/tls/command-signing.key" not in service("mqtt_bridge_bench")
