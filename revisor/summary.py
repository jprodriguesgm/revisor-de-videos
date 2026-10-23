"""Números e listas que as telas mostram, tirados de uma análise do cache.

Separa o que é "frame marcado" (texto que entrou, lista, slide que mudou),
"corte" (fica na linha do tempo) e "aviso" (algo para conferir).
"""
from __future__ import annotations

import re
import unicodedata

from . import analyze, transitions
from .timecode import parse_rate

# eventos da imagem/texto/fala que são avisos (precisam de atenção)
WARN_EVENT_KINDS = {"slide_transition", "freeze", "spelling", "name_tag", "speech_phrase",
                    "speech_repeat", "color_jump", "bright_jump", "black", "flash"}
FRAME_KINDS = {"text_in", "text_out", "change"}
# eventos de áudio que só aparecem como marca na forma de onda (não são aviso):
# "corte no meio da fala" deu 6 alarmes nas 10 aulas aprovadas e o JP ouviu os 6
# (19/10/2026): todos eram ritmo normal de fala, nenhum áudio cortado.
AUDIO_MARK_KINDS = {"speech_cut"}

AUDIO_LABEL = {
    "clip": "áudio estourando", "spike": "pico de volume", "gap": "fala começa ou termina cortada",
    "level_jump": "volume muda de repente", "noise_change": "ruído de fundo muda",
    "long_silence": "silêncio longo", "speech_cut": "corte no meio da fala",
}
EVENT_LABEL = {
    "slide_transition": "transição do slide", "freeze": "imagem congelada", "spelling": "ortografia",
    "name_tag": "tarja de nome", "speech_phrase": "frase de erro na fala", "speech_repeat": "take repetido",
    "color_jump": "cor muda de repente", "bright_jump": "brilho muda de repente",
    "black": "tela preta", "flash": "frame solto entre cortes",
}
FRAME_LABEL = {"text_in": "texto entrou", "text_out": "texto saiu", "change": "mudança na tela"}


_OLD_SLIDE = re.compile(r"\(esperado: (desce|sobe) em \d+f\)")
_OLD_SLIDE_LEN = re.compile(r"frames de movimento \(padrão: (\d+); ")


def fix_note(note: str) -> str:
    """Textos de análises antigas do cache: a transição do slide aparece como 12f do Premiere."""
    note = _OLD_SLIDE.sub(lambda m: f"(esperado: {m.group(1)} em {transitions.PREMIERE_FRAMES}f no Premiere)", note)
    return _OLD_SLIDE_LEN.sub(lambda m: f"frames de movimento visível (padrão: {transitions.PREMIERE_FRAMES}f no "
                              f"Premiere ≈ {m.group(1)} visíveis; ", note)


def _mmss(sec: float | None) -> str:
    if sec is None:
        return ""
    sec = int(sec)
    h, m, s = sec // 3600, sec % 3600 // 60, sec % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def _fold(s: str) -> str:
    n = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in n if not unicodedata.combining(c)).lower().strip()


def warning_key(kind: str, frame: int | None, word: str | None = None) -> str:
    """Chave estável de um aviso (para "Ignorar" valer mesmo depois de reabrir a revisão).

    Ortografia: a palavra (o mesmo erro é avisado uma vez por vídeo). Os outros: tipo + frame.
    """
    if kind == "spelling" and word:
        return f"spelling:{_fold(word)}"
    return f"{kind}:{frame if frame is not None else 0}"


