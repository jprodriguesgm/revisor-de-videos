"""Conferir correções da rodada anterior (pedido do JP, 22/10).

Quando um vídeo volta corrigido, o JP quer ver só os comentários que fez antes, com o frame antigo ao
lado do frame novo no mesmo ponto, e marcar "corrigido" / "não corrigido".

- Comentário da rodada anterior:
  · do mesmo vídeo (mesmo nome e duração), feito ANTES de o arquivo atual ser salvo (data do arquivo);
  · ou de uma versão que saiu da pasta (outra duração = rodada seguinte) com o mesmo nome.
- O ponto equivalente no vídeo novo é achado pelo ÁUDIO: cada comentário guarda, ao ser criado, o volume
  de ±8 s em volta dele ("afp", janelas de 0,1 s). No vídeo novo, procura onde esse trecho de volume se
  repete (correlação). Se o editor cortou alguma coisa antes, o tempo muda e o app acompanha.
  Comentário sem "afp" (de antes desta versão) ou trecho não achado: mesmo tempo, marcado "aproximado".
- A imagem antiga vem de uma cópia do frame guardada junto da revisão quando o comentário é criado
  (o cache do vídeo é apagado quando ele é analisado de novo).
"""
from __future__ import annotations

import time
import unicodedata

import numpy as np

AFP_HALF_S = 8.0          # trecho de áudio guardado em volta do comentário (cada lado)
SEARCH_S = 180.0          # procura até 3 min antes/depois do tempo antigo
MIN_CORR = 0.6            # correlação mínima para aceitar a posição achada


def _ts(text: str | None) -> float | None:
    try:
        return time.mktime(time.strptime(str(text), "%Y-%m-%d %H:%M:%S"))
    except (ValueError, OverflowError, TypeError):
        return None


def _name_key(file: str) -> str:
    n = unicodedata.normalize("NFKD", file or "")
    n = "".join(c for c in n if not unicodedata.combining(c)).lower()
    for ext in (".mp4", ".mov", ".m4v"):
        if n.endswith(ext):
            n = n[: -len(ext)]
    return " ".join(n.split()).strip(" -_.")


def fingerprint(analysis: dict | None, seconds: float) -> dict | None:
    """Volume (dB por 0,1 s) de ±8 s em volta do comentário."""
    au = (analysis or {}).get("audio") or {}
    env = au.get("envelope_db") or []
    step = float(au.get("envelope_step") or 0.1)
    if not env:
        return None
    i0 = max(0, int((seconds - AFP_HALF_S) / step))
    i1 = min(len(env), int((seconds + AFP_HALF_S) / step) + 1)
    if i1 - i0 < 20:
        return None
    return {"t0": round(i0 * step, 3), "t": round(seconds, 3), "step": step, "env": [int(x) for x in env[i0:i1]]}


def map_time(afp: dict | None, analysis: dict | None) -> tuple[float, float] | None:
    """(tempo no vídeo novo, correlação) do trecho guardado; None se não achou com segurança."""
    au = (analysis or {}).get("audio") or {}
    env = np.asarray(au.get("envelope_db") or [], np.float32)
    if not afp or env.size == 0 or abs(float(au.get("envelope_step") or 0.1) - afp["step"]) > 1e-6:
        return None
    pat = np.asarray(afp["env"], np.float32)
    L = pat.size
    if env.size < L or L < 20:
        return None
    step = afp["step"]
    lo = max(0, int((afp["t0"] - SEARCH_S) / step))
    hi = min(env.size - L, int((afp["t0"] + SEARCH_S) / step))
    if hi < lo:
        lo, hi = 0, env.size - L
    p = pat - pat.mean()
    pn = float(np.sqrt((p * p).sum()))
    if pn < 1e-3:                       # trecho todo em silêncio: não dá para achar
        return None
    win = np.lib.stride_tricks.sliding_window_view(env, L)[lo:hi + 1]
    w = win - win.mean(axis=1, keepdims=True)
    wn = np.sqrt((w * w).sum(axis=1))
    corr = (w @ p) / np.maximum(wn * pn, 1e-6)
    best = float(corr.max())
    if best < MIN_CORR:
        return None
    # fala com ritmo parecido pode "bater" em mais de um lugar: entre os quase iguais ao melhor, fica o
    # mais perto do tempo antigo (o editor costuma mexer pouco)
    near = np.flatnonzero(corr >= best - 0.03)
    k = int(near[np.argmin(np.abs((lo + near) * step - afp["t0"]))])
    c = float(corr[k])
    return (lo + k) * step + (afp["t"] - afp["t0"]), c


def previous_comments(rev: dict, v: dict, analysis: dict | None) -> list[tuple[dict, dict]]:
    """[(vídeo de onde veio, comentário)] da rodada anterior deste vídeo."""
    out = []
    mt = ((analysis or {}).get("source") or {}).get("mtime")
    if mt:
        for c in v.get("comments", []) or []:
            ct = _ts(c.get("created"))
            if ct is not None and ct < float(mt) - 60:
                out.append((v, c))
    key = _name_key(v.get("file", ""))
    for x in rev.get("videos", []):
        if x is v or not x.get("missing") or _name_key(x.get("file", "")) != key:
            continue
        if int(x.get("round") or 1) >= int(v.get("round") or 1):
            continue
        out += [(x, c) for c in x.get("comments", []) or []]
    out.sort(key=lambda p: (int(p[0].get("round") or 1), int(p[1].get("frame") or 0)))
    return out
