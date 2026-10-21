"""Servidor local: as telas abrem no navegador e conversam com o motor por aqui.

Só escuta em 127.0.0.1 (nada sai do computador). Rodar: python3 -m revisor
"""
from __future__ import annotations

import io
import json
import mimetypes
import os
import re
import shutil
import socket
import threading
import time
import traceback
import uuid
import webbrowser
from datetime import date, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

import numpy as np

from . import __version__, analyze, appdata, dialogs, export, frames, jobs, life, media, review, scopes, spell, summary
from .timecode import parse_rate

UI_DIR = Path(__file__).resolve().parent / "ui"
DEFAULT_PORT = 8765
VIDEO_TYPES = {".mp4": "video/mp4", ".m4v": "video/mp4", ".mov": "video/mp4"}   # .mov H.264 toca como mp4


class ApiError(Exception):
    def __init__(self, msg: str, status: int = 400):
        super().__init__(msg)
        self.status = status


def scope_marks() -> tuple[dict, dict]:
    """Alvos Rec.709 (75%) e linha de pele em coordenadas 0–1 do vectorscope (x = Cb, y = Cr para cima)."""
    tpos = {}
    for name, t in scopes.targets(0.75).items():
        tpos[name] = {"x": (128 + 224 * t["pb"]) / 256, "y": 1 - (128 + 224 * t["pr"]) / 256,
                      "angle": t["angle"]}
    ang = np.radians(scopes.SKIN_LINE_DEG)
    skin = {"x": (128 + 224 * 0.62 * np.cos(ang)) / 256, "y": 1 - (128 + 224 * 0.62 * np.sin(ang)) / 256}
    return tpos, skin


# ====================================================================== estado do app

QUEUE_FILE = "fila.json"      # pastas que ainda faltava analisar quando o app fechou


def qkey(project: str | None) -> str:
    return review.project_key(project or "")