def warnings_of(a: dict, spell: bool = True, dismissed=None) -> list[dict]:
    """Todos os avisos de um vídeo, em ordem de tempo.

    {time, tc, frame, key, kind, label, note, source, region, extra}
    spell=False: ortografia desligada na tela de início (os avisos de ortografia somem).
    dismissed: chaves de avisos marcados "Ignorar" na revisão (somem da contagem).
    """
    dismissed = set(dismissed or ())
    rate = parse_rate(a.get("fps", "30000/1001"))
    last = int(a["frames"]) - 1 if a.get("frames") else None     # último frame (para não passar do fim)
    out = []
    for e in a.get("events", []):
        if e["kind"] == "spelling" and not spell:
            continue
        if e["kind"] in WARN_EVENT_KINDS:
            fr = e.get("show_frame") if e.get("show_frame") is not None else e.get("frame")
            extra = e.get("extra") or {}
            out.append({"time": e.get("time"), "tc": e.get("tc") or _mmss(e.get("time")), "frame": fr,
                        "key": warning_key(e["kind"], e.get("frame"), extra.get("word")),
                        "kind": e["kind"], "label": EVENT_LABEL.get(e["kind"], e["kind"]),
                        "note": fix_note(e.get("note", "")), "region": e.get("region"),
                        "extra": {k: v for k, v in extra.items() if k not in ("transition",)},
                        "source": "imagem" if e["kind"] in ("slide_transition", "freeze", "color_jump",
                                                            "bright_jump", "black", "flash") else
                        "texto" if e["kind"] in ("spelling", "name_tag") else "fala"})
    au = a.get("audio") or {}
    for e in au.get("events", []):
        if e["kind"] in AUDIO_MARK_KINDS:
            continue
        fr = rate.frame_at(e["start"]) if last is None else min(rate.frame_at(e["start"]), last)
        out.append({"time": e["start"], "tc": _mmss(e["start"]), "frame": fr,
                    "key": warning_key("audio_" + e["kind"], fr), "kind": e["kind"],
                    "label": AUDIO_LABEL.get(e["kind"], e["kind"]), "note": e.get("note", ""),
                    "region": None, "extra": {"start": e["start"], "end": e.get("end")}, "source": "áudio"})
    vin = a.get("vinheta") or {}
    for w in vin.get("warnings", []):
        fr = int(w.get("frame") or 0) if last is None else min(int(w.get("frame") or 0), last)
        t = rate.seconds_of(fr)
        out.append({"time": t, "tc": _mmss(t), "frame": fr, "key": warning_key(w["kind"], fr),
                    "kind": w["kind"], "label": "vinheta", "note": w.get("note", ""), "region": None,
                    "extra": {}, "source": "vinheta"})
    out = [w for w in out if w["key"] not in dismissed]
    out.sort(key=lambda x: x["time"] if x["time"] is not None else 0)
    return out


def counts_of(a: dict, sensitivity: int, spell: bool = True, dismissed=None) -> dict:
    vis = analyze.visible_events(a, sensitivity)
    groups = set()
    frames = 0
    cuts = 0
    for e in vis:
        if e["kind"] == "cut":
            cuts += 1
        elif e["kind"] in FRAME_KINDS:
            if e.get("group") is not None and e["kind"] == "text_in":
                if e["group"] in groups:
                    continue
                groups.add(e["group"])
            frames += 1
    return {"frames": frames, "cuts": cuts, "warnings": len(warnings_of(a, spell, dismissed))}


def video_row(a: dict, sensitivity: int, spell: bool = True, dismissed=None) -> dict:
    au = a.get("audio") or {}
    c = counts_of(a, sensitivity, spell, dismissed)
    w = warnings_of(a, spell, dismissed)
    return {
        "id": a["id"], "file": a["file"], "duration": a["duration"],
        "audio": {"min_db": au.get("min_db"), "min_time": au.get("min_time"),
                  "peak_dbfs": au.get("peak_dbfs"), "peak_time": au.get("peak_time"),
                  "avg_db": au.get("avg_db"), "lufs": au.get("lufs")} if au else None,
        "counts": c,
        "warnings": w,
        "first_audio_warning": next((x for x in w if x["source"] == "áudio"), None),
        "audio_marks": [{"time": e["start"], "tc": _mmss(e["start"]), "kind": e["kind"],
                         "label": AUDIO_LABEL.get(e["kind"], e["kind"])}
                        for e in au.get("events", []) if e["kind"] in AUDIO_MARK_KINDS],
        "name_tag": (a.get("name_tag") or {}).get("note"),
        "speech": (a.get("speech") or {}).get("status"),
        "text": (a.get("text") or {}).get("status"),
        "report_entry": a.get("report_entry"),
    }


