"""Colar o cartão do Planner (pedido do JP, 23/11/2026).

O JP copia o bloco "Preenchimento do professor" do cartão e cola no Início. O texto vem no formato
"Campo: valor", uma linha por campo, às vezes com marcas do Markdown do Planner ("> ###", links
"[texto](mailto:…)"). Daqui saem só os campos que o Revisor usa:

- "Nome que será utilizado na aula" → professor e nome na tarja (o mesmo nome das pastas);
  sem ele, o "Nome completo do professor";
- "Curso" e "Disciplina";
- "Data da gravação" → só para conferir com a data no nome da pasta ("AAAA MM DD Professor").

Telefone, e-mail, matrícula e os outros campos são ignorados e não ficam guardados.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date

EMPTY = {"", "-", "--", "nao sei", "não sei", "n/a", "na", "nenhum", "nenhuma", "sem", "nao", "não", "?"}

# rótulo do cartão (sem acento, minúsculo) → campo
LABELS = [
    (re.compile(r"^nome (que sera )?utilizado na aula$|^nome (para|na) (a )?aula$|^nome na tarja$"), "nome_aula"),
    (re.compile(r"^nome completo( do professor| da professora| do docente)?$|^nome do professor$|^professor$"),
     "nome_completo"),
    (re.compile(r"^curso$|^nome do curso$"), "curso"),
    (re.compile(r"^disciplina$|^nome da disciplina$"), "disciplina"),
    (re.compile(r"^data da gravacao$|^data de gravacao$|^gravacao$"), "data_gravacao"),
]


def _plain(s: str) -> str:
    n = unicodedata.normalize("NFKD", s)
    n = "".join(c for c in n if not unicodedata.combining(c)).lower()
    return re.sub(r"\s+", " ", n).strip()


def _clean_value(v: str) -> str:
    v = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", v)        # [texto](link) → texto
    v = re.sub(r"[*_`]+", "", v)                           # negrito / itálico do Markdown
    v = re.sub(r"\s+", " ", v).strip(" \t-–—:;")
    return v


def _clean_label(k: str) -> str:
    k = re.sub(r"^[\s>#*\-•·]+", "", k)                   # "> ###", marcadores de lista
    k = re.sub(r"[*_`]+", "", k)
    return _plain(k)


def parse_date(text: str | None) -> str | None:
    """"01/10/2026", "1/10/26", "2026-10-01" → "2026-10-01"."""
    if not text:
        return None
    t = text.strip()
    m = re.search(r"(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2,4})", t)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        y = y + 2000 if y < 100 else y
    else:
        m = re.search(r"(\d{4})[/.\-](\d{1,2})[/.\-](\d{1,2})", t)
        if not m:
            return None
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        return date(y, mo, d).isoformat()
    except ValueError:
        return None


def folder_date(folder_name: str | None) -> str | None:
    """Data no começo do nome da pasta: "2026 11 10 Maria Clara Souza" → "2026-11-10"."""
    if not folder_name:
        return None
    m = re.match(r"\s*(\d{4})[ ._\-](\d{1,2})[ ._\-](\d{1,2})(?!\d)", folder_name)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
    except ValueError:
        return None


def parse(text: str) -> dict:
    """Lê o bloco colado. Devolve os campos achados (None quando vazio ou "não sei")."""
    found: dict[str, str | None] = {}
    others: list[str] = []
    for raw in (text or "").splitlines():
        if ":" not in raw:
            continue
        k, v = raw.split(":", 1)
        label = _clean_label(k)
        if not label or len(label) > 60:
            continue
        field = next((f for rx, f in LABELS if rx.search(label)), None)
        if field is None:
            others.append(label)
            continue
        if field in found and found[field]:
            continue                                        # fica o primeiro preenchido
        val = _clean_value(v)
        found[field] = None if _plain(val) in EMPTY else val
    nome_aula, completo = found.get("nome_aula"), found.get("nome_completo")
    prof = nome_aula or completo
    out = {
        "professor": prof,
        "professor_from": "nome_aula" if nome_aula else ("nome_completo" if completo else None),
        "nome_tarja": nome_aula or completo,
        "curso": found.get("curso"),
        "disciplina": found.get("disciplina"),
        "data_gravacao": parse_date(found.get("data_gravacao")),
        "data_gravacao_text": found.get("data_gravacao"),
        "ignored": len(others),
    }
    out["ok"] = any(out[k] for k in ("professor", "curso", "disciplina", "data_gravacao"))
    return out


def check(card: dict, folder_name: str | None) -> dict:
    """Confere a data da gravação do cartão com a data no nome da pasta."""
    fd = folder_date(folder_name)
    cd = card.get("data_gravacao")
    res = {"folder_date": fd, "card_date": cd, "date_mismatch": bool(fd and cd and fd != cd)}
    return res