class App:
    def __init__(self):
        self.lock = threading.RLock()
        self.review: dict | None = None
        self.scan: dict | None = None
        # Fila de pastas (pedido do JP, 21/10): uma análise por vez, uma pasta depois da outra, em
        # segundo plano. Trocar a revisão aberta não para a análise. Cada item:
        # {key, project, folder, professor, scan, job (AnalysisJob; "idle" = esperando a vez)}
        self.queue: list[dict] = []
        self._dying: list[jobs.AnalysisJob] = []           # canceladas que ainda não pararam de fato
        self._restore: list[dict] | None = None             # fila que ficou da última vez (lida do disco)
        self._stopping = False                              # o app está fechando: nada novo começa
        self.frames = frames.FrameService(self.cache_root)
        self._acache: dict[str, tuple[float, dict]] = {}     # análises lidas do cache (id → (mtime, dados))

    @property
    def job(self) -> jobs.AnalysisJob | None:
        """Análise da revisão aberta (pode estar esperando a vez na fila: estado "idle")."""
        rev = self.review
        if rev is None:
            return None
        e = self._entry(rev["project"])
        return e["job"] if e else None

    # ---------------------------------------------------------------- utilidades
    @property
    def settings(self) -> dict:
        return appdata.load_settings()

    def cache_root(self) -> Path:
        return appdata.cache_dir()

    def reviews_root(self) -> Path:
        return appdata.reviews_dir()

    def save_review(self):
        if self.review is not None:
            review.save(self.reviews_root(), self.review)

    def load_analysis(self, vid: str) -> dict | None:
        if self.job is not None:
            a = self.job.analysis(vid)
            if a is not None:
                return a
        p = self.cache_root() / vid / "analysis.json"
        try:
            mt = p.stat().st_mtime
        except OSError:
            return None
        hit = self._acache.get(vid)
        if hit and hit[0] == mt:
            return hit[1]
        try:
            a = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        self._acache[vid] = (mt, a)
        return a

    def write_analysis(self, a: dict) -> None:
        """Grava no cache uma análise mudada pela revisão (listas reagrupadas, lista própria)."""
        p = self.cache_root() / a["id"] / "analysis.json"
        if not p.parent.is_dir():
            return
        analyze._write_json(p, a)
        try:
            self._acache[a["id"]] = (p.stat().st_mtime, a)
        except OSError:
            pass

    def ready_analysis(self, vid: str) -> dict | None:
        """Análise pronta para a tela de revisão, com as listas juntadas como a revisão pede."""
        a = self.load_analysis(vid)
        if a is None or self.review is None:
            return a
        gap = float(self.review.get("group_gap_s", 8.0))
        with self.lock:
            if analyze.regroup_lists(a, gap):
                self.write_analysis(a)
        return a

    @staticmethod
    def _note_fps(v: dict, a: dict | None) -> bool:
        """Guarda na revisão a taxa de frames do vídeo (o SRT e o texto copiado precisam dela
        mesmo em outro computador, sem o cache)."""
        if a and a.get("fps") and v.get("fps") != a["fps"]:
            v["fps"] = a["fps"]
            return True
        return False

    def video_entry(self, vid: str) -> dict:
        if self.review is None:
            raise ApiError("Nenhuma revisão aberta.")
        for v in self.review["videos"]:
            if v["id"] == vid:
                return v
        raise ApiError("Vídeo não está nesta revisão.", 404)

    def video_path(self, vid: str) -> str | None:
        """Caminho do vídeo NESTE computador (só vídeos da revisão aberta; nunca um caminho qualquer)."""
        v = self.video_entry(vid)
        if self.scan:
            for x in self.scan.get("videos", []):
                if x.get("id") == vid and Path(x["path"]).is_file():
                    return x["path"]
        folder = Path(self.review.get("folder") or "")
        p = folder / v["file"]
        if p.is_file():
            return str(p)
        a = self.load_analysis(vid)
        if a and a.get("path") and Path(a["path"]).is_file() and Path(a["path"]).name == v["file"]:
            return a["path"]
        return None

    def engine_settings(self, rev: dict, s: dict) -> analyze.Settings:
        return analyze.Settings(
            sensitivity=int(rev.get("sensitivity", s["sensitivity"])),
            group_gap_s=float(rev.get("group_gap_s", s["group_gap_s"])),
            vinheta_in=s.get("vinheta_in"), vinheta_out=s.get("vinheta_out"),
            read_text=True,       # a tarja precisa do OCR mesmo com a ortografia desligada
            custom_words_file=str(appdata.custom_words_file()),
            name_expected=(rev.get("nome_tarja") or None),
            transcribe=bool(rev.get("transcribe", s["transcribe"])),
            error_phrases=list(s.get("error_phrases") or []),
            generic_names=list(s.get("generic_names") or []),
            spell_langs=appdata.spell_langs(s),
        )

    # ---------------------------------------------------------------- pasta
    def folder_info(self, path: str) -> dict:
        path = path.strip()
        if not path:
            raise ApiError("Escolha a pasta dos vídeos.")
        sc = jobs.scan_folder(Path(path).expanduser().resolve())
        s = self.settings
        prev = review.find(self.reviews_root(), sc["name"]) if sc["ok"] else None
        prof = (prev or {}).get("professor") or review.suggest_professor(sc["name"])
        entrega = (prev or {}).get("entrega")
        entrega_from = "revisão salva" if entrega else None
        if not entrega and sc.get("report") and sc["report"].get("date"):
            entrega = sc["report"]["date"][:10]
            entrega_from = "relatório de tempo"
        if not entrega and sc.get("newest_mtime"):
            entrega = datetime.fromtimestamp(sc["newest_mtime"]).date().isoformat()
            entrega_from = "data dos arquivos"
        tag = (prev or {}).get("nome_tarja") or s["tag_names"].get(prof) or ""
        return {
            "scan": {k: sc[k] for k in ("ok", "folder", "name", "total_s", "report", "warnings", "error")}
            | {"count": sum(1 for v in sc["videos"] if not v.get("error")),
               "videos": [{k: v[k] for k in ("file", "duration", "error", "detail")}
                                                      for v in sc["videos"]]},
            "prev": None if not prev else {
                "professor": prev.get("professor"), "curso": prev.get("curso"),
                "disciplina": prev.get("disciplina"), "entrega": prev.get("entrega"),
                "entrega_locked": prev.get("entrega_locked"), "nome_tarja": prev.get("nome_tarja"),
                "updated": prev.get("updated"),
                "comments": sum(len(v.get("comments", [])) for v in prev.get("videos", [])),
                "sensitivity": prev.get("sensitivity"), "group_gap_s": prev.get("group_gap_s")},
            "suggest": {"professor": prof, "curso": (prev or {}).get("curso") or "",
                        "disciplina": (prev or {}).get("disciplina") or "",
                        "entrega": entrega, "entrega_from": entrega_from, "nome_tarja": tag},
        }

    # ---------------------------------------------------------------- começar
    def start(self, body: dict) -> dict:
        folder = (body.get("folder") or "").strip()
        if not folder:
            raise ApiError("Escolha a pasta dos vídeos.")
        sc = jobs.scan_folder(Path(folder).expanduser().resolve())
        if not sc["ok"]:
            raise ApiError(sc["error"] or "Pasta sem vídeos.")
        s = self.settings
        rev = review.find(self.reviews_root(), sc["name"]) or review.new_review(sc["folder"])
        rev["folder"] = sc["folder"]
        prof = (body.get("professor") or "").strip()
        if not prof:
            raise ApiError("Preencha o professor.")
        rev["professor"] = prof
        rev["curso"] = (body.get("curso") or "").strip()
        rev["disciplina"] = (body.get("disciplina") or "").strip()
        rev["nome_tarja"] = (body.get("nome_tarja") or "").strip()
        if not rev.get("entrega_locked"):
            ent = review.parse_date(body.get("entrega"))
            if not ent:
                raise ApiError("Preencha a entrega da edição (dd/mm/aaaa).")
            rev["entrega"] = ent
            rev["entrega_locked"] = True
        rev["sensitivity"] = int(body.get("sensitivity", s["sensitivity"]))
        rev["group_gap_s"] = float(body.get("group_gap_s", s["group_gap_s"]))
        rev["spell"] = bool(body.get("spell", s["spell"]))
        rev["transcribe"] = bool(body.get("transcribe", s["transcribe"]))
        rep = sc.get("report")
        rev["report"] = None if not rep else {k: rep[k] for k in (
            "file", "project", "date", "total_raw_s", "total_edited_s", "usage_pct", "discarded_s",
            "ignored_raw", "ignored_edited", "raw")}
        rev["folder_warnings"] = [f"{v['file']}: {v['error']}." for v in sc["videos"] if v.get("error")] + sc["warnings"]
        review.merge_videos(rev, [{"id": v["id"], "file": v["file"], "duration": v["duration"]}
                                  for v in sc["videos"] if v["id"]])
        for v in rev["videos"]:
            v["report_entry"] = sc["matches"].get(v["file"])
        # lembrar para as próximas revisões
        upd = {"sensitivity": rev["sensitivity"], "group_gap_s": rev["group_gap_s"], "spell": rev["spell"],
               "transcribe": rev["transcribe"], "last_folder": str(Path(sc["folder"]).parent)}
        if rev["nome_tarja"]:
            tn = dict(s["tag_names"])
            tn[prof] = rev["nome_tarja"]
            upd["tag_names"] = tn
        appdata.save_settings(upd)
        appdata.remember("professores", prof)
        appdata.remember("cursos", rev["curso"])
        appdata.remember("disciplinas", rev["disciplina"])
        review.save(self.reviews_root(), rev)
        busy = self._running_entry()
        if busy is not None and busy["key"] != qkey(rev["project"]):
            # outra pasta está analisando: esta entra no fim da fila e a revisão aberta continua a mesma
            self._enqueue(rev, sc)
            return {"ok": True, "project": rev["project"], "queued": True, "position": self._position(rev["project"]),
                    "running": busy["project"]}
        with self.lock:
            self.review, self.scan = rev, sc
            self._touch_cache(rev)
            self._enqueue(rev, sc, front=True)
        self._pump()
        return {"ok": True, "project": rev["project"], "queued": False}

    def open_saved(self, project: str) -> dict:
        """Abre uma revisão salva. Se a pasta já está na fila, só troca a revisão aberta (a análise
        continua onde está). Se não está e a pasta existe neste computador, ela entra na fila: na
        hora quando nada está analisando, no fim da fila quando outra pasta está."""
        rev = review.find(self.reviews_root(), project)
        if rev is None:
            raise ApiError("Revisão não encontrada.", 404)
        e = self._entry(rev["project"])
        if e is not None and not e["job"].alive() and e["job"].state != "idle":
            # já analisada nesta sessão: se a pasta mudou (vídeo corrigido, "rodada 2"), analisa de novo
            folder = Path(rev.get("folder") or e["folder"])
            sc = jobs.scan_folder(folder) if folder.is_dir() else None
            ids = lambda x: {v["id"] for v in x["videos"] if v.get("id")}
            if sc and sc["ok"] and ids(sc) != ids(e["scan"]):
                with self.lock:
                    self.queue.remove(e)
                e = None
        if e is not None:
            with self.lock:
                self.review, self.scan = rev, e["scan"]
            self._touch_cache(rev)
            return {"ok": True, "folder_found": True, "queued": e["job"].state == "idle", "ready_n": self._ready_n()}
        folder = Path(rev.get("folder") or "")
        with self.lock:
            self.review = rev
            self.scan = None
        self._touch_cache(rev)
        if rev.get("folder") and folder.is_dir():
            sc = jobs.scan_folder(folder)
            if sc["ok"]:
                review.merge_videos(rev, [{"id": v["id"], "file": v["file"], "duration": v["duration"]}
                                          for v in sc["videos"] if v["id"]])
                busy = self._running_entry()
                with self.lock:
                    self.scan = sc
                    self.save_review()
                    self._enqueue(rev, sc, front=busy is None)
                self._pump()
                return {"ok": True, "folder_found": True, "queued": busy is not None, "ready_n": self._ready_n()}
        return {"ok": True, "folder_found": False, "queued": False, "ready_n": self._ready_n()}

    def _ready_n(self) -> int | None:
        """Nº do primeiro vídeo da revisão aberta que já pode ser revisado (para abrir direto nele)."""
        for k, v in enumerate((self.review or {}).get("videos", [])):
            if self.load_analysis(v["id"]) is not None:
                return k + 1
        return None

    # ---------------------------------------------------------------- fila de pastas
    def _entry(self, project: str | None) -> dict | None:
        k = qkey(project)
        for e in self.queue:
            if e["key"] == k:
                return e
        return None

    def _running_entry(self) -> dict | None:
        for e in self.queue:
            if e["job"].alive():
                return e
        return None

    def _any_alive(self) -> bool:
        return any(e["job"].alive() for e in self.queue) or any(j.alive() for j in self._dying)

    def _make_job(self, rev: dict, sc: dict) -> jobs.AnalysisJob:
        return jobs.AnalysisJob(sc, self.engine_settings(rev, appdata.load_settings()), self.cache_root(),
                                on_done=self._job_done)

    def _retire(self, job: jobs.AnalysisJob) -> None:
        """Cancela uma análise; ela fica em _dying até parar de fato (a próxima só começa depois)."""
        if job.alive():
            job.cancel()
            self._dying.append(job)

    def _enqueue(self, rev: dict, sc: dict, front: bool = False) -> dict:
        """Põe a pasta na fila (ou refaz o pedido dela, com as escolhas novas). Não começa nada:
        quem começa é _pump, quando nenhuma análise está rodando."""
        with self.lock:
            old = self._entry(rev["project"])
            if old is not None:
                self._retire(old["job"])
                self.queue.remove(old)
            e = {"key": qkey(rev["project"]), "project": rev["project"], "folder": sc["folder"],
                 "professor": rev.get("professor") or "", "scan": sc, "job": self._make_job(rev, sc)}
            self.queue.append(e)
            self._order(e if front else None)
        self._save_queue()
        return e

    def _order(self, first: dict | None = None, second: dict | None = None) -> None:
        """Ordem da lista: prontas/analisando primeiro, depois as que esperam (first e second na frente)."""
        started = [e for e in self.queue if e["job"].state != "idle"]
        waiting = [e for e in self.queue if e["job"].state == "idle"]
        for x in (second, first):
            if x is not None and x in waiting:
                waiting.remove(x)
                waiting.insert(0, x)
        self.queue[:] = started + waiting

    def _pump(self) -> None:
        """Começa a próxima pasta da fila, se nenhuma análise está rodando."""
        with self.lock:
            if self._stopping or self._any_alive():
                return
            for e in self.queue:
                if e["job"].state == "idle":
                    e["job"].start()
                    break
        self._save_queue()

    def _job_done(self, job: jobs.AnalysisJob) -> None:
        with self.lock:
            self._dying = [j for j in self._dying if j is not job and j.alive()]
        self._pump()

    def _position(self, project: str) -> int:
        """1 = a próxima a começar."""
        waiting = [e for e in self.queue if e["job"].state == "idle"]
        for k, e in enumerate(waiting):
            if e["key"] == qkey(project):
                return k + 1
        return 0

    def queue_now(self, project: str) -> dict:
        """"Analisar esta agora": passa na frente; a que estava rodando volta para a fila logo depois
        (os vídeos que ela já terminou ficam no cache e não são refeitos)."""
        with self.lock:
            e = self._entry(project)
            if e is None:
                raise ApiError("Esta pasta não está na fila.", 404)
            if e["job"].state != "idle":
                return {"ok": True}
            r = self._running_entry()
            if r is not None:
                rev_r = review.find(self.reviews_root(), r["project"])
                if rev_r is None:
                    raise ApiError("A revisão da pasta que está analisando não foi encontrada.", 404)
                self._retire(r["job"])
                r["job"] = self._make_job(rev_r, r["scan"])
            self._order(e, r)
        self._pump()
        return {"ok": True}

    def queue_remove(self, project: str) -> dict:
        """Tira a pasta da lista (se está analisando, a análise para; a revisão salva continua)."""
        with self.lock:
            e = self._entry(project)
            if e is None:
                return {"ok": True}
            self._retire(e["job"])
            self.queue.remove(e)
        self._pump()
        return {"ok": True}

    def queue_view(self) -> dict:
        open_key = qkey((self.review or {}).get("project"))
        out = []
        pos = 0
        with self.lock:
            entries = list(self.queue)
        for e in entries:
            j = e["job"]
            snap = j.snapshot()
            st = {"idle": "wait"}.get(j.state, j.state)
            if st == "wait":
                pos += 1
            out.append({"project": e["project"], "professor": e["professor"], "folder": e["folder"],
                        "status": st, "position": pos if st == "wait" else 0,
                        "done": snap["done"], "total": snap["total"], "failed": snap["failed"],
                        "pct": snap["pct"], "eta_s": snap["eta_s"], "open": e["key"] == open_key})
        waiting_eta = sum(x["eta_s"] or 0 for x in out if x["status"] in ("wait", "running", "paused"))
        return {"entries": out, "restore": self.restore_list(), "eta_total_s": waiting_eta,
                "running": next((x["project"] for x in out if x["status"] in ("running", "paused")), None)}

    def next_folder(self) -> dict | None:
        """A pasta seguinte da fila, para o botão "Próxima pasta" na última aula."""
        cur = qkey((self.review or {}).get("project"))
        with self.lock:
            entries = list(self.queue)
        keys = [e["key"] for e in entries]
        rest = entries[keys.index(cur) + 1:] if cur in keys else entries
        for e in rest:
            j = e["job"]
            snap = j.snapshot()
            if j.state == "done":
                txt = "análise pronta"
            elif j.alive():
                txt = f"analisando · {snap['done']} de {snap['total']} vídeos prontos"
            elif j.state == "idle":
                txt = "esperando na fila"
            else:
                txt = "análise interrompida"
            return {"project": e["project"], "status_text": txt}
        return None

    # ---- fila que ficou da última vez (o app fechou com pastas esperando)
    def _queue_path(self) -> Path:
        return appdata.home() / QUEUE_FILE

    def restore_list(self) -> list[dict]:
        if self._restore is None:
            try:
                data = json.loads(self._queue_path().read_text(encoding="utf-8"))
                items = [x for x in data.get("pending", []) if isinstance(x, dict) and x.get("project")]
            except (OSError, ValueError, AttributeError):
                items = []
            self._restore = [{"project": str(x["project"]), "folder": str(x.get("folder") or "")} for x in items]
        have = {e["key"] for e in self.queue}
        return [x for x in self._restore if qkey(x["project"]) not in have]

    def _save_queue(self) -> None:
        """Guarda as pastas que ainda não terminaram (e a fila antiga não retomada), para não perder
        a fila se o app fechar."""
        with self.lock:
            pend = [{"project": e["project"], "folder": e["folder"]} for e in self.queue
                    if e["job"].state in ("idle", "running", "paused", "cancelled")]
        pend += self.restore_list()
        try:
            p = self._queue_path()
            tmp = p.with_suffix(".tmp")
            tmp.write_text(json.dumps({"pending": pend}, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(p)
        except OSError:
            pass

    def queue_restore(self, keep: bool) -> dict:
        """Continuar (ou descartar) a fila que ficou da última vez."""
        items = self.restore_list()
        added, missing = 0, []
        self._restore = []
        if keep:
            for x in items:
                rev = review.find(self.reviews_root(), x["project"])
                folder = Path((rev or {}).get("folder") or x["folder"] or "")
                sc = jobs.scan_folder(folder) if rev and folder.is_dir() else None
                if not sc or not sc["ok"]:
                    missing.append(x["project"])
                    continue
                review.merge_videos(rev, [{"id": v["id"], "file": v["file"], "duration": v["duration"]}
                                          for v in sc["videos"] if v["id"]])
                review.save(self.reviews_root(), rev)
                self._enqueue(rev, sc)
                added += 1
        self._save_queue()
        self._pump()
        return {"ok": True, "added": added, "missing": missing}

    def stop_all(self) -> None:
        with self.lock:
            self._stopping = True
            for e in self.queue:
                e["job"].cancel()
            for j in self._dying:
                j.cancel()

    # ---------------------------------------------------------------- telas
    def review_view(self) -> dict:
        rev = self.review
        if rev is None:
            return {"review": None}
        sens = int(rev.get("sensitivity", 55))
        rows = []
        noted = False
        for k, v in enumerate(rev["videos"]):
            a = self.ready_analysis(v["id"])
            noted |= self._note_fps(v, a)
            row = summary.video_row(a, sens, spell=rev.get("spell", True), dismissed=v.get("dismissed")) if a else None
            rows.append({"n": k + 1, "id": v["id"], "file": v["file"], "duration": v["duration"],
                         "editor": v.get("editor"), "missing": v.get("missing", False),
                         "comments": len(v.get("comments", [])), "row": row})
        if noted:
            self.save_review()
        ready = [r["row"] for r in rows if r["row"]]
        tpos, skin = scope_marks()
        return {
            "review": {k: rev.get(k) for k in ("project", "folder", "professor", "curso", "disciplina", "nome_tarja",
                                               "entrega", "entrega_locked", "sensitivity", "group_gap_s", "spell",
                                               "transcribe", "report", "folder_warnings", "updated")},
            "videos": rows,
            "audio": summary.audio_totals(ready),
            "editors": appdata.active_editors(),
            "scope": {"targets": tpos, "skin": skin, "ids": [r["id"] for r in rows if r["row"]]},
            "job": self.job.snapshot() if self.job else None,
        }

    def set_editor(self, body: dict) -> dict:
        rev = self.review
        if rev is None:
            raise ApiError("Nenhuma revisão aberta.")
        ed = body.get("editor") or None
        target = body.get("id")
        for v in rev["videos"]:
            if target == "all" or v["id"] == target:
                v["editor"] = ed
        self.save_review()
        return {"ok": True}

    def set_sensitivity(self, body: dict) -> dict:
        rev = self.review
        if rev is None:
            raise ApiError("Nenhuma revisão aberta.")
        rev["sensitivity"] = max(0, min(100, int(body.get("sensitivity", 55))))
        self.save_review()
        return {"ok": True}

    # ---------------------------------------------------------------- 4 · revisão
    def _job_status(self, vid: str) -> dict | None:
        if self.job is None:
            return None
        for v in self.job.videos:
            if v["id"] == vid:
                return {"status": v["status"], "pct": v["pct"], "error": v.get("error")}
        return None

    def video_view(self, n: int) -> dict:
        rev = self.review
        if rev is None:
            return {"review": None}
        vids = rev["videos"]
        if not vids:
            raise ApiError("Esta revisão não tem vídeos.")
        n = max(1, min(len(vids), int(n)))
        v = vids[n - 1]
        sens = int(rev.get("sensitivity", 55))
        spell_on = bool(rev.get("spell", True))
        tabs = []
        noted = False
        for k, x in enumerate(vids):
            a2 = self.ready_analysis(x["id"])
            noted |= self._note_fps(x, a2)
            tabs.append({"n": k + 1, "id": x["id"], "file": x["file"], "missing": x.get("missing", False),
                         "ready": a2 is not None, "comments": len(x.get("comments", [])),
                         "warnings": len(summary.warnings_of(a2, spell_on, x.get("dismissed"))) if a2 else 0})
        if noted:
            self.save_review()
        s = self.settings
        out = {
            "review": {k: rev.get(k) for k in ("project", "professor", "curso", "disciplina", "sensitivity",
                                               "group_gap_s", "spell")},
            "n": n, "total": len(vids), "tabs": tabs,
            "video": {k: v.get(k) for k in ("id", "file", "duration", "editor", "missing", "round")},
            "comments": sorted(v.get("comments", []), key=lambda c: c["frame"]),
            "editors": appdata.active_editors(s),
            "time_format": s.get("time_format", "seconds"),
            "clip_half_s": frames.clip_half(s.get("clip_half_s")),
            "clip_choices": list(frames.CLIP_HALF_CHOICES),
            "next_folder": self.next_folder() if n == len(vids) else None,
            "job": self._job_status(v["id"]),
            "ready": False,
            "scope": dict(zip(("targets", "skin"), scope_marks())),
        }
        a = self.ready_analysis(v["id"])
        if a is None:
            return out
        path = self.video_path(v["id"])
        it = summary.review_items(a, sens, spell_on, v.get("dismissed"))
        if s.get("nav_slides"):            # opcional: cada slide em tela cheia vira um item navegável
            merged = sorted(it["items"] + summary.slide_pages(a), key=lambda x: (x["frame"], x["kind"] == "slide"))
            for k, x in enumerate(merged):
                x["i"] = k
            it["items"] = merged
        out["nav_slides"] = bool(s.get("nav_slides"))
        au = a.get("audio") or {}
        out.update({
            "ready": True,
            "meta": {"fps": a["fps"], "frames": a["frames"], "width": a["width"], "height": a["height"],
                     "duration": a["duration"], "content": a.get("content"), "has_video": path is not None,
                     # o navegador tenta tocar o original; se não der (ProRes, HEVC…), usa o trecho em MP4
                     "playable": bool(path) and Path(path).suffix.lower() in VIDEO_TYPES,
                     "speech": (a.get("speech") or {}).get("status"),
                     "text": (a.get("text") or {}).get("status"),
                     "timings": a.get("timings")},          # tempo de cada etapa da análise (diagnóstico)
            "items": it["items"], "cuts": it["cuts"], "counts": it["counts"],
            "slides": summary.slide_spans(a),          # trechos com slide em tela cheia (marca na linha do tempo)
            "audio": None if not au else {
                "step": au.get("envelope_step", 0.1), "env": au.get("envelope_db") or [],
                "min_db": au.get("min_db"), "min_time": au.get("min_time"),
                "peak_dbfs": au.get("peak_dbfs"), "peak_time": au.get("peak_time"),
                "avg_db": au.get("avg_db"), "marks": it["audio_marks"]},
            "vinheta": {k: (a.get("vinheta") or {}).get(k) for k in ("frames_in", "frames_out", "start_found",
                                                                      "end_found")},
        })
        return out

    def _rev_video(self, body: dict) -> dict:
        if self.review is None:
            raise ApiError("Nenhuma revisão aberta.")
        return self.video_entry(str(body.get("id") or ""))

    def set_comment(self, body: dict) -> dict:
        """Um comentário por frame: texto vazio apaga. Salva a revisão na hora."""
        v = self._rev_video(body)
        try:
            frame = int(body.get("frame"))
        except (TypeError, ValueError):
            raise ApiError("Frame inválido.")
        text = (body.get("text") or "").strip()
        if len(text) > 4000:
            raise ApiError("Comentário longo demais.")
        cs = v.setdefault("comments", [])
        cur = next((c for c in cs if c["frame"] == frame), None)
        now = review.now_text()
        with self.lock:
            if not text:
                if cur is not None:
                    cs.remove(cur)
            elif cur is None:
                cs.append({"cid": uuid.uuid4().hex[:10], "frame": frame, "text": text,
                           "source": (body.get("source") or "livre")[:60], "label": (body.get("label") or "")[:60],
                           "selected": True, "with_frame": True, "created": now, "updated": now})
            else:
                cur["text"] = text
                cur["updated"] = now
            cs.sort(key=lambda c: c["frame"])
            self.save_review()
        return {"ok": True, "comments": cs}

    def dismiss(self, body: dict) -> dict:
        """"Ignorar" um aviso neste vídeo (ou desfazer). Some da contagem, continua visível apagado."""
        v = self._rev_video(body)
        key = str(body.get("key") or "")
        if not key or len(key) > 200:
            raise ApiError("Aviso inválido.")
        lst = v.setdefault("dismissed", [])
        with self.lock:
            if body.get("undo"):
                if key in lst:
                    lst.remove(key)
            elif key not in lst:
                lst.append(key)
            self.save_review()
        return {"ok": True, "dismissed": lst}

    def accept_word(self, body: dict) -> dict:
        """"Aceitar": a palavra entra na lista própria e a ortografia é refeita em todos os vídeos
        da revisão (sem ler o vídeo de novo)."""
        rev = self.review
        if rev is None:
            raise ApiError("Nenhuma revisão aberta.")
        word = spell.nfc((body.get("word") or "").strip())
        if not word or len(word) > 80 or any(c.isspace() for c in word):
            raise ApiError("Palavra inválida.")
        spell.add_to_custom(appdata.custom_words_file(), word)
        es = self.engine_settings(rev, self.settings)
        checker = analyze.make_checker(es)
        changed = 0
        with self.lock:
            for v in rev["videos"]:
                a = self.load_analysis(v["id"])
                if a is None or (a.get("text") or {}).get("status") != "ok":
                    continue
                analyze.refresh_text_checks(a, es, checker=checker)
                self.write_analysis(a)
                changed += 1
        return {"ok": True, "videos": changed}

    def adjust(self, body: dict) -> dict:
        """Sensibilidade e "juntar listas" mudados na tela de revisão (sem reanalisar)."""
        rev = self.review
        if rev is None:
            raise ApiError("Nenhuma revisão aberta.")
        with self.lock:
            if "sensitivity" in body:
                rev["sensitivity"] = max(0, min(100, int(body["sensitivity"])))
            if "group_gap_s" in body:
                g = float(body["group_gap_s"])
                if g not in (0.0, 4.0, 8.0, 12.0):
                    raise ApiError("Intervalo inválido.")
                rev["group_gap_s"] = g
            self.save_review()
            appdata.save_settings({k: rev[k] for k in ("sensitivity", "group_gap_s")})
        return {"ok": True}

    def _frame_ctx(self, q: dict):
        vid = q.get("id", "")
        if not vid.isalnum():
            raise ApiError("Vídeo inválido.")
        a = self.load_analysis(vid)
        if a is None:
            raise ApiError("Vídeo ainda não analisado.", 404)
        try:
            f = int(q.get("f", "0"))
        except ValueError:
            raise ApiError("Frame inválido.")
        f = max(0, min(f, int(a["frames"]) - 1))
        return vid, a, f, self.video_path(vid), parse_rate(a["fps"])

    def frame_jpeg(self, q: dict) -> tuple[bytes, bool]:
        """(JPEG, exato). exato=False: pediu o frame cheio, mas o vídeo não está aqui e veio a
        miniatura (o navegador não deve guardar essa resposta)."""
        vid, a, f, path, rate = self._frame_ctx(q)
        size = "full" if q.get("s") == "full" else "thumb"
        try:
            p = self.frames.jpeg(vid, path, rate, f, size, int(a["width"]))
        except media.MediaError as e:
            raise ApiError(str(e), 500)
        if p is None:
            raise ApiError("Frame indisponível: o vídeo não está neste computador.", 404)
        return p.read_bytes(), (size == "thumb" or p.parent.name == "full")

    def pick(self, body: dict) -> dict:
        vid, a, f, path, rate = self._frame_ctx({k: str(body.get(k, "")) for k in ("id", "f")})
        if path is None:
            raise ApiError("O conta-gotas lê o vídeo original, que não está neste computador.", 404)
        try:
            x, y = int(body.get("x")), int(body.get("y"))
        except (TypeError, ValueError):
            raise ApiError("Ponto inválido.")
        return self.frames.pick(vid, path, rate, f, int(a["width"]), int(a["height"]), x, y,
                                int(body.get("size") or 9))

    def frame_scope(self, q: dict) -> bytes:
        vid, a, f, path, rate = self._frame_ctx(q)
        if path is None:
            raise ApiError("Os gráficos leem o vídeo original, que não está neste computador.", 404)
        kind = q.get("k", "luma")
        if kind not in ("luma", "parade", "vector"):
            raise ApiError("Gráfico inválido.")
        return self.frames.scope_png(vid, path, rate, f, int(a["width"]), int(a["height"]), kind)

    def clip_file(self, q: dict) -> Path:
        vid, a, f, path, rate = self._frame_ctx(q)
        if path is None:
            raise ApiError("O vídeo não está neste computador.", 404)
        try:
            p, _start = self.frames.clip(vid, path, rate, f, float(a["duration"]), q.get("fmt", "mp4"),
                                         frames.clip_half(q.get("h", frames.CLIP_HALF_S)))
        except media.MediaError as e:
            raise ApiError(str(e), 500)
        return p

    def media_file(self, q: dict) -> tuple[Path, str]:
        vid = q.get("id", "")
        if not vid.isalnum():
            raise ApiError("Vídeo inválido.")
        path = self.video_path(vid)
        if path is None:
            raise ApiError("O vídeo não está neste computador.", 404)
        p = Path(path)
        return p, VIDEO_TYPES.get(p.suffix.lower(), "video/mp4")

    def scope_png(self, ids: list[str]) -> bytes:
        tot = np.zeros((128, 128), np.int64)
        for vid in ids:
            p = self.cache_root() / vid / "scope.npy"
            if p.exists():
                try:
                    tot += np.load(p).astype(np.int64)
                except (OSError, ValueError):
                    pass
        img = scopes.average_scope_png(tot).resize((512, 512), resample=1)   # 1 = LANCZOS
        buf = io.BytesIO()
        img.save(buf, "PNG")
        return buf.getvalue()

    # ================================================================ etapa 5
    def _need_review(self) -> dict:
        if self.review is None:
            raise ApiError("Nenhuma revisão aberta.")
        return self.review

    def _job_running(self) -> bool:
        return self._any_alive()

    def _queued_ids(self) -> set[str]:
        """Vídeos das pastas na fila que ainda vão ser (ou estão sendo) analisados."""
        with self.lock:
            return {v["id"] for e in self.queue if e["job"].state in ("idle", "running", "paused")
                    for v in e["job"].videos}

    def _touch_cache(self, rev: dict) -> None:
        """Marca o cache dos vídeos da revisão como usado (a limpeza automática olha a data)."""
        now = time.time()
        for v in rev.get("videos", []):
            d = self.cache_root() / v["id"]
            if d.is_dir():
                try:
                    os.utime(d, (now, now))
                except OSError:
                    pass

    def review_frames_dir(self, rev: dict) -> Path:
        return review.path_for(self.reviews_root(), rev["project"]).parent / "frames"

    def comment_frame(self, vid: str, f: int, size: str = "full") -> tuple[bytes, bool] | None:
        """Imagem de um frame comentado: do vídeo/cache; se não houver, a que veio no pacote."""
        rev = self._need_review()
        v = self.video_entry(vid)
        a = self.load_analysis(vid)
        if a is not None:
            f = max(0, min(int(f), int(a["frames"]) - 1))
            try:
                p = self.frames.jpeg(vid, self.video_path(vid), parse_rate(a["fps"]), f,
                                     "full" if size == "full" else "thumb", int(a["width"]))
            except media.MediaError:
                p = None
            if p is not None:
                return p.read_bytes(), (size != "full" or p.parent.name == "full")
        name = (rev.get("pkg_frames") or {}).get(f"{v['id']}:{int(f)}")
        if name:
            p = self.review_frames_dir(rev) / Path(name).name
            if p.is_file():
                return p.read_bytes(), True
        return None

    def _frame_file(self, v: dict, f: int) -> Path | None:
        """Para o pacote: JPEG cheio do frame (vídeo ou cache), ou a imagem que veio de outro pacote."""
        a = self.load_analysis(v["id"])
        if a is not None:
            try:
                p = self.frames.jpeg(v["id"], self.video_path(v["id"]), parse_rate(a["fps"]),
                                     max(0, min(int(f), int(a["frames"]) - 1)), "full", int(a["width"]))
            except media.MediaError:
                p = None
            if p is not None:
                return p
        name = (self.review.get("pkg_frames") or {}).get(f"{v['id']}:{int(f)}")
        if name:
            p = self.review_frames_dir(self.review) / Path(name).name
            if p.is_file():
                return p
        return None

    # ---------------------------------------------------------------- 5 · resumo final
    def final_view(self) -> dict:
        rev = self.review
        if rev is None:
            return {"review": None}
        s = self.settings
        rows = export.comment_rows(rev, s.get("time_format", "seconds"))
        folder = Path(rev.get("folder") or "")
        jobs_ = export.srt_jobs(rev)
        return {
            "review": {k: rev.get(k) for k in ("project", "professor", "curso", "disciplina", "entrega",
                                               "entrega_locked", "report", "updated")},
            "videos": [{"n": k + 1, "id": v["id"], "file": v["file"], "missing": v.get("missing", False),
                        "editor": v.get("editor"), "comments": len(v.get("comments", []))}
                       for k, v in enumerate(rev["videos"])],
            "rows": rows,
            "hours": export.editor_hours(rev),
            "srt": {"videos": len(jobs_), "block_s": s.get("srt_block_s", 3), "prefix": s.get("srt_prefix", "CORRIGIR:"),
                    "where": s.get("srt_where", "beside"), "folder_found": bool(rev.get("folder")) and folder.is_dir(),
                    "names": [j["name"] for j in jobs_]},
            "time_format": s.get("time_format", "seconds"),
        }

    def final_mark(self, body: dict) -> dict:
        """Marcar/desmarcar e com/sem frame (um comentário, ou "all")."""
        rev = self._need_review()
        target = body.get("cid")
        changed = 0
        with self.lock:
            for v in rev["videos"]:
                for c in v.get("comments", []):
                    if target != "all" and c.get("cid") != target:
                        continue
                    for k in ("selected", "with_frame"):
                        if k in body:
                            c[k] = bool(body[k])
                    changed += 1
            if not changed:
                raise ApiError("Comentário não encontrado.", 404)
            self.save_review()
        return {"ok": True, "changed": changed}

    def final_srt(self) -> dict:
        rev = self._need_review()
        s = self.settings
        if not export.srt_jobs(rev):
            raise ApiError("Nenhum comentário marcado: não há SRT para gerar.")
        folder = Path(rev.get("folder") or "")
        if not rev.get("folder") or not folder.is_dir():
            return {"ok": True, "zip": True}
        try:
            out = export.write_srts(rev, folder, s.get("srt_block_s", 3), s.get("srt_prefix", "CORRIGIR:"),
                                    s.get("srt_where", "beside"))
        except OSError as e:
            raise ApiError(f"Não deu para gravar os SRT na pasta dos vídeos ({e.strerror or e}). "
                           "Baixe em .zip pelo botão ao lado.", 500)
        return {"ok": True, "zip": False, **out}

    def final_srt_zip(self) -> bytes:
        rev = self._need_review()
        s = self.settings
        return export.srt_zip(rev, s.get("srt_block_s", 3), s.get("srt_prefix", "CORRIGIR:"))

    # ---------------------------------------------------------------- 6 · pacote
    def _default_export_dir(self) -> str:
        s = self.settings
        if s.get("export_dir") and Path(s["export_dir"]).is_dir():
            return s["export_dir"]
        for cand in (Path.home() / "Desktop", Path.home() / "Área de Trabalho", Path.home()):
            if cand.is_dir():
                return str(cand)
        return str(Path.home())

    def package_info(self) -> dict:
        rev = self.review
        out = {"export_dir": self._default_export_dir(), "review": None}
        if rev is None:
            return out
        n_frames = 0
        for v in rev["videos"]:
            a = self.load_analysis(v["id"])
            has_src = self.video_path(v["id"]) is not None or (a is not None)
            for c in v.get("comments", []):
                if has_src or (rev.get("pkg_frames") or {}).get(f"{v['id']}:{c['frame']}"):
                    n_frames += 1
        out["review"] = {
            "project": rev["project"], "entrega": rev.get("entrega"), "professor": rev.get("professor"),
            "comments": export.comment_count(rev), "videos": len(rev["videos"]),
            "editors_marked": sum(1 for v in rev["videos"] if v.get("editor")), "frames": n_frames,
            "est_bytes": n_frames * 450_000, "name": export.package_name(rev),
        }
        return out

    def package_export(self, body: dict) -> dict:
        rev = self._need_review()
        dest = Path(str(body.get("dest") or "")).expanduser()
        if not str(body.get("dest") or "").strip() or not dest.is_dir():
            raise ApiError("Escolha uma pasta que exista para salvar o pacote.")
        try:
            out = export.export_package(rev, dest.resolve(), self._frame_file)
        except OSError as e:
            raise ApiError(f"Não deu para gravar o pacote nessa pasta ({e.strerror or e}).", 500)
        appdata.save_settings({"export_dir": str(dest.resolve())})
        return {"ok": True, **out}

    def _scan_ids(self, folder: str | None) -> tuple[set, str | None]:
        if not folder:
            return set(), None
        p = Path(folder).expanduser()
        if not p.is_dir():
            return set(), None
        sc = jobs.scan_folder(p.resolve())
        return {v["id"] for v in sc.get("videos", []) if v.get("id")}, sc.get("folder")

    def package_inspect(self, body: dict) -> dict:
        try:
            data, base = export.read_package(str(body.get("path") or ""))
        except export.PackageError as e:
            raise ApiError(str(e))
        local = review.find(self.reviews_root(), data["project"])
        folder = (body.get("videos_folder") or "").strip() or (local or {}).get("folder")
        ids, folder_ok = self._scan_ids(folder)
        frames_ = export.package_frames(data, base)
        return {
            "project": data["project"], "professor": data.get("professor"), "curso": data.get("curso"),
            "entrega": data.get("entrega"), "updated": data.get("updated"),
            "exported": (data.get("package") or {}).get("exported"),
            "comments": export.comment_count(data), "frames": len(frames_),
            "videos": [{"n": k + 1, "file": v["file"], "duration": v.get("duration"), "found": v["id"] in ids,
                        "comments": len(v.get("comments", []))} for k, v in enumerate(data["videos"])],
            "videos_folder": folder_ok,
            "local": None if not local else {"updated": local.get("updated"), "comments": export.comment_count(local),
                                             "same": export.same_content(local, data)},
        }

    def package_open(self, body: dict) -> dict:
        try:
            data, base = export.read_package(str(body.get("path") or ""))
        except export.PackageError as e:
            raise ApiError(str(e))
        root = self.reviews_root()
        local = review.find(root, data["project"])
        choice = body.get("choice")
        if local is not None and choice not in ("keep", "package", "merge"):
            raise ApiError("Já existe uma revisão deste projeto neste computador: escolha manter, usar a do pacote ou juntar.")
        pkg_frames = export.package_frames(data, base)
        if local is None or choice == "package":
            rev = json.loads(json.dumps(data))
        elif choice == "keep":
            rev = local
        else:
            rev = export.merge_reviews(local, data)
        rev.pop("package", None)
        rev.pop("_source", None)
        if local is not None:
            rev["project"] = local["project"]          # mesma pasta de revisão (a grafia daqui)
        rev["key"] = review.project_key(rev["project"])
        rev.setdefault("review_version", review.REVIEW_VERSION)
        rev.setdefault("created", review.now_text())
        vf = (body.get("videos_folder") or "").strip()
        if vf and Path(vf).expanduser().is_dir():
            rev["folder"] = str(Path(vf).expanduser().resolve())
        elif local is not None and local.get("folder"):
            rev["folder"] = local["folder"]
        else:
            rev["folder"] = rev.get("folder") or ""
        if choice != "keep" and pkg_frames:
            fdir = review.path_for(root, rev["project"]).parent / "frames"
            fdir.mkdir(parents=True, exist_ok=True)
            m = dict(rev.get("pkg_frames") or {}) if choice == "merge" else {}
            stamp = time.strftime("%Y%m%d%H%M%S")
            for key, src in pkg_frames.items():
                name = f"{stamp}_{src.name}"
                shutil.copyfile(src, fdir / name)
                m[key] = name
            rev["pkg_frames"] = m
        for k in ("professor", "curso", "disciplina"):
            appdata.remember({"professor": "professores", "curso": "cursos", "disciplina": "disciplinas"}[k], rev.get(k))
        review.save(root, rev)
        res = self.open_saved(rev["project"])
        return {**res, "project": rev["project"], "comments": export.comment_count(rev)}

    # ---------------------------------------------------------------- 7 · relatório do mês
    def month_dirs(self) -> list[Path]:
        s = self.settings
        dirs = [self.reviews_root()]
        if s.get("report_dir"):
            dirs.append(Path(s["report_dir"]))
        return dirs

    def month(self, m: str | None) -> tuple[dict, int, int]:
        if m and not re.fullmatch(r"\d{4}-\d{2}", m):
            raise ApiError("Mês inválido.")
        revs, read, dup = export.find_reviews(self.month_dirs())
        if self.review is not None:          # a revisão aberta, como está agora
            k = self.review.get("key") or review.project_key(self.review["project"])
            revs = [r for r in revs if (r.get("key") or review.project_key(r["project"])) != k] + [self.review]
        return export.month_report(revs, m or None), read, dup

    def month_view(self, m: str | None) -> dict:
        rep, read, dup = self.month(m)
        s = self.settings
        return {**rep, "reviews_read": read, "duplicates": dup,
                "dirs": [str(d) for d in self.month_dirs()], "report_dir": s.get("report_dir"),
                "reviews_dir": str(self.reviews_root())}

    # ---------------------------------------------------------------- configurações
    def cache_list(self) -> dict:
        root = self.cache_root()
        owner: dict[str, dict] = {}
        for p in Path(self.reviews_root()).glob("*/revisao.json"):
            try:
                r = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                continue
            for v in r.get("videos", []):
                owner.setdefault(v.get("id"), r)
        groups: dict[str, dict] = {}
        total = 0
        for d in sorted(root.iterdir()) if root.is_dir() else []:
            if not d.is_dir() or not d.name.isalnum():
                continue
            size, newest = appdata.dir_size(d)
            newest = max(newest, d.stat().st_mtime)
            total += size
            r = owner.get(d.name)
            key = r["project"] if r else ""
            g = groups.setdefault(key, {
                "project": key, "label": " · ".join(x for x in ((r or {}).get("professor"), (r or {}).get("disciplina")
                                                                 or (r or {}).get("curso")) if x) or key or "Vídeos sem revisão salva",
                "entrega": (r or {}).get("entrega"), "videos": 0, "bytes": 0, "newest": 0.0,
                "open": bool(self.review and r and r.get("key") == self.review.get("key"))})
            g["videos"] += 1
            g["bytes"] += size
            g["newest"] = max(g["newest"], newest)
        out = sorted(groups.values(), key=lambda g: -g["newest"])
        return {"total_bytes": total, "groups": out, "folder": str(root)}

    def cache_clear(self, body: dict) -> dict:
        root = self.cache_root()
        open_ids = {v["id"] for v in (self.review or {}).get("videos", [])}
        if body.get("all"):
            ids = [d.name for d in root.iterdir() if d.is_dir() and d.name.isalnum()] if root.is_dir() else []
        else:
            project = str(body.get("project") or "")
            ids = []
            owned = set()
            for p in Path(self.reviews_root()).glob("*/revisao.json"):
                try:
                    r = json.loads(p.read_text(encoding="utf-8"))
                except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                    continue
                vids = {v.get("id") for v in r.get("videos", [])}
                owned |= vids
                if r.get("project") == project:
                    ids += [x for x in vids if x]
            if not project:      # "Vídeos sem revisão salva"
                ids = [d.name for d in root.iterdir() if d.is_dir() and d.name.isalnum() and d.name not in owned]
        if self._queued_ids() & set(ids):
            raise ApiError("Estes vídeos estão na fila da análise. Espere a análise terminar (ou tire a pasta da fila) para limpar.")
        freed = 0
        for vid in ids:
            d = root / vid
            if vid.isalnum() and d.is_dir():
                freed += appdata.dir_size(d)[0]
                shutil.rmtree(d, ignore_errors=True)
                self._acache.pop(vid, None)
        return {"ok": True, "videos": len(ids), "freed": freed}

    def clean_old_cache(self) -> int:
        """Limpeza automática: apaga do cache o que não é usado há N dias (nunca a revisão aberta)."""
        days = int(self.settings.get("cache_auto_days") or 0)
        if days <= 0:
            return 0
        root = self.cache_root()
        limit = time.time() - days * 86400
        open_ids = {v["id"] for v in (self.review or {}).get("videos", [])} | self._queued_ids()
        n = 0
        for d in list(root.iterdir()) if root.is_dir() else []:
            if not d.is_dir() or not d.name.isalnum() or d.name in open_ids:
                continue
            try:
                newest = max(d.stat().st_mtime, appdata.dir_size(d)[1])
            except OSError:
                continue
            if newest < limit:
                shutil.rmtree(d, ignore_errors=True)
                n += 1
        return n

    def settings_view(self) -> dict:
        s = self.settings
        return {
            "settings": {k: s.get(k) for k in ("sensitivity", "group_gap_s", "transcribe", "spell", "spell_en", "spell_la",
                                               "time_format", "srt_block_s", "srt_prefix", "srt_where",
                                               "cache_auto_days", "error_phrases", "generic_names")},
            "editors": s.get("editors", []),
            "folders": {"cache_dir": str(self.cache_root()), "reviews_dir": str(self.reviews_root()),
                        "report_dir": s.get("report_dir"),
                        "custom": {k: bool(s.get(k)) for k in ("cache_dir", "reviews_dir")}},
            "words": spell.load_custom(appdata.custom_words_file()),
            "home": str(appdata.home()),
            "review_open": self.review is not None,
        }

    def _refresh_open(self, text: bool = False, speech_: bool = False) -> int:
        """Refaz avisos da revisão aberta sem ler os vídeos (ortografia/tarja e/ou falas)."""
        rev = self.review
        if rev is None:
            return 0
        es = self.engine_settings(rev, self.settings)
        checker = analyze.make_checker(es) if text else None
        n = 0
        with self.lock:
            for v in rev["videos"]:
                a = self.load_analysis(v["id"])
                if a is None:
                    continue
                if text and (a.get("text") or {}).get("status") == "ok":
                    analyze.refresh_text_checks(a, es, checker=checker)
                if speech_:
                    analyze.refresh_speech_checks(a, es)
                self.write_analysis(a)
                n += 1
        return n

    def settings_save(self, body: dict) -> dict:
        cur = self.settings
        upd = {}
        def pick(k, ok):
            if k in body:
                if not ok(body[k]):
                    raise ApiError(f"Valor inválido: {k}.")
                upd[k] = body[k]
        pick("time_format", lambda v: v in ("seconds", "ndf", "df"))
        pick("srt_block_s", lambda v: v in (2, 3, 5))
        pick("srt_prefix", lambda v: isinstance(v, str) and len(v) <= 30)
        pick("srt_where", lambda v: v in ("beside", "subfolder"))
        pick("sensitivity", lambda v: isinstance(v, int) and 0 <= v <= 100)
        pick("group_gap_s", lambda v: v in (0, 4, 8, 12))
        pick("cache_auto_days", lambda v: v in (0, 7, 15, 30, 60))
        for k in ("transcribe", "spell", "spell_en", "spell_la"):
            pick(k, lambda v: isinstance(v, bool))
        for k in ("error_phrases", "generic_names"):
            if k in body:
                v = body[k]
                if not isinstance(v, list) or len(v) > 200:
                    raise ApiError(f"Lista inválida: {k}.")
                clean, seen = [], set()
                for x in v:
                    x = " ".join(str(x).split())[:80]
                    if x and x.lower() not in seen:
                        seen.add(x.lower())
                        clean.append(x)
                upd[k] = clean
        if "srt_prefix" in upd:
            upd["srt_prefix"] = upd["srt_prefix"].strip()
        if "group_gap_s" in upd:
            upd["group_gap_s"] = float(upd["group_gap_s"])
        appdata.save_settings(upd)
        text = any(k in upd and upd[k] != cur.get(k) for k in ("spell_en", "spell_la", "generic_names"))
        sp = "error_phrases" in upd and upd["error_phrases"] != cur.get("error_phrases")
        refreshed = self._refresh_open(text=text, speech_=sp) if (text or sp) else 0
        if "cache_auto_days" in upd:
            threading.Thread(target=self.clean_old_cache, daemon=True).start()
        return {"ok": True, "refreshed": refreshed}

    def settings_editors(self, body: dict) -> dict:
        op = body.get("op")
        s = self.settings
        eds = [dict(e) for e in s.get("editors", [])]
        name = " ".join(str(body.get("name") or "").split())
        names_low = {e["name"].lower(): e for e in eds}
        if op == "add":
            if not name or len(name) > 40:
                raise ApiError("Escreva o nome do editor (até 40 letras).")
            if name.lower() in names_low:
                e = names_low[name.lower()]
                if e.get("active", True):
                    raise ApiError("Esse editor já está na equipe.")
                e["active"] = True
            else:
                eds.append({"name": name, "active": True})
        elif op == "toggle":
            e = names_low.get(name.lower())
            if e is None:
                raise ApiError("Editor não encontrado.", 404)
            e["active"] = not e.get("active", True)
        elif op == "rename":
            new = " ".join(str(body.get("new") or "").split())
            e = names_low.get(name.lower())
            if e is None:
                raise ApiError("Editor não encontrado.", 404)
            if not new or len(new) > 40:
                raise ApiError("Escreva o novo nome (até 40 letras).")
            if new.lower() in names_low and new.lower() != name.lower():
                raise ApiError("Já existe um editor com esse nome.")
            old = e["name"]
            e["name"] = new
            # as revisões salvas passam a usar o nome novo (as horas continuam juntas no relatório)
            n = 0
            for p in Path(self.reviews_root()).glob("*/revisao.json"):
                try:
                    r = json.loads(p.read_text(encoding="utf-8"))
                except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                    continue
                hit = False
                for v in r.get("videos", []):
                    if v.get("editor") == old:
                        v["editor"] = new
                        hit = True
                if hit and not (self.review and r.get("key") == self.review.get("key")):
                    review.save(self.reviews_root(), r)
                    n += 1
            if self.review:
                for v in self.review["videos"]:
                    if v.get("editor") == old:
                        v["editor"] = new
                self.save_review()
        else:
            raise ApiError("Operação inválida.")
        appdata.save_settings({"editors": eds})
        return {"ok": True, "editors": eds}

    def settings_words(self, body: dict) -> dict:
        op = body.get("op")
        word = spell.nfc(" ".join(str(body.get("word") or "").split()))
        if not word or len(word) > 80:
            raise ApiError("Escreva a palavra ou expressão (até 80 letras).")
        f = appdata.custom_words_file()
        if op == "add":
            spell.add_to_custom(f, word)
        elif op == "remove":
            spell.remove_from_custom(f, word)
        else:
            raise ApiError("Operação inválida.")
        refreshed = self._refresh_open(text=True)
        return {"ok": True, "words": spell.load_custom(f), "refreshed": refreshed}

    def settings_folder(self, body: dict) -> dict:
        kind = body.get("kind")
        if kind not in ("cache_dir", "reviews_dir", "report_dir"):
            raise ApiError("Pasta inválida.")
        raw = body.get("path")
        path = None
        if raw:
            p = Path(str(raw)).expanduser()
            if not p.is_dir():
                raise ApiError("Essa pasta não existe.")
            path = str(p.resolve())
        if kind == "cache_dir" and self._job_running():
            raise ApiError("Espere a análise terminar para trocar a pasta do cache.")
        copied = 0
        if kind == "reviews_dir":
            old = self.reviews_root()
            new = Path(path) if path else appdata.home() / "revisoes"
            new.mkdir(parents=True, exist_ok=True)
            if new.resolve() != old.resolve():
                # leva as revisões já salvas (cópia; a pasta antiga fica como estava)
                for d in old.iterdir():
                    if d.is_dir() and (d / "revisao.json").is_file() and not (new / d.name).exists():
                        shutil.copytree(d, new / d.name)
                        copied += 1
        appdata.save_settings({kind: path})
        return {"ok": True, "copied": copied}


APP = App()


# ====================================================================== HTTP

class Handler(BaseHTTPRequestHandler):
    server_version = f"Revisor/{__version__}"

    def log_message(self, fmt, *args):   # silencioso (o terminal fica limpo)
        pass

    # ------------------------------------------------------------ respostas
    def _send(self, status: int, body: bytes, ctype: str, extra: dict | None = None, cache: bool = False):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        # frames e gráficos de um frame nunca mudam (o id do vídeo leva nome + duração)
        self.send_header("Cache-Control", "private, max-age=86400" if cache else "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _send_file(self, path: Path, ctype: str):
        """Arquivo grande (vídeo) em pedaços, com "Range" (o player do navegador pula no tempo assim)."""
        size = path.stat().st_size
        start, end, status = 0, size - 1, 200
        rng = self.headers.get("Range")
        if rng:
            m = re.fullmatch(r"\s*bytes=(\d*)-(\d*)\s*", rng)
            if m and (m.group(1) or m.group(2)):
                if m.group(1):
                    start = int(m.group(1))
                    if m.group(2):
                        end = min(int(m.group(2)), size - 1)
                else:                                  # "bytes=-500": os últimos 500
                    start = max(size - int(m.group(2)), 0)
                status = 206
            if start > end or start >= size:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        if self.command == "HEAD":
            return
        with open(path, "rb") as fh:
            fh.seek(start)
            left = end - start + 1
            while left > 0:
                chunk = fh.read(min(512 * 1024, left))
                if not chunk:
                    break
                self.wfile.write(chunk)
                left -= len(chunk)

    def _download(self, data: bytes, filename: str, ctype: str):
        """Arquivo para o navegador salvar (vai para a pasta Downloads)."""
        ascii_name = re.sub(r"[^A-Za-z0-9._ -]+", "_", filename) or "arquivo"
        self._send(200, data, ctype, {"Content-Disposition":
                                      f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"})

    def _json(self, data, status: int = 200):
        self._send(status, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _host_ok(self) -> bool:
        host = (self.headers.get("Host") or "").split(":")[0]
        return host in ("127.0.0.1", "localhost")

    def _body(self) -> dict:
        if "application/json" not in (self.headers.get("Content-Type") or ""):
            raise ApiError("Content-Type deve ser application/json", 415)
        n = int(self.headers.get("Content-Length") or 0)
        if n > 2_000_000:
            raise ApiError("Pedido grande demais", 413)
        raw = self.rfile.read(n) if n else b"{}"
        try:
            return json.loads(raw.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ApiError("JSON inválido")

    # ------------------------------------------------------------ rotas
    def do_GET(self):
        self._dispatch("GET")

    def do_HEAD(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def _dispatch(self, method: str):
        if not self._host_ok():
            return self._send(403, b"forbidden", "text/plain")
        u = urlparse(self.path)
        q = {k: v[-1] for k, v in parse_qs(u.query).items()}
        path = unquote(u.path)
        try:
            if method == "GET":
                if path == "/" or path == "/index.html":
                    return self._static("index.html")
                if path.startswith("/ui/"):
                    return self._static(path[4:])
                if path.startswith("/api/"):
                    return self._api_get(path[5:], q)
            elif method == "POST" and path.startswith("/api/"):
                return self._api_post(path[5:], self._body())
            self._send(404, b"not found", "text/plain")
        except ApiError as e:
            self._json({"error": str(e)}, e.status)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            traceback.print_exc()
            self._json({"error": f"Erro interno: {type(e).__name__}: {e}"}, 500)

    def _static(self, rel: str):
        p = (UI_DIR / rel).resolve()
        if UI_DIR not in p.parents or not p.is_file():
            return self._send(404, b"not found", "text/plain")
        ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
        if p.suffix == ".woff2":
            ctype = "font/woff2"
        if ctype.startswith("text/") or ctype in ("application/javascript",):
            ctype += "; charset=utf-8"
        self._send(200, p.read_bytes(), ctype)

    def _api_get(self, ep: str, q: dict):
        if ep == "hello":       # outra cópia do app pergunta se esta está viva
            return self._json({"app": "revisor", "version": __version__})
        if ep == "log.txt":     # fim do revisor.log (app empacotado), para diagnóstico
            p = appdata.home() / "revisor.log"
            data = p.read_bytes()[-200_000:] if p.is_file() else b"(sem revisor.log)"
            return self._send(200, data, "text/plain; charset=utf-8")
        if ep == "state":
            s = APP.settings
            return self._json({
                "version": __version__,
                "settings": {k: s[k] for k in ("vinheta_in", "vinheta_out", "sensitivity", "group_gap_s", "spell",
                                               "transcribe", "history", "last_folder", "time_format")},
                "editors": appdata.active_editors(s),
                "vinhetas_ok": {"in": bool(s.get("vinheta_in") and Path(s["vinheta_in"]).is_file()),
                                "out": bool(s.get("vinheta_out") and Path(s["vinheta_out"]).is_file())},
                "review_open": APP.review is not None,
                "project": APP.review["project"] if APP.review else None,
                "job": APP.job.snapshot() if APP.job else None,
                "queue": {"total": len(APP.queue), "running": (APP._running_entry() or {}).get("project"),
                          "waiting": sum(1 for e in APP.queue if e["job"].state == "idle"),
                          "restore": len(APP.restore_list())},
                "today": date.today().isoformat(),
            })
        if ep == "folder":
            return self._json(APP.folder_info(q.get("path", "")))
        if ep == "job":
            return self._json(APP.job.snapshot() if APP.job else {"state": "none"})
        if ep == "queue":
            return self._json(APP.queue_view())
        if ep == "review":
            return self._json(APP.review_view())
        if ep == "reviews":
            return self._json({"reviews": review.list_saved(APP.reviews_root())})
        if ep == "ls":
            if not q.get("path"):
                return self._json({"roots": dialogs.roots()})
            try:
                return self._json(dialogs.listdir(q["path"]) | {"roots": dialogs.roots()})
            except FileNotFoundError:
                raise ApiError("Pasta não encontrada.", 404)
        if ep == "scope.png":
            ids = [x for x in q.get("ids", "").split(",") if x and x.isalnum()]
            return self._send(200, APP.scope_png(ids), "image/png")
        # ---- tela de revisão (etapa 4)
        if ep == "video":
            return self._json(APP.video_view(int(q.get("n", "1") or 1)))
        if ep == "frame.jpg":
            data, exact = APP.frame_jpeg(q)
            return self._send(200, data, "image/jpeg", cache=exact)
        if ep == "fscope.png":
            return self._send(200, APP.frame_scope(q), "image/png", cache=True)
        if ep == "media":
            p, ctype = APP.media_file(q)
            return self._send_file(p, ctype)
        if ep == "clip":
            p = APP.clip_file(q)
            return self._send_file(p, "video/webm" if p.suffix == ".webm" else "video/mp4")
        # ---- etapa 5
        if ep == "cframe.jpg":
            vid = q.get("id", "")
            if not vid.isalnum():
                raise ApiError("Vídeo inválido.")
            try:
                f = int(q.get("f", "0"))
            except ValueError:
                raise ApiError("Frame inválido.")
            got = APP.comment_frame(vid, f, "full" if q.get("s") == "full" else "thumb")
            if got is None:
                raise ApiError("Imagem indisponível: o vídeo não está neste computador.", 404)
            return self._send(200, got[0], "image/jpeg", cache=got[1])
        if ep == "final":
            return self._json(APP.final_view())
        if ep == "final/srt.zip":
            rev = APP._need_review()
            return self._download(APP.final_srt_zip(), f"SRT {review.slug(rev['project'])}.zip", "application/zip")
        if ep == "final/horas.txt":
            rev = APP._need_review()
            return self._download(export.hours_txt(rev).encode("utf-8"), f"Horas {review.slug(rev['project'])}.txt",
                                  "text/plain; charset=utf-8")
        if ep == "package":
            return self._json(APP.package_info())
        if ep == "month":
            return self._json(APP.month_view(q.get("m")))
        if ep in ("month.txt", "month.csv"):
            rep, read, _dup = APP.month(q.get("m"))
            name = f"Relatorio do mes {rep['month']}"
            if ep == "month.txt":
                return self._download(export.month_txt(rep, read).encode("utf-8"), name + ".txt",
                                      "text/plain; charset=utf-8")
            return self._download(export.month_csv(rep), name + ".csv", "text/csv; charset=utf-8")
        if ep == "settings/all":
            return self._json(APP.settings_view())
        if ep == "cache":
            return self._json(APP.cache_list())
        raise ApiError("rota desconhecida", 404)

    def _api_post(self, ep: str, body: dict):
        if ep == "ping":
            LIFE.ping(str(body.get("client") or ""))
            return self._json({"ok": True, "packaged": LIFE.auto_exit})
        if ep == "bye":
            LIFE.bye(str(body.get("client") or ""))
            return self._json({"ok": True})
        if ep == "quit":
            threading.Timer(0.3, LIFE.exit).start()
            return self._json({"ok": True})
        if ep == "start":
            return self._json(APP.start(body))
        if ep == "dialog":
            kind = body.get("kind", "folder")
            start = body.get("start") or None
            try:
                if kind == "folder":
                    p = dialogs.choose_folder(body.get("prompt") or "Escolha a pasta dos vídeos", start)
                else:
                    p = dialogs.choose_file(body.get("prompt") or "Escolha o arquivo", start)
            except dialogs.Unsupported:
                return self._json({"unsupported": True})
            return self._json({"path": p, "cancelled": p is None})
        if ep == "settings":
            allowed = {"vinheta_in", "vinheta_out", "sensitivity", "group_gap_s", "spell", "transcribe", "nav_slides",
                       "clip_half_s"}
            upd = {k: v for k, v in body.items() if k in allowed}
            if "clip_half_s" in upd:
                upd["clip_half_s"] = frames.clip_half(upd["clip_half_s"])
            for k in ("vinheta_in", "vinheta_out"):
                if upd.get(k):
                    if not Path(upd[k]).expanduser().is_file():
                        raise ApiError("Arquivo não encontrado: " + upd[k])
                    upd[k] = str(Path(upd[k]).expanduser().resolve())
            appdata.save_settings(upd)
            return self._json({"ok": True})
        # pausar/continuar valem para a análise que está rodando (a fila espera junto)
        if ep == "job/pause":
            r = APP._running_entry()
            if r:
                r["job"].pause()
            return self._json({"ok": True})
        if ep == "job/resume":
            r = APP._running_entry()
            if r:
                r["job"].resume()
            return self._json({"ok": True})
        if ep == "job/cancel":
            if APP.job:
                APP.job.cancel()
            return self._json({"ok": True})
        if ep == "queue/now":
            return self._json(APP.queue_now(str(body.get("project") or "")))
        if ep == "queue/remove":
            return self._json(APP.queue_remove(str(body.get("project") or "")))
        if ep == "queue/restore":
            return self._json(APP.queue_restore(bool(body.get("keep"))))
        if ep == "review/editor":
            return self._json(APP.set_editor(body))
        if ep == "review/sensitivity":
            return self._json(APP.set_sensitivity(body))
        if ep == "reviews/open":
            return self._json(APP.open_saved(body.get("project") or ""))
        # ---- tela de revisão (etapa 4)
        if ep == "comment":
            return self._json(APP.set_comment(body))
        if ep == "dismiss":
            return self._json(APP.dismiss(body))
        if ep == "accept":
            return self._json(APP.accept_word(body))
        if ep == "review/adjust":
            return self._json(APP.adjust(body))
        if ep == "pick":
            return self._json(APP.pick(body))
        # ---- etapa 5
        if ep == "final/mark":
            return self._json(APP.final_mark(body))
        if ep == "final/srt":
            return self._json(APP.final_srt())
        if ep == "package/export":
            return self._json(APP.package_export(body))
        if ep == "package/inspect":
            return self._json(APP.package_inspect(body))
        if ep == "package/open":
            return self._json(APP.package_open(body))
        if ep == "settings/save":
            return self._json(APP.settings_save(body))
        if ep == "settings/editors":
            return self._json(APP.settings_editors(body))
        if ep == "settings/words":
            return self._json(APP.settings_words(body))
        if ep == "settings/folder":
            return self._json(APP.settings_folder(body))
        if ep == "cache/clear":
            return self._json(APP.cache_clear(body))
        raise ApiError("rota desconhecida", 404)


def _free_port(preferred: int) -> int:
    for port in [preferred] + list(range(preferred + 1, preferred + 20)):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if hasattr(socket, "SO_REUSEADDR") and not hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)   # porta em TIME_WAIT serve
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


LIFE = life.Life(auto_exit=False)


def _busy() -> bool:
    return any(e["job"].state == "running" for e in APP.queue)


def serve(port: int | None = None, open_browser: bool = True, auto_exit: bool = False):
    """Abre o servidor. auto_exit: fecha sozinho sem página aberta (app empacotado)."""
    global LIFE
    home = appdata.home()
    url = life.running_url(home)
    if url:                                   # já está aberto: só mostra a página
        print(f"O Revisor de Vídeos já está aberto em {url}")
        if open_browser:
            webbrowser.open(url)
        return
    port = _free_port(port or DEFAULT_PORT)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    httpd.daemon_threads = True
    url = f"http://127.0.0.1:{port}/"

    def stop():
        APP.stop_all()
        threading.Thread(target=httpd.shutdown, daemon=True).start()

    LIFE = life.Life(auto_exit=auto_exit, busy=_busy, on_exit=stop)
    LIFE.watch()
    life.write_instance(home, port)
    print(f"Revisor de Vídeos aberto em {url}")
    print("Para fechar o app: botão Sair na página, feche esta janela ou aperte Ctrl+C.")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    threading.Thread(target=APP.clean_old_cache, daemon=True).start()   # limpeza automática do cache
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        APP.stop_all()
        httpd.server_close()
        life.clear_instance(home, port)