def audio_totals(rows: list[dict]) -> dict:
    """Mínimo, máximo e média de todos os vídeos (média ponderada pela duração)."""
    mins = [(r["audio"]["min_db"], r) for r in rows if r.get("audio") and r["audio"]["min_db"] is not None]
    maxs = [(r["audio"]["peak_dbfs"], r) for r in rows if r.get("audio") and r["audio"]["peak_dbfs"] is not None]
    avgs = [(r["audio"]["avg_db"], r["duration"]) for r in rows if r.get("audio") and r["audio"]["avg_db"] is not None]
    out = {"min": None, "max": None, "avg": None}
    if mins:
        v, r = min(mins, key=lambda x: x[0])
        out["min"] = {"db": v, "video": r["id"], "file": r["file"], "time": r["audio"]["min_time"]}
    if maxs:
        v, r = max(maxs, key=lambda x: x[0])
        out["max"] = {"db": v, "video": r["id"], "file": r["file"], "time": r["audio"]["peak_time"]}
    if avgs:
        tot = sum(d for _, d in avgs) or 1.0
        out["avg"] = {"db": round(sum(v * d for v, d in avgs) / tot, 1)}
    return out


# ====================================================================== tela de revisão (etapa 4)

def _frame_item(e: dict) -> dict:
    fr = e["show_frame"] if e.get("show_frame") is not None else e["frame"]
    extra = e.get("extra") or {}
    label = FRAME_LABEL.get(e["kind"], e["kind"])
    reg = e.get("region")
    if e["kind"] == "change" and reg and reg[2] * reg[3] >= 0.25:
        label = "slide mudou"
    note = ""
    if extra.get("on_screen_s"):
        note = f"na tela por {str(round(extra['on_screen_s'], 1)).replace('.', ',')} s"
    return {"kind": e["kind"], "label": label, "warn": False, "frame": fr, "start": e["frame"],
            "region": reg, "note": note, "key": f"{e['kind']}:{e['frame']}", "steps": None, "extra": {}}


def review_items(a: dict, sensitivity: int, spell: bool = True, dismissed=None) -> dict:
    """O que a tela de revisão percorre com ← →: frames marcados e avisos, em ordem de tempo.

    - texto que entrou / saiu (sem par) / mudança na tela; lista = um item com passos;
    - avisos (imagem, texto, fala, áudio, vinheta), com "dismissed" se foram ignorados;
    - cortes ficam à parte (marcas na linha do tempo).
    """
    dismissed = set(dismissed or ())
    items = []
    groups: dict[int, dict] = {}
    cuts = []
    for e in analyze.visible_events(a, sensitivity):
        k = e["kind"]
        if k == "cut":
            if e.get("frame") is not None:
                cuts.append({"frame": e["frame"], "tc": e.get("tc")})
            continue
        if k not in FRAME_KINDS or e.get("frame") is None:
            continue
        it = _frame_item(e)
        if k == "text_in" and e.get("group") is not None:
            g = groups.get(e["group"])
            if g is None:
                g = dict(it, kind="list", key=f"list:{e['frame']}", steps=[])
                groups[e["group"]] = g
                items.append(g)
            g["steps"].append({"frame": it["frame"], "region": it["region"]})
            continue
        items.append(it)
    for g in groups.values():
        n = len(g["steps"])
        g["frame"] = g["steps"][-1]["frame"]          # a lista inteira na tela
        g["region"] = _union([s["region"] for s in g["steps"]])
        g["label"] = f"lista · {n} itens" if n > 1 else "texto entrou"
        if n == 1:
            g["steps"] = None
    shown = warnings_of(a, spell)            # todos, para marcar os ignorados
    for w in shown:
        items.append({"kind": w["kind"], "label": w["label"], "warn": True, "frame": w["frame"],
                      "start": w["frame"], "region": w["region"], "note": w["note"], "key": w["key"],
                      "source": w["source"], "steps": None, "extra": w["extra"],
                      "dismissed": w["key"] in dismissed})
    items.sort(key=lambda x: (x["start"] if x["start"] is not None else 0, 0 if not x["warn"] else 1))
    for k, it in enumerate(items):
        it["i"] = k
    au = a.get("audio") or {}
    marks = [{"time": e["start"], "kind": e["kind"], "label": AUDIO_LABEL.get(e["kind"], e["kind"])}
             for e in au.get("events", []) if e["kind"] in AUDIO_MARK_KINDS]
    return {"items": items, "cuts": cuts, "audio_marks": marks,
            "counts": counts_of(a, sensitivity, spell, dismissed)}


