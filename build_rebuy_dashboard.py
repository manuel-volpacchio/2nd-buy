"""
Orquestador del pipeline REBUY v2 (con App, Loyalty, Payments, Economics y
Customer Service). Corre en orden los scripts de pipeline/ y deja
rebuy_data_v2.json listo para rebuy_dashboard.html.

Uso:
    python build_rebuy_dashboard.py             # usa cache si existe
    python build_rebuy_dashboard.py --rebuild    # fuerza reprocesar los CSV crudos
                                                   (usar cuando hay archivos mensuales nuevos)

Ver pipeline/*.py para el detalle de cada fase, y INFORME_METODOLOGICO.md para
las decisiones metodologicas (target multi-horizonte, leakage, censura, etc.).
"""
import subprocess
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PIPELINE_DIR = BASE_DIR / "pipeline"

STEPS = [
    "01_build_base_tables.py",
    "02_build_modeling_view.py",
    "03_descriptive_cohorts.py",
    "04_survival.py",
    "05_modeling.py",
    "06_legacy_extras.py",
    "07_assemble.py",
]


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def main():
    rebuild = "--rebuild" in sys.argv
    for step in STEPS:
        args = [sys.executable, str(PIPELINE_DIR / step)]
        if rebuild and step == "01_build_base_tables.py":
            args.append("--rebuild")
        log(f"=== {step} ===")
        result = subprocess.run(args, cwd=str(PIPELINE_DIR))
        if result.returncode != 0:
            log(f"FALLO en {step} (exit code {result.returncode}). Deteniendo pipeline.")
            sys.exit(result.returncode)
    log("Pipeline completo. Ver rebuy_data_v2.json y rebuy_dashboard.html")


if __name__ == "__main__":
    main()
