"""Orquestra a análise de uma pasta de aulas e grava o cache.

Cache (pode ser apagado a qualquer momento; o app refaz):
  <cache>/<id do vídeo>/analysis.json
  <cache>/<id do vídeo>/scope.npy        vectorscope médio (128×128)
  <cache>/<id do vídeo>/thumbs/*.jpg     miniaturas dos frames marcados

O id do vídeo é nome do arquivo + duração: o mesmo vídeo em outro
computador (ou outra pasta) tem o mesmo id.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import __version__, audio, media, nametag, ocr, report, speech, spell, transitions, video, vinheta
from .timecode import fmt_seconds

VIDEO_EXT = {".mp4", ".mov", ".m4v"}
ANALYSIS_VERSION = 10  # 9: frame do texto = quando o lettering para; 10: começo da imagem congelada procurado 1,5 s antes
# Fala (etapa 2b) e áudio têm versão própria: mudar a fala não refaz a imagem e o OCR.
SPEECH_VERSION = 2


@dataclass
class Settings:
    sensitivity: int = 55
    group_gap_s: float = 8.0
    vinheta_in: str | None = None
    vinheta_out: str | None = None
    thumb_width: int = 640
    slide_frames: int = transitions.EXPECTED_FRAMES   # duração esperada da entrada/saída do slide
    slide_tolerance: int = transitions.TOLERANCE
    # etapa 2: texto na tela
    read_text: bool = True                     # OCR + ortografia + tarja
    spell_langs: tuple = spell.DICTS           # pt_BR, en_US, la
    custom_words_file: str | None = None       # lista própria (cresce com "Aceitar")
    name_expected: str | None = None           # "Nome na tarja" da tela de início
    name_window_s: float = nametag.WINDOW_S
    generic_names: list = field(default_factory=lambda: list(nametag.GENERIC_DEFAULT))
    # etapa 2b: fala
    transcribe: bool = True                    # "Transcrever falas" (Whisper local)
    error_phrases: list = field(default_factory=lambda: list(speech.ERROR_PHRASES_DEFAULT))


def video_id(name: str, duration: float) -> str:
    key = f"{name}|{round(duration, 1)}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def list_videos(folder: str | Path) -> list[Path]:
    folder = Path(folder)
    vids = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXT
            and not p.name.startswith(".")]
    return sorted(vids, key=lambda p: p.name.lower())


class _Progress:
    def __init__(self, cb, lo: float, hi: float):
        self.cb, self.lo, self.hi = cb, lo, hi

    def __call__(self, x: float):
        if self.cb:
            self.cb(self.lo + (self.hi - self.lo) * x)


def analyze_video(path: str | Path, cache_root: str | Path, settings: Settings,
                  sig_in: vinheta.Signature | None = None, sig_out: vinheta.Signature | None = None,
                  progress=None, force: bool = False) -> dict:
    path = Path(path)
    t_start = time.time()
    info = media.probe(path)
    vid = video_id(path.name, info.duration)
    out_dir = Path(cache_root) / vid
    out_json = out_dir / "analysis.json"
    if out_json.exists() and not force:
        try:
            cached = json.loads(out_json.read_text(encoding="utf-8"))
            if cached.get("analysis_version") == ANALYSIS_VERSION:
                if cached.get("speech_version") != SPEECH_VERSION or \
                        (settings.transcribe and (cached.get("speech") or {}).get("status") != "ok"):
                    update_audio_speech(cached, path, out_dir, settings, progress)
                refresh_text_checks(cached, settings)
                refresh_speech_checks(cached, settings)
                ensure_text_thumbs(cached, out_dir, settings.thumb_width)
                _write_json(out_json, cached)
                if progress:
                    progress(1.0)
                return cached
        except (OSError, json.JSONDecodeError):
            pass
    (out_dir / "thumbs").mkdir(parents=True, exist_ok=True)
    rate = info.rate
    timings = {}

    # 1) passada leve (imagem)
    t = time.time()
    coarse = video.coarse_pass(str(path), rate, info.frames, progress=_Progress(progress, 0.0, 0.70))
    timings["coarse_s"] = round(time.time() - t, 2)
    # (total de frames vem do probe; a passada leve pode ter 1 amostra a mais)

    # 2) vinhetas
    t = time.time()
    vin = vinheta.find(str(path), rate, info.frames, sig_in, sig_out)
    timings["vinheta_s"] = round(time.time() - t, 2)
    c_first = vin.content_first_frame if vin.content_first_frame is not None else 0
    c_end = vin.end_first_frame if vin.end_first_frame is not None else info.frames
    s_lo = int(np.ceil(rate.seconds_of(c_first) * video.SAMPLE_FPS)) + 1
    s_hi = int(rate.seconds_of(c_end) * video.SAMPLE_FPS) - 1

    # 3) candidatos + frame exato
    t = time.time()
    events = video.detect(coarse, (s_lo, s_hi))
    for k, ev in enumerate(events):
        video.refine(str(path), rate, ev)
        if progress:
            progress(0.70 + 0.15 * (k + 1) / max(len(events), 1))
    video.group_lists(events, rate, settings.group_gap_s)
    video.pair_text(events, rate)
    timings["refine_s"] = round(time.time() - t, 2)

    # 3b) transições câmera ↔ slide (regra do núcleo)
    t = time.time()
    cut_list = []
    for ev in events:
        if ev.kind != "cut" or ev.frame is None:
            continue
        try:
            tinfo = transitions.analyze_cut(str(path), rate, ev.frame)
        except media.MediaError:
            tinfo = None
        if tinfo is None:
            continue
        ev.extra["transition"] = tinfo.to_dict()
        cut_list.append({"frame": ev.frame, "info": tinfo,
                         "ring_before": transitions.ring_signature(str(path), rate, max(ev.frame - 15, 0)),
                         "ring_after": transitions.ring_signature(str(path), rate, ev.frame + 15)})
    for w in transitions.lesson_rule(cut_list, settings.slide_frames, settings.slide_tolerance):
        s = int(rate.seconds_of(w["frame"]) * video.SAMPLE_FPS)
        events.append(video.Event("slide_transition", s, 10000.0, frame=w["frame"],
                                  show_frame=w["frame"], note=w["note"]))
    events.sort(key=lambda e: (e.frame if e.frame is not None else 0))
    timings["transitions_s"] = round(time.time() - t, 2)

    # 3c) texto na tela: OCR nos frames já marcados (ortografia e tarja usam depois)
    t = time.time()
    reads = []
    text_status = "desligado"
    if settings.read_text:
        if ocr.available():
            checker = make_checker(settings)

            def verify(rd, gray):
                # palavra suspeita: relê ampliada antes de avisar (o OCR erra acento)
                for ln in rd.lines:
                    for w in ln.words:
                        if spell.word_problems(w.to_dict(), checker):
                            try:
                                w.reread = ocr.reread_word(gray, w.box, info.width, info.height)
                            except ocr.OCRError:
                                w.reread = None
            reads = ocr.read_video(str(path), rate, events, (c_first, c_end), info.width, info.height,
                                   progress=_Progress(progress, 0.85, 0.93), on_frame=verify,
                                   tag_window_s=settings.name_window_s)
            text_status = "ok"
        else:
            text_status = "sem_tesseract"
    timings["ocr_s"] = round(time.time() - t, 2)

    # 4) áudio (sem as vinhetas nos números)
    t = time.time()
    vcuts = [rate.seconds_of(ev.frame) for ev in events if ev.kind == "cut" and ev.frame is not None]
    aud = audio.analyze(str(path), content=(rate.seconds_of(c_first), rate.seconds_of(c_end)), video_cuts=vcuts) \
        if info.has_audio else None
    timings["audio_s"] = round(time.time() - t, 2)
    if progress:
        progress(0.95)

    # 5) miniaturas
    t = time.time()
    thumbs = {}
    wanted = set()
    for ev in events:
        if ev.show_frame is not None:
            wanted.add(ev.show_frame)
    wanted.update(rd.frame for rd in reads if rd.lines and rd.source != "tag_scan")
    wanted.update(vin.frames_in)
    wanted.update(vin.frames_out)
    for f in sorted(wanted):
        name = f"f{f:07d}.jpg"
        dst = out_dir / "thumbs" / name
        if not dst.exists():
            try:
                media.save_jpeg(str(path), rate, f, dst, settings.thumb_width)
            except Exception:  # miniatura é conveniência; não derruba a análise
                continue
        thumbs[f] = f"thumbs/{name}"
    timings["thumbs_s"] = round(time.time() - t, 2)

    np.save(out_dir / "scope.npy", coarse.scope.astype(np.int64))
    sc = coarse.scope.astype(np.float64)
    tot = sc.sum()
    if tot > 0:
        ii, jj = np.meshgrid(np.arange(128), np.arange(128), indexing="ij")
        mean_cb = float((sc * (ii * 2 + 1)).sum() / tot)
        mean_cr = float((sc * (jj * 2 + 1)).sum() / tot)
    else:
        mean_cb = mean_cr = 128.0

    ev_dicts = []
    for k, ev in enumerate(events):
        d = ev.to_dict()
        d["id"] = k
        d["time"] = round(rate.seconds_of(ev.frame), 3) if ev.frame is not None else None
        d["tc"] = fmt_seconds(rate, ev.frame) if ev.frame is not None else None
        d["thumb"] = thumbs.get(ev.show_frame)
        ev_dicts.append(d)

    result = {
        "analysis_version": ANALYSIS_VERSION,
        "app_version": __version__,
        "id": vid,
        "file": path.name,
        "path": str(path),
        "duration": info.duration,
        "fps": f"{rate.fps.numerator}/{rate.fps.denominator}",
        "frames": info.frames,
        "width": info.width, "height": info.height,
        "color": {"matrix": info.color_matrix, "range": info.color_range, "pix_fmt": info.pix_fmt},
        "content": {"first_frame": c_first, "end_frame": c_end},
        "vinheta": {**vin.to_dict(),
                    "thumbs_in": [thumbs.get(f) for f in vin.frames_in],
                    "thumbs_out": [thumbs.get(f) for f in vin.frames_out]},
        "events": ev_dicts,
        "text": {"status": text_status, "reads": [rd.to_dict() for rd in reads]},
        "audio": aud.to_dict() if aud else None,
        "scope": {"file": "scope.npy", "mean_cb": round(mean_cb, 2), "mean_cr": round(mean_cr, 2)},
        "settings_used": {"group_gap_s": settings.group_gap_s},
        "timings": {**timings, "total_s": round(time.time() - t_start, 2)},
        "analyzed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    result["thumbs"] = {str(f): v for f, v in thumbs.items()}
    result["speech_version"] = SPEECH_VERSION

    # 6) fala (Whisper local), em pedaços guardados no cache
    t = time.time()
    result["speech"] = run_speech(path, result, out_dir, settings, _Progress(progress, 0.95, 0.99))
    result["timings"]["speech_s"] = round(time.time() - t, 2)

    t = time.time()
    refresh_speech_checks(result, settings)
    refresh_text_checks(result, settings, out_dir=None)
    ensure_text_thumbs(result, out_dir, settings.thumb_width)
    result["timings"]["spell_s"] = round(time.time() - t, 2)
    _write_json(out_json, result)
    if progress:
        progress(1.0)
    return result


def run_speech(path: Path, analysis: dict, out_dir: Path, settings: Settings, progress=None,
               budget_s: float | None = None) -> dict:
    if not settings.transcribe:
        return {"status": "desligado"}
    if not analysis.get("audio"):
        return {"status": "sem_audio"}
    if not speech.available():
        return {"status": "sem_whisper"}
    fps = _rate_of(analysis)
    content = (fps.seconds_of(analysis["content"]["first_frame"]), fps.seconds_of(analysis["content"]["end_frame"]))
    au = analysis["audio"]
    try:
        return speech.transcribe(str(path), content, out_dir, au.get("envelope_db"), au.get("envelope_step", 0.1),
                                 progress=progress, budget_s=budget_s)
    except (speech.SpeechError, media.MediaError, OSError) as e:
        return {"status": "erro", "error": str(e)[-300:]}


def update_audio_speech(analysis: dict, path: Path, out_dir: Path, settings: Settings, progress=None,
                        budget_s: float | None = None) -> None:
    """Refaz só o áudio e a fala de uma análise do cache (sem reler a imagem)."""
    fps = _rate_of(analysis)
    t = time.time()
    if analysis.get("speech_version") != SPEECH_VERSION:
        try:
            info = media.probe(path)
            if info.has_audio:
                c0 = fps.seconds_of(analysis["content"]["first_frame"])
                c1 = fps.seconds_of(analysis["content"]["end_frame"])
                vcuts = [e["time"] for e in analysis["events"] if e["kind"] == "cut" and e.get("time") is not None]
                analysis["audio"] = audio.analyze(str(path), content=(c0, c1), video_cuts=vcuts).to_dict()
        except media.MediaError:
            pass
    analysis.setdefault("timings", {})["audio_s"] = round(time.time() - t, 2)
    t = time.time()
    analysis["speech"] = run_speech(path, analysis, out_dir, settings, progress, budget_s)
    analysis["timings"]["speech_s"] = round(time.time() - t, 2)
    if analysis["speech"].get("status") != "parcial":
        analysis["speech_version"] = SPEECH_VERSION


SPEECH_KINDS = ("speech_phrase", "speech_repeat")


def refresh_speech_checks(analysis: dict, settings: Settings) -> None:
    """(Re)faz os avisos da fala a partir da transcrição guardada (lista de frases pode mudar)."""
    events = [e for e in analysis["events"] if e["kind"] not in SPEECH_KINDS]
    sp = analysis.get("speech") or {}
    found = []
    if sp.get("status") in ("ok", "parcial") and sp.get("words"):
        au = analysis.get("audio") or {}
        act = speech.activity_from_envelope(au.get("envelope_db") or [], au.get("envelope_step", 0.1))
        found = speech.checks(sp, settings.error_phrases, act)
    rate = _rate_of(analysis)
    thumbs = analysis.get("thumbs", {})
    for f in found:
        fr = rate.frame_at(f.get("restart", f["start"])) if f["kind"] == "speech_repeat" else rate.frame_at(f["start"])
        fr = max(0, min(int(fr), analysis["frames"] - 1))
        e = {"kind": f["kind"], "sample": int(rate.seconds_of(fr) * video.SAMPLE_FPS), "score": 10000.0,
             "frame": fr, "show_frame": fr, "value": 0.0, "note": speech.note_for(f), "group": None,
             "region": None, "extra": {k: v for k, v in f.items() if k != "kind"}}
        e["time"] = round(rate.seconds_of(fr), 3)
        e["tc"] = fmt_seconds(rate, fr)
        e["thumb"] = thumbs.get(str(fr))
        events.append(e)
    events.sort(key=lambda e: (e["frame"] if e["frame"] is not None else 0))
    for k, e in enumerate(events):
        e["id"] = k
    analysis["events"] = events
    analysis["speech_checks"] = found


def _write_json(out_json: Path, data: dict) -> None:
    tmp = out_json.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(out_json)


def make_checker(settings: Settings) -> spell.Checker:
    return spell.Checker(settings.spell_langs, spell.load_custom(settings.custom_words_file))


TEXT_KINDS = ("spelling", "name_tag")
THUMB_KINDS = ("spelling", "name_tag", "speech_phrase", "speech_repeat")


def refresh_text_checks(analysis: dict, settings: Settings, checker: spell.Checker | None = None,
                        out_dir: Path | None = None) -> None:
    """(Re)faz ortografia e tarja a partir das leituras guardadas, sem ler o vídeo.

    Usado depois da análise, ao abrir do cache e quando a lista própria ou o
    nome da tarja mudam. Os avisos entram em analysis["events"] (tipos
    "spelling" e "name_tag") e o resultado da tarja em analysis["name_tag"].
    """
    text = analysis.get("text") or {}
    events = [e for e in analysis["events"] if e["kind"] not in TEXT_KINDS]
    if text.get("status") != "ok":
        analysis["events"] = events
        analysis["name_tag"] = None
        analysis["spelling"] = []
        return
    reads = text.get("reads", [])
    num, den = (int(x) for x in analysis["fps"].split("/"))
    fps = num / den
    checker = checker or make_checker(settings)
    first = analysis["content"]["first_frame"]
    nt = nametag.check(reads, analysis["events"], fps, first, settings.name_expected,
                       settings.generic_names, settings.name_window_s, ocr.TAG_SCAN_FPS)
    analysis["name_tag"] = nt
    # a linha da tarja é conferida pela regra da tarja, não pela ortografia
    findings = spell.check_reads(reads, checker, skip_lines={nt["read"]} if nt.get("read") else None)
    thumbs = analysis.get("thumbs", {})
    new = []
    for f in findings:
        new.append({"kind": "spelling", "sample": int(f["frame"] / fps * video.SAMPLE_FPS), "score": 10000.0,
                    "frame": f["frame"], "show_frame": f["frame"], "value": f["conf"], "note": spell.note_for(f),
                    "group": None, "region": f["box"], "extra": {k: f[k] for k in
                    ("word", "suggestions", "line", "frames", "reread", "source", "conf")}})
    if nt["status"] != "ok" or nt.get("short") or nt.get("accent_diff"):
        fr = nt["frame"] if nt["frame"] is not None else first
        new.append({"kind": "name_tag", "sample": int(fr / fps * video.SAMPLE_FPS), "score": 10000.0,
                    "frame": fr, "show_frame": fr, "value": 0.0, "note": nt["note"], "group": None,
                    "region": nt["box"], "extra": {"status": nt["status"], "read": nt["read"],
                                                   "expected": nt["expected"],
                                                   "on_screen_s": nt.get("on_screen_s")}})
    for e in new:
        e["time"] = round(e["frame"] / fps, 3)
        e["tc"] = fmt_seconds(_rate_of(analysis), e["frame"])
        e["thumb"] = thumbs.get(str(e["show_frame"]))
    events += new
    events.sort(key=lambda e: (e["frame"] if e["frame"] is not None else 0))
    for k, e in enumerate(events):
        e["id"] = k
    analysis["events"] = events
    analysis["spelling"] = findings
    if out_dir is not None:
        _write_json(Path(out_dir) / "analysis.json", analysis)


def ensure_text_thumbs(analysis: dict, out_dir: Path, width: int) -> None:
    """Miniatura dos avisos de texto (a varredura da tarja não gera miniatura de tudo)."""
    rate = _rate_of(analysis)
    thumbs = analysis.setdefault("thumbs", {})
    for e in analysis["events"]:
        if e["kind"] not in THUMB_KINDS or e.get("show_frame") is None:
            continue
        f = e["show_frame"]
        if str(f) not in thumbs:
            name = f"f{f:07d}.jpg"
            dst = Path(out_dir) / "thumbs" / name
            if not dst.exists():
                try:
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    media.save_jpeg(analysis["path"], rate, f, dst, width)
                except Exception:  # vídeo em outro computador: fica sem miniatura
                    continue
            thumbs[str(f)] = f"thumbs/{name}"
        e["thumb"] = thumbs[str(f)]


def _rate_of(analysis: dict):
    from .timecode import parse_rate
    return parse_rate(analysis["fps"])


PAIR_KEYS = ("pair_of_frame", "until_frame", "on_screen_s")


def regroup_lists(analysis: dict, group_gap_s: float) -> bool:
    """Refaz "juntar listas" com outro intervalo, sem ler o vídeo de novo.

    Usa as regiões e frames guardados das entradas/saídas de texto. Devolve True
    se mudou algo (aí o cache deve ser regravado).
    """
    used = (analysis.get("settings_used") or {}).get("group_gap_s")
    if used is not None and abs(float(used) - float(group_gap_s)) < 1e-6:
        return False
    rate = _rate_of(analysis)
    pairs = []
    for d in analysis["events"]:
        if d["kind"] not in ("text_in", "text_out"):
            continue
        extra = {k: v for k, v in (d.get("extra") or {}).items() if k not in PAIR_KEYS}
        ev = video.Event(d["kind"], d.get("sample", 0), d.get("score", 0.0),
                         region=tuple(d["region"]) if d.get("region") else None,
                         frame=d.get("frame"), show_frame=d.get("show_frame"), extra=extra)
        pairs.append((d, ev))
    evs = [ev for _, ev in pairs]
    video.group_lists(evs, rate, float(group_gap_s))
    video.pair_text(evs, rate)
    for d, ev in pairs:
        d["group"] = ev.group
        if ev.extra:
            d["extra"] = ev.extra
        else:
            d.pop("extra", None)
    analysis.setdefault("settings_used", {})["group_gap_s"] = float(group_gap_s)
    return True


def visible_events(analysis: dict, sensitivity: int) -> list[dict]:
    """Aplica o controle de sensibilidade (sem reanalisar)."""
    out = []
    for e in analysis["events"]:
        if (e.get("extra") or {}).get("pair_of_frame") is not None:
            continue          # saída de texto já ligada à entrada (vira duração)
        if e["score"] >= video.score_threshold(e["kind"], sensitivity):
            out.append(e)
    return out


@dataclass
class FolderResult:
    folder: str
    videos: list[dict] = field(default_factory=list)
    report: dict | None = None
    warnings: list[str] = field(default_factory=list)


def analyze_folder(folder: str | Path, cache_root: str | Path, settings: Settings,
                   on_video=None, on_progress=None) -> FolderResult:
    folder = Path(folder)
    res = FolderResult(folder=str(folder))
    rp = report.find_in_folder(folder)
    if rp:
        rep = report.parse(rp)
        res.report = rep.to_dict()
    vids = list_videos(folder)
    if res.report is not None and len(res.report["edited"]) != len(vids):
        res.warnings.append(
            f"A pasta tem {len(vids)} vídeos, mas o relatório de tempo lista {len(res.report['edited'])} editados.")
    report_match = {}
    if rp:
        durs = []
        for v in vids:
            try:
                durs.append((v.name, media.probe(v).duration))
            except media.MediaError:
                durs.append((v.name, 0.0))
        matches, mw = report.match_videos(rep, durs)
        res.warnings += mw
        report_match = {m.video: m for m in matches}
    sig_in = vinheta.signature(settings.vinheta_in) if settings.vinheta_in else None
    sig_out = vinheta.signature(settings.vinheta_out) if settings.vinheta_out else None
    for k, v in enumerate(vids):
        def prog(x, k=k):
            if on_progress:
                on_progress(k, x)
        a = analyze_video(v, cache_root, settings, sig_in, sig_out, progress=prog)
        m = report_match.get(v.name)
        a["report_entry"] = ({"seconds": m.entry[0], "file": m.entry[1], "by": m.by}
                             if m and m.entry else None)
        res.videos.append(a)
        if on_video:
            on_video(k, a)
    return res
