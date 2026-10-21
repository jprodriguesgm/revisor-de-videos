"""Pastas e configurações do app (o que fica salvo entre uma revisão e outra).

Tudo fica numa pasta do usuário (não precisa de administrador):
  Mac:      ~/Library/Application Support/Revisor de Vídeos
  Windows:  %APPDATA%\\Revisor de Vídeos
  Linux:    ~/.local/share/revisor-de-videos
A variável REVISOR_HOME troca essa pasta (testes).

Dentro dela:
  configuracoes.json     escolhas da tela de início e das configurações
  lista_propria.txt      palavras aceitas na ortografia ("Aceitar")
  cache/                 análises (pode ser apagado; o app refaz)
  revisoes/              revisões salvas (nunca apagadas pelo "limpar cache")
"""
from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path

from . import nametag, speech

APP_NAME = "Revisor de Vídeos"

DEFAULTS = {
    "vinheta_in": None,              # caminho do arquivo da vinheta inicial
    "vinheta_out": None,             # caminho do arquivo da vinheta final
    "sensitivity": 55,
    "group_gap_s": 8.0,              # 0 = não juntar
    "spell": True,                   # conferir a ortografia do texto na tela
    "transcribe": True,              # transcrever as falas (Whisper local)
    "editors": [],                   # cada unidade cadastra a sua equipe em Configurações → Equipe
    "time_format": "seconds",        # seconds | ndf | df
    "srt_block_s": 3,
    "srt_prefix": "CORRIGIR:",
    "srt_where": "beside",           # beside | subfolder
    "cache_dir": None,               # None = <home>/cache
    "reviews_dir": None,             # None = <home>/revisoes
    "report_dir": None,              # outra pasta lida pelo relatório do mês (pacotes de outro computador)
    "export_dir": None,              # última pasta onde um pacote foi exportado
    "cache_auto_days": 30,           # apagar do cache o que não é usado há N dias (0 = nunca)
    "spell_en": True,                # inglês (EUA e Reino Unido) na ortografia
    "spell_la": True,                # latim na ortografia
    "nav_slides": False,             # revisão: ← → passam também por cada slide em tela cheia
    "clip_half_s": 4.0,              # revisão: trecho (V) com N s antes e N s depois do frame
    "last_folder": None,
    "tag_names": {},                 # professor → nome usado na tarja
    "history": {"professores": [], "cursos": [], "disciplinas": []},
    "error_phrases": list(speech.ERROR_PHRASES_DEFAULT),
    "generic_names": list(nametag.GENERIC_DEFAULT),
}

_lock = threading.Lock()


def home() -> Path:
    env = os.environ.get("REVISOR_HOME")
    if env:
        p = Path(env)
    elif sys.platform == "darwin":
        p = Path.home() / "Library" / "Application Support" / APP_NAME
    elif os.name == "nt":
        p = Path(os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming")) / APP_NAME
    else:
        p = Path(os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share")) / "revisor-de-videos"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _settings_path() -> Path:
    return home() / "configuracoes.json"


def load_settings() -> dict:
    data = {}
    try:
        data = json.loads(_settings_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    out = json.loads(json.dumps(DEFAULTS))     # cópia funda
    out.update({k: v for k, v in data.items() if k in DEFAULTS})
    for k in ("professores", "cursos", "disciplinas"):
        out["history"].setdefault(k, [])
    return out


def save_settings(data: dict) -> dict:
    with _lock:
        cur = load_settings()
        cur.update({k: v for k, v in data.items() if k in DEFAULTS})
        tmp = _settings_path().with_suffix(".tmp")
        tmp.write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(_settings_path())
        return cur


def cache_dir(settings: dict | None = None) -> Path:
    s = settings or load_settings()
    p = Path(s["cache_dir"]) if s.get("cache_dir") else home() / "cache"
    p.mkdir(parents=True, exist_ok=True)
    return p


def reviews_dir(settings: dict | None = None) -> Path:
    s = settings or load_settings()
    p = Path(s["reviews_dir"]) if s.get("reviews_dir") else home() / "revisoes"
    p.mkdir(parents=True, exist_ok=True)
    return p


def custom_words_file() -> Path:
    p = home() / "lista_propria.txt"
    if not p.exists():
        p.write_text("", encoding="utf-8")
    return p


def remember(kind: str, value: str | None, limit: int = 60) -> None:
    """Guarda professor/curso/disciplina para sugerir nas próximas revisões."""
    value = (value or "").strip()
    if not value:
        return
    s = load_settings()
    lst = [v for v in s["history"].get(kind, []) if v.lower() != value.lower()]
    lst.insert(0, value)
    s["history"][kind] = lst[:limit]
    save_settings({"history": s["history"]})


def active_editors(settings: dict | None = None) -> list[str]:
    s = settings or load_settings()
    return [e["name"] for e in s.get("editors", []) if e.get("active", True)]


def spell_langs(settings: dict | None = None) -> tuple:
    """Dicionários ligados: português sempre; inglês e latim pelas configurações."""
    s = settings or load_settings()
    langs = ["pt_BR"]
    if s.get("spell_en", True):
        langs += ["en_US", "en_GB"]
    if s.get("spell_la", True):
        langs.append("la")
    return tuple(langs)


def dir_size(p: Path) -> tuple[int, float]:
    """(bytes, modificação mais recente) de uma pasta."""
    total, newest = 0, 0.0
    for q in Path(p).rglob("*"):
        try:
            st = q.stat()
        except OSError:
            continue
        if q.is_file():
            total += st.st_size
        newest = max(newest, st.st_mtime)
    return total, newest
