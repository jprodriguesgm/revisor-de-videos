"""Etapa 6: vida do app empacotado (uma cópia só, fechar sozinho, Sair)."""
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from revisor import life

ROOT = Path(__file__).resolve().parent.parent


def test_fecha_sozinho_sem_pagina():
    t0 = 1000.0
    lf = life.Life(auto_exit=True)
    lf.started = lf.empty_since = t0
    assert not lf.should_exit(t0 + 60)                      # navegador ainda abrindo
    assert lf.should_exit(t0 + life.FIRST_S + 1)            # nunca abriu: fecha depois de 5 min


def test_pagina_aberta_segura_o_app():
    lf = life.Life(auto_exit=True)
    lf.ping("a")
    assert not lf.should_exit(time.time() + 600)            # aba em segundo plano por 10 min
    lf.bye("a")
    now = time.time()
    assert not lf.should_exit(now + 30)                     # recarregar a página não fecha
    assert lf.should_exit(now + life.GRACE_S + 1)


def test_aba_esquecida_sem_aviso_conta_como_fechada():
    lf = life.Life(auto_exit=True)
    lf.ping("a")
    lf.clients["a"] -= life.ALIVE_S + 1
    now = time.time()
    assert not lf.should_exit(now)                          # começa a contar agora
    assert lf.should_exit(now + life.GRACE_S + 1)


def test_analise_rodando_nao_fecha():
    lf = life.Life(auto_exit=True, busy=lambda: True)
    assert not lf.should_exit(time.time() + 10_000)


def test_sem_auto_exit_nunca_fecha():
    lf = life.Life(auto_exit=False)
    assert not lf.should_exit(time.time() + 10_000)


def test_instancia_morta_nao_conta(tmp_path):
    (tmp_path / life.INSTANCE_FILE).write_text(json.dumps({"port": 1, "pid": 1}), encoding="utf-8")
    assert life.running_url(tmp_path, timeout=0.3) is None
    assert life.running_url(tmp_path / "nada") is None


def _post(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=5) as r:
        return json.loads(r.read())


def test_segunda_copia_e_sair(tmp_path):
    env = dict(os.environ, REVISOR_HOME=str(tmp_path), PYTHONPATH=str(ROOT))
    cmd = [sys.executable, "-m", "revisor", "abrir", "--sem-navegador", "--porta", "8899", "--fechar-sozinho"]
    p = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        url = None
        for _ in range(100):
            url = life.running_url(tmp_path, timeout=0.3)
            if url:
                break
            time.sleep(0.1)
        assert url, "o app não abriu"
        assert _post(url + "api/ping", {"client": "t"})["packaged"] is True
        # segunda cópia: só aponta para a primeira e sai
        r = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=30)
        assert "já está aberto" in r.stdout
        assert _post(url + "api/quit", {})["ok"]
        p.wait(timeout=15)
        assert p.returncode == 0
        assert not (tmp_path / life.INSTANCE_FILE).exists()
    finally:
        if p.poll() is None:
            p.kill()
