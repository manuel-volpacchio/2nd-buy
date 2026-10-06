"""
FASE 7 - Ensambla todos los fragmentos JSON en un unico payload para el dashboard.
"""
import json
import time
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PIPELINE_DIR.parent
OUT_JSON = PROJECT_DIR / "rebuy_data_v2.json"


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def load(name):
    p = PIPELINE_DIR / f"_fragment_{name}.json"
    return json.loads(p.read_text(encoding="utf-8"))


def main():
    payload = {
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "version": "v2_app_loyalty_payments_economics_cs",
    }
    payload["descriptive"] = load("descriptive")
    payload["survival"] = load("survival")
    payload["modeling"] = load("modeling")
    payload["legacy"] = load("legacy")

    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    log(f"Guardado {OUT_JSON} ({OUT_JSON.stat().st_size/1024:.1f} KB)")


if __name__ == "__main__":
    main()
