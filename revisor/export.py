"""Etapa 5: o que sai da revisão.

- texto copiado ("Vídeo 02 · 00:00:44 · comentário") e linhas do Resumo final;
- SRT de cada vídeo (mesmo nome do vídeo + .srt; blocos de N s; "CORRIGIR: …");
- horas por editor da revisão e o txt de horas;
- pacote para levar a revisão a outro computador (pasta com revisao.json, frames/ e
  horas.txt — só nomes, nenhum caminho, nenhum vídeo) e a junção de duas revisões;
- relatório do mês por editor (horas de vídeo editado no mês da ENTREGA da edição;
  horas gravadas no mês da gravação; cada vídeo conta uma vez).

Nada aqui lê vídeo: tudo sai da revisão salva (e, para as imagens, de uma função
que o servidor passa).
"""
from __future__ import annotations

import copy
import csv
import io
import json
import re
import shutil
import time
import zipfile
from collections import OrderedDict, defaultdict
from datetime import date, datetime
from pathlib import Path

from . import report as treport
from . import review, timecode
from .timecode import NTSC_2997, Rate, parse_rate

PACKAGE_FORMAT = 1
NO_EDITOR = "Sem editor"
NO_COURSE = "Sem curso"
MONTHS = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro",
          "outubro", "novembro", "dezembro"]
SRT_SUBFOLDER = "Correções"
_ID_RE = re.compile(r"^[0-9A-Za-z]{1,40}$")
_RAW_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})[ _]")


# ====================================================================== formatos

def fmt_hms(s: float | None) -> str:
    """0:55:04"""
    if s is None:
        return "—"
    s = int(round(s))
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"


def fmt_hm(s: float | None) -> str:
    """0:42h (horas e minutos, como no desenho)"""
    if s is None:
        return "—"
    m = int(round(s / 60))
    return f"{m // 60}:{m % 60:02d}h"


def fmt_clock(s: float | None) -> str:
    """42:18 ou 1:02:18 (duração)"""
    if s is None:
        return "—"
    return timecode.fmt_duration(s)


def fmt_pct(v: float | None) -> str:
    return "—" if v is None else f"{v:.1f}%".replace(".", ",")


def month_key(iso: str | None) -> str | None:
    """"2026-10-07" → "2026-10"."""
    if not iso or not re.match(r"^\d{4}-\d{2}", iso):
        return None
    return iso[:7]


def month_label(key: str) -> str:
    """"2026-10" → "Outubro de 2026"."""
    y, m = key.split("-")
    return f"{MONTHS[int(m) - 1].capitalize()} de {y}"


# ====================================================================== comentários

def rate_of(v: dict) -> Rate:
    try:
        return parse_rate(v.get("fps") or "30000/1001")
    except (ValueError, ZeroDivisionError):
        return Rate(NTSC_2997)


GENERAL_TC = "Geral"          # no lugar do tempo: "Vídeo 01 · Geral · aumentar o áudio geral"


def general_cid(v: dict) -> str:
    return "g" + str(v["id"])


def comment_rows(rev: dict, style: str = "seconds") -> list[dict]:
    """Todos os comentários da revisão, na ordem dos vídeos e do tempo (para o Resumo final)."""
    rows = []
    for k, v in enumerate(rev.get("videos", [])):
        r = rate_of(v)
        g = review.general_of(v)
        if g:       # comentário geral: vem primeiro, sem tempo e sem frame
            rows.append({
                "cid": general_cid(v), "vid": v["id"], "n": k + 1, "file": v["file"], "frame": None, "general": True,
                "tc": GENERAL_TC, "seconds": None, "text": g["text"], "label": "geral",
                "selected": bool(g.get("selected", True)), "with_frame": False, "missing": bool(v.get("missing", False)),
            })
        for c in sorted(v.get("comments", []), key=lambda c: c["frame"]):
            rows.append({
                "cid": c.get("cid"), "vid": v["id"], "n": k + 1, "file": v["file"], "frame": int(c["frame"]),
                "tc": timecode.fmt(r, int(c["frame"]), style), "seconds": r.seconds_of(int(c["frame"])),
                "text": c.get("text", ""), "label": c.get("label", ""), "tag": c.get("tag"),
                "selected": bool(c.get("selected", True)), "with_frame": bool(c.get("with_frame", True)),
                "missing": bool(v.get("missing", False)),
            })
    return rows


