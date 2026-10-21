"""Vida do app empacotado: uma cópia só, fechar sozinho e o botão "Sair".

O app não tem janela própria: é um servidor local + a página no navegador. Então:
- Abrir o app de novo (dois cliques) com ele já aberto só abre a página de novo
  (instancia.json na pasta do app guarda a porta).
- A página avisa que está aberta (/api/ping a cada 20 s) e se despede ao fechar
  (/api/bye). Sem nenhuma página aberta por 90 s, e sem análise rodando, o app fecha
  sozinho (no app empacotado; no "python3 -m revisor" só com --fechar-sozinho).
  Aba em segundo plano: o navegador espaça os avisos (até 1 por minuto), por isso a
  página só é dada como fechada depois de 20 min sem aviso.
- "Sair" na página fecha na hora (a análise que estiver rodando para e continua do
  ponto em que parou na próxima vez, pelo cache).
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.request
from pathlib import Path

ALIVE_S = 20 * 60      # sem aviso por mais que isso = página fechada
GRACE_S = 90           # tempo sem nenhuma página antes de fechar (recarregar a página não fecha)
FIRST_S = 5 * 60       # o navegador não abriu? espera isso antes de fechar
INSTANCE_FILE = "instancia.json"


class Life:
    def __init__(self, auto_exit: bool, busy=lambda: False, on_exit=None):
        self.auto_exit = auto_exit
        self.busy = busy
        self.on_exit = on_exit
        self.clients: dict[str, float] = {}
        self.started = time.time()
        self.empty_since: float | None = self.started
        self.ever = False
        self._lock = threading.Lock()
        self._stop = threading.Event()

    # ------------------------------------------------------------ página
    def ping(self, cid: str):
        with self._lock:
            self.clients[cid[:40] or "?"] = time.time()
            self.ever = True
            self.empty_since = None

    def bye(self, cid: str):
        with self._lock:
            self.clients.pop(cid[:40] or "?", None)
            if not self._alive():
                self.empty_since = time.time()

    def _alive(self) -> list[str]:
        now = time.time()
        for k in [k for k, t in self.clients.items() if now - t > ALIVE_S]:
            del self.clients[k]
        return list(self.clients)

    # ------------------------------------------------------------ fechar sozinho
    def should_exit(self, now: float | None = None) -> bool:
        if not self.auto_exit:
            return False
        now = now or time.time()
        with self._lock:
            if self._alive():
                self.empty_since = None
                return False
            if self.empty_since is None:
                self.empty_since = now
            wait = GRACE_S if self.ever else FIRST_S
            if now - self.empty_since < wait:
                return False
        try:
            if self.busy():
                return False
        except Exception:
            pass
        return True

    def watch(self, every: float = 15.0):
        def run():
            while not self._stop.wait(every):
                if self.should_exit():
                    self.exit()
                    return
        threading.Thread(target=run, name="vida", daemon=True).start()

    def exit(self):
        self._stop.set()
        if self.on_exit:
            self.on_exit()


# ---------------------------------------------------------------- uma cópia só

def instance_path(home: Path) -> Path:
    return home / INSTANCE_FILE


def running_url(home: Path, timeout: float = 1.5) -> str | None:
    """Endereço do app que já está aberto neste computador (ou None)."""
    p = instance_path(home)
    try:
        info = json.loads(p.read_text(encoding="utf-8"))
        port = int(info["port"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    url = f"http://127.0.0.1:{port}/"
    try:
        # sem proxy: numa rede com proxy (ex.: a da PUC) o 127.0.0.1 não pode passar por ele
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(url + "api/hello", timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
        if data.get("app") == "revisor":
            return url
    except Exception:
        pass
    return None


def write_instance(home: Path, port: int):
    try:
        home.mkdir(parents=True, exist_ok=True)
        instance_path(home).write_text(json.dumps({"port": port, "pid": os.getpid(),
                                                   "started": time.strftime("%Y-%m-%d %H:%M:%S")}),
                                       encoding="utf-8")
    except OSError:
        pass


def clear_instance(home: Path, port: int):
    p = instance_path(home)
    try:
        info = json.loads(p.read_text(encoding="utf-8"))
        if int(info.get("port", -1)) == port and int(info.get("pid", -1)) == os.getpid():
            p.unlink()
    except (OSError, ValueError, TypeError):
        pass
