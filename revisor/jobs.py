"""Análise em segundo plano: um vídeo por vez, com progresso, pausa e cancelamento.

A tela de análise pergunta o estado (snapshot) algumas vezes por segundo.
Vídeo que já está no cache fica pronto na hora.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

from . import analyze, media, report, summary, vinheta

# estimativa antes de medir (máquina virtual do Mac: ~3 s/min imagem + ~1 s/min texto + ~9 s/min fala)
GUESS_S_PER_MIN = {"base": 4.0, "speech": 9.0}


class Cancelled(Exception):
    pass


def scan_folder(folder: str | Path) -> dict:
    """O que a tela de início mostra ao escolher a pasta (sem analisar)."""
    folder = Path(folder)
    out = {"ok": False, "folder": str(folder), "name": folder.name, "videos": [], "total_s": 0.0,
           "report": None, "warnings": [], "matches": {}, "error": None, "newest_mtime": None}
    if not folder.is_dir():
        out["error"] = "Pasta não encontrada."
        return out
    vids = analyze.list_videos(folder)
    newest = None
    for v in vids:
        item = {"file": v.name, "path": str(v), "duration": None, "id": None, "error": None, "detail": None}
        try:
            info = media.probe(v)
            item["duration"] = info.duration
            item["id"] = analyze.video_id(v.name, info.duration)
            out["total_s"] += info.duration
        except media.MediaError as e:
            item["error"] = "não foi possível ler o vídeo (arquivo incompleto, corrompido ou ainda copiando)"
            item["detail"] = str(e)[-300:]
        try:
            mt = v.stat().st_mtime
            newest = mt if newest is None or mt > newest else newest
        except OSError:
            pass
        out["videos"].append(item)
    out["newest_mtime"] = newest
    rp = report.find_in_folder(folder)
    if rp:
        try:
            rep = report.parse(rp)
            out["report"] = rep.to_dict()
            if len(rep.edited) != len(vids):
                out["warnings"].append(
                    f"A pasta tem {len(vids)} vídeos, mas o relatório de tempo lista {len(rep.edited)} editados.")
            matches, mw = report.match_videos(rep, [(v["file"], v["duration"] or 0.0) for v in out["videos"]])
            out["warnings"] += mw
            out["matches"] = {m.video: ({"seconds": m.entry[0], "file": m.entry[1], "by": m.by}
                                        if m.entry else None) for m in matches}
        except (OSError, ValueError) as e:
            out["warnings"].append(f"Não foi possível ler o relatório de tempo ({e}).")
    out["ok"] = bool(vids)
    if not vids:
        out["error"] = "Nenhum vídeo (MP4, MOV) nesta pasta."
    return out


class AnalysisJob:
    def __init__(self, scan: dict, settings: analyze.Settings, cache_root: Path, on_video=None, on_done=None):
        self.scan = scan
        self.settings = settings
        self.cache_root = Path(cache_root)
        self.on_video = on_video                 # callback(video_dict, analysis) quando um vídeo fica pronto
        self.on_done = on_done                   # callback(job) quando a análise acaba (fila de pastas)
        self.videos = []
        for k, v in enumerate(scan["videos"]):
            self.videos.append({"n": k + 1, "id": v["id"], "file": v["file"], "path": v["path"],
                                "duration": v["duration"] or 0.0,
                                "status": "erro" if v.get("error") else "wait",
                                "error": v.get("error"), "detail": v.get("detail"), "pct": 0.0, "row": None,
                                "started": None, "finished": None, "from_cache": False})
        self.analyses: dict[str, dict] = {}
        self.state = "idle"
        self.error = None
        self.started = None
        self.finished = None
        self._resume = threading.Event()
        self._resume.set()
        self._cancel = False
        self._thread = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------ controle
    def start(self):
        self.state = "running"
        self.started = time.time()
        self._thread = threading.Thread(target=self._run, name="analise", daemon=True)
        self._thread.start()

    def pause(self):
        if self.state == "running":
            self.state = "paused"
            self._resume.clear()

    def resume(self):
        if self.state == "paused":
            self.state = "running"
            self._resume.set()

    def cancel(self):
        self._cancel = True
        self._resume.set()

    def _checkpoint(self):
        while not self._resume.is_set():
            self._resume.wait(0.5)
        if self._cancel:
            raise Cancelled()

    # ------------------------------------------------------------ trabalho
    def _run(self):
        try:
            st = self.settings
            sig_in = vinheta.signature(st.vinheta_in) if st.vinheta_in and Path(st.vinheta_in).exists() else None
            sig_out = vinheta.signature(st.vinheta_out) if st.vinheta_out and Path(st.vinheta_out).exists() else None
            for v in self.videos:
                if v["status"] == "erro":
                    continue
                self._checkpoint()
                v["status"] = "run"
                v["started"] = time.time()
                cached = (self.cache_root / v["id"] / "analysis.json").exists()

                def prog(x, v=v):
                    v["pct"] = max(v["pct"], min(float(x), 1.0))
                    self._checkpoint()
                try:
                    a = analyze.analyze_video(v["path"], self.cache_root, st, sig_in, sig_out, progress=prog)
                except Cancelled:
                    raise
                except Exception as e:  # um vídeo com problema não para os outros
                    v["status"] = "erro"
                    v["error"] = "a análise deste vídeo falhou"
                    v["detail"] = f"{type(e).__name__}: {str(e)[-300:]}"
                    continue
                a["report_entry"] = self.scan.get("matches", {}).get(v["file"])
                v["finished"] = time.time()
                v["from_cache"] = cached and (v["finished"] - v["started"] < 3)
                v["pct"] = 1.0
                v["row"] = summary.video_row(a, st.sensitivity)
                with self._lock:
                    self.analyses[v["id"]] = a
                v["status"] = "ok"
                if self.on_video:
                    try:
                        self.on_video(v, a)
                    except Exception:
                        pass
            self.state = "done"
        except Cancelled:
            self.state = "cancelled"
            for v in self.videos:
                if v["status"] == "run":
                    v["status"] = "wait"
                    v["pct"] = 0.0
        except Exception as e:
            self.state = "error"
            self.error = f"{type(e).__name__}: {e}"
        finally:
            self.finished = time.time()
            if self.on_done:
                try:
                    self.on_done(self)
                except Exception:
                    pass

    def alive(self) -> bool:
        """Começou e ainda não acabou (rodando ou pausada; uma cancelada fica viva até parar de fato)."""
        return self.state in ("running", "paused")

    # ------------------------------------------------------------ estado para a tela
    def eta_s(self) -> float | None:
        if self.state in ("done", "cancelled", "error"):
            return 0.0
        measured_t = measured_d = 0.0
        for v in self.videos:
            if v["status"] == "ok" and not v["from_cache"] and v["finished"] and v["started"]:
                measured_t += v["finished"] - v["started"]
                measured_d += v["duration"]
            elif v["status"] == "run" and v["started"] and v["pct"] > 0.05:
                measured_t += time.time() - v["started"]
                measured_d += v["duration"] * v["pct"]
        if measured_d >= 20:
            rate = measured_t / measured_d
        else:
            per_min = GUESS_S_PER_MIN["base"] + (GUESS_S_PER_MIN["speech"] if self.settings.transcribe else 0)
            rate = per_min / 60.0
        left = 0.0
        for v in self.videos:
            if v["status"] == "wait":
                left += v["duration"]
            elif v["status"] == "run":
                left += v["duration"] * (1 - v["pct"])
        return left * rate

    def snapshot(self) -> dict:
        total_d = sum(v["duration"] for v in self.videos if v["status"] != "erro") or 1.0
        done_d = sum(v["duration"] * (1.0 if v["status"] == "ok" else v["pct"] if v["status"] == "run" else 0.0)
                     for v in self.videos if v["status"] != "erro")
        return {
            "state": self.state, "error": self.error,
            "done": sum(1 for v in self.videos if v["status"] == "ok"),
            "total": sum(1 for v in self.videos if v["status"] != "erro" or v.get("row")),
            "failed": sum(1 for v in self.videos if v["status"] == "erro"),
            "pct": round(done_d / total_d, 4),
            "eta_s": self.eta_s(),
            "videos": [{k: v[k] for k in ("n", "id", "file", "duration", "status", "error", "detail", "pct", "row")}
                       | {"cached": v["status"] == "wait" and (self.cache_root / v["id"] / "analysis.json").exists()}
                       for v in self.videos],
        }

    def analysis(self, vid: str) -> dict | None:
        with self._lock:
            return self.analyses.get(vid)