def line_of(row: dict) -> str:
    """Todo texto copiado leva o vídeo e o tempo: "Vídeo 02 · 00:00:44 · comentário"."""
    return f"Vídeo {row['n']:02d} · {row['tc']} · {row['text']}"


def copy_text(rows: list[dict]) -> str:
    return "\n".join(line_of(r) for r in rows)


# ====================================================================== SRT

def _srt_body(text: str) -> str:
    # linha em branco encerra o bloco no SRT: junta parágrafos numa linha só
    text = text.replace("\r", "")
    return re.sub(r"\n\s*\n+", "\n", text).strip()


def srt_text(comments: list[dict], rate: Rate, block_s: float = 3, prefix: str = "CORRIGIR:") -> str:
    """SRT de um vídeo com os comentários dados (já filtrados). Blocos não se sobrepõem:
    se o próximo comentário vem antes de acabar o bloco, o bloco termina ali."""
    cs = sorted(comments, key=lambda c: c["frame"])
    out = []
    for i, c in enumerate(cs):
        start = rate.seconds_of(int(c["frame"]))     # o geral está no frame 0 (começo da timeline)
        end = start + float(block_s)
        if i + 1 < len(cs):
            end = min(end, rate.seconds_of(int(cs[i + 1]["frame"])) - 0.001)
        end = max(end, start + 0.001)
        body = _srt_body(c.get("text", ""))
        if c.get("general"):
            body = f"(geral) {body}"
        text = f"{prefix.strip()} {body}".strip() if prefix and prefix.strip() else body
        out.append(f"{i + 1}\n{timecode.fmt_srt(start)} --> {timecode.fmt_srt(end)}\n{text}\n")
    return "\n".join(out)


def srt_bytes(text: str) -> bytes:
    # UTF-8 com BOM e fim de linha do Windows: o Premiere lê os acentos certo nos dois sistemas
    return ("﻿" + text.replace("\n", "\r\n")).encode("utf-8")


def srt_name(video_file: str) -> str:
    return Path(video_file).stem + ".srt"


def srt_jobs(rev: dict) -> list[dict]:
    """Um SRT por vídeo que tem comentário MARCADO (os desmarcados não entram)."""
    jobs = []
    for k, v in enumerate(rev.get("videos", [])):
        sel = [c for c in v.get("comments", []) if c.get("selected", True) and (c.get("text") or "").strip()]
        g = review.general_of(v)
        if g and g.get("selected", True):
            sel = [{"frame": 0, "text": g["text"], "general": True}] + sel
        if sel:
            jobs.append({"n": k + 1, "video": v, "comments": sel, "name": srt_name(v["file"])})
    return jobs


def write_srts(rev: dict, folder: Path, block_s: float = 3, prefix: str = "CORRIGIR:",
               where: str = "beside") -> dict:
    """Grava os SRT ao lado dos vídeos (ou na subpasta "Correções"). Substitui o SRT anterior."""
    folder = Path(folder)
    target = folder / SRT_SUBFOLDER if where == "subfolder" else folder
    written = []
    jobs = srt_jobs(rev)
    if jobs:
        target.mkdir(parents=True, exist_ok=True)
    for j in jobs:
        p = target / j["name"]
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_bytes(srt_bytes(srt_text(j["comments"], rate_of(j["video"]), block_s, prefix)))
        tmp.replace(p)
        written.append({"n": j["n"], "file": p.name, "comments": len(j["comments"])})
    return {"folder": str(target), "files": written}


