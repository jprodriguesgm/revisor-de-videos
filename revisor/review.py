"""Revisão salva: os dados de um projeto (pasta de editados) que não podem se perder.

Fica em <revisoes>/<nome da pasta>/revisao.json e é salva sozinha a cada mudança.
Limpar o cache nunca apaga uma revisão.

Uma revisão por projeto: reabrir a mesma pasta (mesmo nome, em qualquer
caminho ou computador) continua a mesma revisão. O vídeo é identificado por
nome do arquivo + duração (o mesmo id do cache).
"""
from __future__ import annotations

import json
import re
import threading
import time
import unicodedata
from datetime import date, datetime
from pathlib import Path

REVIEW_VERSION = 1
_lock = threading.RLock()


def slug(name: str) -> str:
    """Nome de pasta seguro em Mac e Windows (mantém acentos; tira : / \\ etc.)."""
    n = unicodedata.normalize("NFC", name).strip()
    n = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "-", n)
    n = re.sub(r"\s+", " ", n).strip(" .-")
    return n[:80] or "revisao"


def project_key(folder_name: str) -> str:
    """Chave do projeto: o nome da pasta, comparável entre Mac e Windows."""
    n = unicodedata.normalize("NFKD", folder_name)
    n = "".join(c for c in n if not unicodedata.combining(c)).lower()
    return re.sub(r"\s+", " ", n).strip()


def now_text() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def new_review(folder: str | Path) -> dict:
    folder = Path(folder)
    return {
        "review_version": REVIEW_VERSION,
        "project": folder.name,
        "key": project_key(folder.name),
        "folder": str(folder),            # só neste computador; o pacote leva só os nomes
        "professor": "", "curso": "", "disciplina": "", "nome_tarja": "",
        "entrega": None,                  # "AAAA-MM-DD"
        "entrega_locked": False,
        "sensitivity": 55, "group_gap_s": 8.0,
        "report": None,                   # resumo do txt de tempo (números do txt)
        "videos": [],                     # [{id, file, duration, editor, comments, general, round}]
        "created": now_text(), "updated": now_text(),
    }


def general_of(v: dict) -> dict | None:
    """Comentário geral do vídeo (sem tempo: "aumentar o áudio geral", "ajustar a cor da pele")."""
    g = v.get("general")
    return g if isinstance(g, dict) and (g.get("text") or "").strip() else None


def comment_total(v: dict) -> int:
    """Comentários do vídeo: os de cada frame + o geral (se houver)."""
    return len(v.get("comments", []) or []) + (1 if general_of(v) else 0)


def path_for(reviews_root: Path, project: str) -> Path:
    return Path(reviews_root) / slug(project) / "revisao.json"


def find(reviews_root: Path, folder_name: str) -> dict | None:
    key = project_key(folder_name)
    p = path_for(reviews_root, folder_name)
    cands = [p] if p.exists() else []
    if not cands:   # nome com outra grafia (acento decomposto, maiúscula)
        for q in Path(reviews_root).glob("*/revisao.json"):
            try:
                if json.loads(q.read_text(encoding="utf-8")).get("key") == key:
                    cands.append(q)
                    break
            except (OSError, json.JSONDecodeError):
                continue
    for q in cands:
        try:
            return json.loads(q.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
    return None


def save(reviews_root: Path, rev: dict) -> Path:
    with _lock:
        rev["updated"] = now_text()
        p = path_for(reviews_root, rev["project"])
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(rev, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(p)
        return p


def list_saved(reviews_root: Path) -> list[dict]:
    out = []
    for q in Path(reviews_root).glob("*/revisao.json"):
        try:
            r = json.loads(q.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        out.append({
            "project": r.get("project"), "professor": r.get("professor"), "curso": r.get("curso"),
            "disciplina": r.get("disciplina"), "entrega": r.get("entrega"), "folder": r.get("folder"),
            "videos": len(r.get("videos", [])),
            "comments": sum(comment_total(v) for v in r.get("videos", [])),
            "updated": r.get("updated"),
        })
    out.sort(key=lambda x: x.get("updated") or "", reverse=True)
    return out


def merge_videos(rev: dict, found: list[dict]) -> None:
    """Atualiza a lista de vídeos com o que está na pasta, sem perder editor e comentários.

    found: [{id, file, duration}] na ordem da pasta. Vídeo da revisão que não está
    mais na pasta continua guardado (marcado "missing"), para não perder comentários.
    Vídeo novo com o MESMO NOME de um que saiu (voltou corrigido, outra duração) é a
    rodada seguinte: herda o editor e não conta de novo nas horas.
    """
    by_id = {v["id"]: v for v in rev.get("videos", [])}
    found_ids = {f["id"] for f in found}
    by_name = {}
    for v in rev.get("videos", []):
        if v["id"] not in found_ids:
            by_name[_name_key(v["file"])] = v
    out = []
    for f in found:
        v = by_id.pop(f["id"], None)
        if v is None:
            prev = by_name.get(_name_key(f["file"]))
            v = {"id": f["id"], "file": f["file"], "duration": f["duration"],
                 "editor": prev.get("editor") if prev else None,
                 "comments": [], "round": (int(prev.get("round") or 1) + 1) if prev else 1}
        v["file"], v["duration"] = f["file"], f["duration"]
        v.pop("missing", None)
        out.append(v)
    for v in by_id.values():
        v["missing"] = True
        out.append(v)
    rev["videos"] = out


def _name_key(file: str) -> str:
    n = unicodedata.normalize("NFKD", file)
    n = "".join(c for c in n if not unicodedata.combining(c)).lower()
    n = re.sub(r"\.(mp4|mov|m4v)$", "", n.strip())
    return re.sub(r"\s+", " ", n).strip(" -_.")


def suggest_professor(folder_name: str) -> str:
    """"Carlos 21:09" → "Carlos" (a pasta do editado leva o nome e a data/hora)."""
    n = re.sub(r"\s+\d{1,2}[:h.\-]\d{2}\s*$", "", folder_name.strip())
    n = re.sub(r"\s+\d{1,2}[/.\-]\d{1,2}([/.\-]\d{2,4})?\s*$", "", n)
    return n.strip(" -_")


def parse_date(text: str | None) -> str | None:
    """Aceita "07/10/2026" ou "2026-10-07" → "2026-10-07"."""
    if not text:
        return None
    text = text.strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d/%m/%y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def fmt_date(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        return date.fromisoformat(iso).strftime("%d/%m/%Y")
    except ValueError:
        return iso
