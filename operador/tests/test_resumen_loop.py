import os
import signal
import subprocess
import time
from pathlib import Path

LOOP = Path(__file__).resolve().parents[1] / "resumen-loop.sh"


def test_loop_relaunches_after_failures(tmp_path):
    marks = tmp_path / "marks"
    fake = tmp_path / "fake-server.sh"
    fake.write_text(f"#!/bin/sh\necho x >> {marks}\nexit 1\n")
    fake.chmod(0o755)
    env = dict(os.environ, RESUMEN_CMD=str(fake), RESUMEN_PAUSA="0.1")
    # Igual que en start.sh: el bucle corre en un shell con set -e
    proc = subprocess.Popen(["sh", "-c", f"set -e; sh {LOOP}"], env=env, start_new_session=True)
    time.sleep(1.2)
    os.killpg(proc.pid, signal.SIGTERM)
    proc.wait(5)
    assert len(marks.read_text().splitlines()) >= 3  # siguió relanzando aunque el servidor salió con error


def test_start_sh_uses_the_loop_script():
    start = (Path(__file__).resolve().parents[1] / "start.sh").read_text()
    assert "resumen-loop.sh" in start and "resumen.py; sleep" not in start