def srt_zip(rev: dict, block_s: float = 3, prefix: str = "CORRIGIR:") -> bytes:
    """Os mesmos SRT num .zip (quando a pasta dos vídeos não está neste computador)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for j in srt_jobs(rev):
            z.writestr(j["name"], srt_bytes(srt_text(j["comments"], rate_of(j["video"]), block_s, prefix)))
    return buf.getvalue()


# ====================================================================== horas

def video_seconds(v: dict) -> float:
    """Tempo do vídeo editado: o número do relatório de tempo quando o vídeo está nele
    (o app não recalcula); sem relatório, a duração do arquivo."""
    re_ = v.get("report_entry") or {}
    if re_.get("seconds") is not None:
        return float(re_["seconds"])
    return float(v.get("duration") or 0.0)


def counted_videos(rev: dict) -> list[tuple[int, dict]]:
    """Vídeos que contam nas horas. Fica de fora a versão anterior de um vídeo que voltou
    corrigido (saiu da pasta e entrou outro com o mesmo nome: rodada 2, 3)."""
    vids = rev.get("videos", [])
    present = {treport.norm_name(v["file"]) for v in vids if not v.get("missing")}
    out = []
    for k, v in enumerate(vids):
        if v.get("missing") and treport.norm_name(v["file"]) in present:
            continue
        out.append((k + 1, v))
    return out


def editor_hours(rev: dict) -> dict:
    groups: "OrderedDict[str, dict]" = OrderedDict()
    for n, v in counted_videos(rev):
        name = v.get("editor") or NO_EDITOR
        g = groups.setdefault(name, {"name": name, "videos": [], "seconds": 0.0, "none": name == NO_EDITOR})
        g["videos"].append(n)
        g["seconds"] += video_seconds(v)
    eds = sorted(groups.values(), key=lambda g: (g["none"], -g["seconds"]))
    rep = rev.get("report") or {}
    total = rep.get("total_edited_s")
    summed = sum(g["seconds"] for g in eds)
    return {
        "editors": eds,
        "total_s": total if total is not None else summed,
        "summed_s": summed,
        "raw_s": rep.get("total_raw_s"),
        "usage_pct": rep.get("usage_pct"),
        "entrega": rev.get("entrega"),
        "entrega_locked": bool(rev.get("entrega_locked")),
        "without_editor": sum(len(g["videos"]) for g in eds if g["none"]),
        "from_report": total is not None,
    }


def hours_txt(rev: dict) -> str:
    h = editor_hours(rev)
    vids = rev.get("videos", [])
    ent = rev.get("entrega")
    who = " · ".join(x for x in (rev.get("professor"), rev.get("curso"), rev.get("disciplina")) if x)
    lines = ["HORAS DE VÍDEO EDITADO POR EDITOR", f"Projeto (pasta editados): {rev.get('project', '')}"]
    if who:
        lines.append(f"Professor: {who}")
    if ent:
        lines.append(f"Entrega da edição: {review.fmt_date(ent)}  (conta em {month_label(ent[:7]).lower()})")
    lines.append(f"Gerado em: {time.strftime('%d/%m/%Y %H:%M')}")
    lines.append("")
    w = max([len(g["name"]) for g in h["editors"]] + [10])
    for g in h["editors"]:
        lines.append(f"{g['name']:<{w}}  {len(g['videos']):>2} {'vídeo ' if len(g['videos']) == 1 else 'vídeos'}"
                     f"  {fmt_hms(g['seconds'])}")
        for n in g["videos"]:
            v = vids[n - 1]
            lines.append(f"    {n:02d}  {fmt_hms(video_seconds(v)):>8}  {v['file']}")
    lines.append("")
    lines.append("----------------------------------------------")
    lines.append(f"TOTAL EDITADO:     {fmt_hms(h['total_s'])}" + ("" if h["from_report"] else "  (duração dos arquivos)"))
    if h["raw_s"] is not None:
        lines.append(f"GRAVADO (bruto):   {fmt_hms(h['raw_s'])}")
    if h["usage_pct"] is not None:
        lines.append(f"APROVEITAMENTO:    {fmt_pct(h['usage_pct'])}")
    if h["without_editor"]:
        lines.append("")
        lines.append(f"Atenção: {h['without_editor']} vídeo(s) sem editor marcado.")
    return "\n".join(lines) + "\n"


# ====================================================================== pacote entre computadores

def package_name(rev: dict) -> str:
    return review.slug(f"Revisão {rev.get('entrega') or ''} {rev.get('project', '')}")


def export_package(rev: dict, dest_parent: Path, frame_fn) -> dict:
    """Cria <dest_parent>/Revisão <entrega> <projeto>/ com revisao.json, frames/ e horas.txt.

    frame_fn(video, frame) → Path de um JPEG (ou None). Vão as imagens de TODOS os frames
    comentados (no outro computador dá para mudar "com/sem frame"). Nunca vídeos nem cache.
    """
    dest_parent = Path(dest_parent)
    if not dest_parent.is_dir():
        raise FileNotFoundError(str(dest_parent))
    folder = dest_parent / package_name(rev)
    fdir = folder / "frames"
    fdir.mkdir(parents=True, exist_ok=True)
    for old in fdir.glob("v*_f*.jpg"):          # só as imagens que o próprio app pôs aqui antes
        try:
            old.unlink()
        except OSError:
            pass
    data = copy.deepcopy(rev)
    data.pop("folder", None)
    data.pop("raw_folder", None)          # caminho dos brutos (só neste computador)
    data.pop("pkg_frames", None)
    frames_map, size, missing = {}, 0, 0
    for k, v in enumerate(data.get("videos", [])):
        for c in v.get("comments", []):
            src = frame_fn(v, int(c["frame"]))
            if src is None or not Path(src).is_file():
                missing += 1
                continue
            name = f"v{k + 1:02d}_f{int(c['frame']):07d}.jpg"
            shutil.copyfile(src, fdir / name)
            size += (fdir / name).stat().st_size
            frames_map[f"{v['id']}:{int(c['frame'])}"] = f"frames/{name}"
    data["package"] = {"format": PACKAGE_FORMAT, "exported": review.now_text(), "frames": frames_map}
    tmp = folder / "revisao.json.tmp"
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(folder / "revisao.json")
    (folder / "horas.txt").write_text(hours_txt(rev), encoding="utf-8")
    return {"folder": str(folder), "name": folder.name, "frames": len(frames_map), "frames_missing": missing,
            "bytes": size, "comments": comment_count(data)}


class PackageError(ValueError):
    pass


def _clean_video(v) -> dict | None:
    if not isinstance(v, dict) or not isinstance(v.get("file"), str) or not _ID_RE.match(str(v.get("id", ""))):
        return None
    out = dict(v)
    out["file"] = Path(v["file"].replace("\\", "/")).name          # só o nome, nunca caminho
    try:
        out["duration"] = float(v.get("duration") or 0.0)
    except (TypeError, ValueError):
        out["duration"] = 0.0
    cs = []
    for c in v.get("comments") or []:
        if not isinstance(c, dict):
            continue
        try:
            f = int(c.get("frame"))
        except (TypeError, ValueError):
            continue
        text = str(c.get("text") or "").strip()[:4000]
        if f < 0 or not text:
            continue
        cc = dict(c)
        cc.update({"frame": f, "text": text, "selected": bool(c.get("selected", True)),
                   "with_frame": bool(c.get("with_frame", True))})
        if cc.get("tag") not in review.TAGS:
            cc["tag"] = None
        try:
            cc["round"] = max(1, int(c.get("round") or 1))
        except (TypeError, ValueError):
            cc["round"] = 1
        cc.pop("check", None) if not isinstance(c.get("check"), dict) else None
        cc.setdefault("cid", f"{f:07d}")
        cs.append(cc)
    out["comments"] = sorted(cs, key=lambda c: c["frame"])
    g = v.get("general")
    gtext = str(g.get("text") or "").strip()[:4000] if isinstance(g, dict) else ""
    out["general"] = {"text": gtext, "selected": bool(g.get("selected", True)),
                      "created": str(g.get("created") or "")[:40], "updated": str(g.get("updated") or "")[:40]} if gtext else None
    out["dismissed"] = [str(x)[:200] for x in (v.get("dismissed") or []) if isinstance(x, (str, int))]
    ed = v.get("editor")
    out["editor"] = str(ed)[:80] if ed else None
    if out.get("status") not in review.STATUSES:
        out.pop("status", None)
    try:
        out["round"] = max(1, int(v.get("round") or 1))
    except (TypeError, ValueError):
        out["round"] = 1
    return out


def read_package(path: str | Path) -> tuple[dict, Path]:
    """Lê o pacote (a pasta ou o revisao.json dentro dela). Devolve (revisão, pasta do pacote)."""
    p = Path(path).expanduser()
    if p.is_dir():
        p = p / "revisao.json"
    if not p.is_file():
        raise PackageError("Não achei o arquivo revisao.json nessa pasta. Escolha a pasta do pacote exportado.")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise PackageError("O revisao.json está danificado ou não é de uma revisão.")
    if not isinstance(data, dict) or not isinstance(data.get("project"), str) or not isinstance(data.get("videos"), list):
        raise PackageError("Esse arquivo não é uma revisão do Revisor de Vídeos.")
    vids = [x for x in (_clean_video(v) for v in data["videos"]) if x]
    data["videos"] = vids
    data["project"] = data["project"].strip()[:120] or "revisão"
    data["key"] = review.project_key(data["project"])
    data.pop("folder", None)
    data.pop("raw_folder", None)
    return data, p.parent


def package_frames(data: dict, base: Path) -> dict[str, Path]:
    """"<id>:<frame>" → imagem do pacote (só arquivos dentro de frames/ do próprio pacote)."""
    out = {}
    fdir = (Path(base) / "frames").resolve()
    for key, rel in ((data.get("package") or {}).get("frames") or {}).items():
        if not isinstance(rel, str) or not re.fullmatch(r"frames/v\d{2,3}_f\d{7}\.jpg", rel):
            continue
        p = (Path(base) / rel).resolve()
        if p.parent == fdir and p.is_file():
            out[str(key)] = p
    return out


def same_content(a: dict, b: dict) -> bool:
    """As duas revisões têm os mesmos vídeos, editores, comentários e avisos ignorados?"""
    def sig(r):
        out = {}
        for v in r.get("videos", []):
            out[v["id"]] = (v.get("editor") or None,
                            sorted((int(c["frame"]), (c.get("text") or "").strip(), bool(c.get("selected", True)),
                                    bool(c.get("with_frame", True))) for c in v.get("comments", [])),
                            sorted(str(x) for x in v.get("dismissed", []) or []),
                            ((review.general_of(v) or {}).get("text") or "").strip())
        return out
    return sig(a) == sig(b)


def comment_count(rev: dict | None) -> int:
    return sum(review.comment_total(v) for v in (rev or {}).get("videos", []))


def merge_reviews(local: dict, pkg: dict) -> dict:
    """"Juntar as duas": vídeos de um e de outro; comentários dos dois (no mesmo frame fica o
    mais recente); editor marcado num só lado vale; "ignorar" dos dois lados."""
    out = copy.deepcopy(local)
    newer_pkg = (pkg.get("updated") or "") > (local.get("updated") or "")
    by_id = {v["id"]: v for v in out.get("videos", [])}
    for pv in pkg.get("videos", []):
        lv = by_id.get(pv["id"])
        if lv is None:
            nv = copy.deepcopy(pv)
            out.setdefault("videos", []).append(nv)
            by_id[nv["id"]] = nv
            continue
        if pv.get("editor") and (not lv.get("editor") or (newer_pkg and lv.get("editor") != pv["editor"])):
            lv["editor"] = pv["editor"]
        cur = {c["frame"]: c for c in lv.setdefault("comments", [])}
        for c in pv.get("comments", []):
            mine = cur.get(c["frame"])
            if mine is None:
                lv["comments"].append(copy.deepcopy(c))
            elif mine.get("text") != c.get("text") and (c.get("updated") or "") > (mine.get("updated") or ""):
                mine.update(copy.deepcopy(c))
        lv["comments"].sort(key=lambda c: c["frame"])
        pg, lg = review.general_of(pv), review.general_of(lv)       # comentário geral: vale o mais recente
        if pg and (not lg or (lg.get("text") != pg.get("text") and (pg.get("updated") or "") > (lg.get("updated") or ""))):
            lv["general"] = copy.deepcopy(pg)
        dis = lv.setdefault("dismissed", [])
        for k in pv.get("dismissed", []):
            if k not in dis:
                dis.append(k)
        if pv.get("status") and (not lv.get("status") or newer_pkg):     # situação: vale a mais recente
            lv["status"] = pv["status"]
        if not lv.get("fps") and pv.get("fps"):
            lv["fps"] = pv["fps"]
        if not lv.get("report_entry") and pv.get("report_entry"):
            lv["report_entry"] = pv["report_entry"]
    for k in ("professor", "curso", "disciplina", "nome_tarja", "report"):
        if not out.get(k) and pkg.get(k):
            out[k] = copy.deepcopy(pkg[k])
    if not out.get("entrega") and pkg.get("entrega"):
        out["entrega"], out["entrega_locked"] = pkg["entrega"], bool(pkg.get("entrega_locked"))
    return out


# ====================================================================== relatório do mês

def find_reviews(dirs: list[Path]) -> tuple[list[dict], int, int]:
    """Lê as revisões salvas (pasta do app e, opcionalmente, outra pasta com pacotes).
    A mesma revisão em dois lugares (este computador e um pacote) conta uma vez: fica a
    salva por último. Devolve (revisões, lidas, repetidas)."""
    best: dict[str, dict] = {}
    read = dup = 0
    seen_files = set()
    for d in dirs:
        if not d:
            continue
        d = Path(d)
        if not d.is_dir():
            continue
        for pat in ("revisao.json", "*/revisao.json", "*/*/revisao.json"):
            for p in d.glob(pat):
                try:
                    rp = p.resolve()
                except OSError:
                    continue
                if rp in seen_files:
                    continue
                seen_files.add(rp)
                try:
                    r = json.loads(p.read_text(encoding="utf-8"))
                except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                    continue
                if not isinstance(r, dict) or not isinstance(r.get("videos"), list) or not r.get("project"):
                    continue
                read += 1
                r["_source"] = str(p)
                key = r.get("key") or review.project_key(r["project"])
                if key in best:
                    dup += 1
                    if (r.get("updated") or "") <= (best[key].get("updated") or ""):
                        continue
                best[key] = r
    return list(best.values()), read, dup


def raw_entries(rev: dict) -> list[tuple[float, str, str | None]]:
    """Gravações do projeto: (segundos, arquivo, "AAAA-MM-DD" da gravação).

    A data vem do nome que o OBS dá ao bruto ("2026-09-21 10-36-59.mp4"). Revisões antigas
    (sem a lista de brutos) tentam reler o txt na pasta; sem isso, o total vai para a data
    do relatório."""
    rep = rev.get("report") or {}
    raw = rep.get("raw")
    if raw is None and rev.get("folder") and rep.get("file"):
        p = Path(rev["folder"]) / rep["file"]
        if p.is_file():
            try:
                raw = treport.parse(p).to_dict()["raw"]
            except (OSError, ValueError):
                raw = None
    fallback = (rep.get("date") or "")[:10] or rev.get("entrega")
    out = []
    if raw:
        for e in raw:
            try:
                secs = float(e["seconds"])
            except (KeyError, TypeError, ValueError):
                continue
            m = _RAW_DATE.match(str(e.get("file", "")))
            out.append((secs, str(e.get("file", "")), f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else fallback))
    elif rep.get("total_raw_s") is not None:
        out.append((float(rep["total_raw_s"]), "", fallback))
    return out


def month_report(revs: list[dict], month: str | None = None) -> dict:
    """Horas de vídeo editado por editor no mês (mês da entrega da edição).

    Cada vídeo conta uma vez (mesmo id = nome + duração, ou mesmo nome no mesmo projeto):
    conta na PRIMEIRA entrega em que aparece. Gravado: soma dos brutos no mês em que foram
    gravados (cada bruto uma vez)."""
    revs = sorted(revs, key=lambda r: (r.get("entrega") or "9999", r.get("updated") or ""))
    months = set()
    for r in revs:
        if month_key(r.get("entrega")):
            months.add(month_key(r.get("entrega")))
        for _s, _f, d in raw_entries(r):
            if month_key(d):
                months.add(month_key(d))
    months = sorted(months, reverse=True)
    if month is None:
        month = months[0] if months else date.today().isoformat()[:7]
    seen_id, seen_name, seen_raw = set(), set(), set()
    eds: dict[str, dict] = {}
    cursos: dict[str, float] = defaultdict(float)
    weeks = [0.0] * 5
    rows, projects = [], set()
    repeated = no_date = 0
    recorded = 0.0
    for r in revs:
        ent = r.get("entrega")
        key = r.get("key") or review.project_key(r.get("project", ""))
        for _secs, fname, d in raw_entries(r):
            rk = fname or f"{key}|total"
            if rk in seen_raw:
                continue
            seen_raw.add(rk)
            if month_key(d) == month:
                recorded += _secs
        if not month_key(ent):
            no_date += 1
            continue
        for n, v in counted_videos(r):
            nk = (key, treport.norm_name(v["file"]))
            if v["id"] in seen_id or nk in seen_name:
                if month_key(ent) == month:
                    repeated += 1
                continue
            seen_id.add(v["id"])
            seen_name.add(nk)
            if month_key(ent) != month:
                continue
            secs = video_seconds(v)
            name = v.get("editor") or NO_EDITOR
            e = eds.setdefault(name, {"name": name, "videos": 0, "seconds": 0.0, "none": name == NO_EDITOR,
                                      "approved_first": 0, "returned": 0, "tags": {}, "comments": 0})
            e["videos"] += 1
            e["seconds"] += secs
            # situação e etiquetas (22/10): todas as rodadas do mesmo vídeo neste projeto
            same = [x for x in r.get("videos", []) if treport.norm_name(x["file"]) == treport.norm_name(v["file"])]
            rounds = max(int(x.get("round") or 1) for x in same)
            if rounds > 1 or any(x.get("status") == "volta" for x in same):
                e["returned"] += 1
            elif v.get("status") == "aprovado":
                e["approved_first"] += 1
            for x in same:
                for c in x.get("comments", []) or []:
                    e["comments"] += 1
                    t = c.get("tag") or "sem"
                    e["tags"][t] = e["tags"].get(t, 0) + 1
            cursos[(r.get("curso") or "").strip() or NO_COURSE] += secs
            weeks[min(4, (int(ent[8:10]) - 1) // 7)] += secs
            projects.add(key)
            rows.append({"mes": month, "entrega": ent, "editor": name, "professor": r.get("professor", ""),
                         "curso": r.get("curso", ""), "disciplina": r.get("disciplina", ""),
                         "projeto": r.get("project", ""), "n": n, "video": v["file"], "seconds": secs})
    total = sum(e["seconds"] for e in eds.values())
    ed_list = sorted(eds.values(), key=lambda e: (e["none"], -e["seconds"]))
    for e in ed_list:
        e["share"] = (100.0 * e["seconds"] / total) if total else 0.0
    y, m = (int(x) for x in month.split("-"))
    last_day = (date(y + (m == 12), m % 12 + 1, 1) - date(y, m, 1)).days
    nweeks = 5 if last_day > 28 else 4
    return {
        "month": month, "label": month_label(month), "months": [{"key": k, "label": month_label(k)} for k in months],
        "edited_s": total, "recorded_s": recorded,
        "usage_pct": (100.0 * total / recorded) if recorded else None,
        "videos": len(rows), "projects": len(projects), "repeated": repeated, "no_date": no_date,
        "editors": ed_list,
        "courses": [{"name": k, "seconds": s} for k, s in sorted(cursos.items(), key=lambda x: -x[1])],
        "weeks": [{"label": f"Sem {i + 1}", "days": f"{7 * i + 1}–{min(7 * i + 7, last_day)}", "seconds": weeks[i]}
                  for i in range(nweeks)],
        "rows": rows,
    }


def month_txt(rep: dict, reviews_read: int = 0) -> str:
    lines = ["RELATÓRIO DO MÊS — HORAS DE VÍDEO EDITADO", f"Mês: {rep['label']} (mês da entrega da edição)",
             f"Gerado em: {time.strftime('%d/%m/%Y %H:%M')}", ""]
    w = max([len(e["name"]) for e in rep["editors"]] + [10])
    lines.append(f"{'Editor':<{w}}  Vídeos  Horas editadas  Parte")
    for e in rep["editors"]:
        lines.append(f"{e['name']:<{w}}  {e['videos']:>6}  {fmt_hms(e['seconds']):>14}  {e['share']:>4.0f}%")
    lines.append(f"{'Total':<{w}}  {rep['videos']:>6}  {fmt_hms(rep['edited_s']):>14}")
    if any(e.get("comments") or e.get("approved_first") or e.get("returned") for e in rep["editors"]):
        lines += ["", "Revisão por editor (aprovados de primeira · voltaram · correções por tipo):"]
        for e in rep["editors"]:
            tags = " · ".join(f"{review.TAGS.get(k, 'Sem etiqueta')} {n}" for k, n in
                              sorted(e.get("tags", {}).items(), key=lambda x: -x[1]))
            lines.append(f"  {e['name']}: {e.get('approved_first', 0)} aprovados de primeira · "
                         f"{e.get('returned', 0)} voltaram" + (f" · {tags}" if tags else ""))
    lines += ["", f"Gravado no mês (bruto, mês da gravação): {fmt_hms(rep['recorded_s'])}",
              f"Aproveitamento (editado ÷ gravado): {fmt_pct(rep['usage_pct'])}", ""]
    if rep["courses"]:
        lines.append("Por curso:")
        for c in rep["courses"]:
            lines.append(f"  {c['name']}: {fmt_hms(c['seconds'])}")
        lines.append("")
    lines.append("Vídeos:")
    for r in rep["rows"]:
        lines.append(f"  {review.fmt_date(r['entrega'])}  {r['editor']:<{w}}  {fmt_hms(r['seconds']):>8}  "
                     f"{r['projeto']} · {r['video']}")
    lines.append("")
    if reviews_read:
        lines.append(f"{reviews_read} revisões lidas. Cada vídeo conta uma vez (rodadas seguintes não contam de novo).")
    return "\n".join(lines) + "\n"


def month_csv(rep: dict) -> bytes:
    """Uma linha por vídeo (para colar numa planilha). Separador ";" e vírgula decimal
    (padrão do Excel e do Google Planilhas em português)."""
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\r\n")
    w.writerow(["Mês", "Entrega da edição", "Editor", "Professor", "Curso", "Disciplina", "Projeto", "Vídeo",
                "Duração", "Horas (decimal)"])
    for r in rep["rows"]:
        w.writerow([rep["label"], review.fmt_date(r["entrega"]), r["editor"], r["professor"], r["curso"],
                    r["disciplina"], r["projeto"], r["video"], fmt_hms(r["seconds"]),
                    f"{r['seconds'] / 3600:.4f}".replace(".", ",")])
    return ("﻿" + buf.getvalue()).encode("utf-8")