def _union(regs):
    regs = [r for r in regs if r]
    if not regs:
        return None
    x0 = min(r[0] for r in regs)
    y0 = min(r[1] for r in regs)
    x1 = max(r[0] + r[2] for r in regs)
    y1 = max(r[1] + r[3] for r in regs)
    return [round(x0, 4), round(y0, 4), round(x1 - x0, 4), round(y1 - y0, 4)]


def slide_spans(a: dict) -> list[list[int]]:
    """Trechos com slide em tela cheia: [frame em que entrou, frame em que saiu].

    Vem da transição medida em cada corte (transitions.py): "entra" abre o trecho e
    "sai" fecha. Corte seco com slide (aviso "slide entrou/saiu com corte seco")
    também conta. Só para a marca colorida na linha do tempo da revisão.
    """
    end = (a.get("content") or {}).get("end_frame") or a.get("frames") or 0
    dry = {}
    for e in a.get("events", []):
        if e.get("kind") == "slide_transition":
            n = (e.get("note") or "").lower()
            dry[e["frame"]] = "entra" if "entrou" in n else "sai" if "saiu" in n else ""
    spans, start = [], None
    for e in sorted((e for e in a.get("events", []) if e.get("kind") == "cut"), key=lambda e: e["frame"]):
        tr = ((e.get("extra") or {}).get("transition") or {})
        kind = tr.get("kind")
        if kind == "corte_seco":
            kind = dry.get(e["frame"], "")
        if kind == "entra":
            if start is not None:             # entrou outro sem sair: fecha o anterior aqui
                spans.append([start, e["frame"]])
            start = e["frame"]
        elif kind == "sai" and start is not None:
            spans.append([start, e["frame"]])
            start = None
    if start is not None and end > start:
        spans.append([start, int(end)])
    return spans


def slide_pages(a: dict) -> list[dict]:
    """Um item navegável por slide em tela cheia (opcional na revisão: "Navegar pelos slides").

    Cada trecho de slide_spans começa um slide; cortes secos dentro do trecho (slide → slide)
    começam o próximo. O frame mostrado é depois da transição (12f no Premiere) ou logo
    depois do corte seco, para o slide já estar parado.
    """
    spans = slide_spans(a)
    cuts = sorted(e["frame"] for e in a.get("events", []) if e.get("kind") == "cut")
    starts = []                                   # (início, fim do trecho, entrou com movimento?)
    for f0, f1 in spans:
        inner = [c for c in cuts if f0 < c < f1]
        bounds = [f0] + inner + [f1]
        for k in range(len(bounds) - 1):
            starts.append((bounds[k], bounds[k + 1], k == 0))
    items = []
    for n, (p, end, first) in enumerate(starts, 1):
        tr = 15 if first else 2                   # entrada: 12f do Premiere + folga; corte seco: 2 frames
        fr = min(p + tr, max(p, end - 2))
        items.append({"kind": "slide", "label": f"slide {n} de {len(starts)}", "warn": False, "frame": int(fr),
                      "start": int(p), "region": None, "note": "", "key": f"slide:{p}", "steps": None,
                      "extra": {}, "source": "slide"})
    return items
