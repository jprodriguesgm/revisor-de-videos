"""Transcrição pronta (pedido do JP, 23/11/2026).

Para não ouvir as falas de novo na revisão, o vídeo pode chegar com a transcrição feita antes
(pelo "Subir no Drive", com o mesmo motor do Revisor) ou o JP pode adicionar uma à mão.

Arquivo: "<nome do vídeo sem extensão>.transcricao.json", UTF-8:
    {"formato": "revisor-transcricao", "versao": 1,
     "video": {"arquivo": "01 Aula.mp4", "duracao": 1002.37},
     "motor": {"programa": "whisper.cpp", "modelo": "ggml-small-q5_1.bin"},
     "aproximada": false,          # true = tempos por frase (SRT/VTT), palavras espalhadas na frase
     "criado": "2026-11-23 15:20:00",
     "words": [[início, fim, "palavra", prob], ...],     # segundos do vídeo
     "segments": [[início, fim, "frase"], ...]}

Onde o app procura (nesta ordem): pasta "Transcrições" dentro da pasta dos vídeos, pasta
"Transcrições" ao lado dela (pasta do dia, como no Drive) e a própria pasta dos vídeos.
Só vale se a duração bate com o vídeo (±0,5 s): outra versão do vídeo = o app ouve sozinho.

Adicionar à mão aceita: o .json acima, o JSON do whisper (openai/mlx: "segments" com "words",
ou whisper.cpp: "transcription"), .srt e .vtt (do Premiere, por exemplo).
"""
from __future__ import annotations

import json
import re
import time
import unicodedata
from pathlib import Path

FORMAT = "revisor-transcricao"
VERSION = 1
SUFFIX = ".transcricao.json"
FOLDER_NAMES = ("Transcrições", "Transcricoes", "transcrições", "transcricoes", "Transcricões")
DURATION_TOL_S = 0.5
IMPORT_EXTS = (".json", ".srt", ".vtt")
MAX_BYTES = 30 * 1024 * 1024


class TranscriptError(Exception):
    pass


# ------------------------------------------------------------------ onde fica

def file_name(video_file: str) -> str:
    return Path(video_file).stem + SUFFIX


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def _dirs_for(video_path: Path) -> list[Path]:
    """Pastas onde procurar a transcrição de um vídeo (sem repetir)."""
    folder = video_path.parent
    cands: list[Path] = []
    for base in (folder, folder.parent):
        try:
            kids = {_nfc(k.name).lower(): k for k in base.iterdir() if k.is_dir()}
        except OSError:
            kids = {}
        for n in FOLDER_NAMES:
            k = kids.get(_nfc(n).lower())
            if k is not None and k not in cands:
                cands.append(k)
    cands.append(folder)
    return cands


def _find_file(video_path: Path) -> Path | None:
    want = _nfc(file_name(video_path.name)).lower()
    for d in _dirs_for(video_path):
        try:
            for f in d.iterdir():
                if f.is_file() and _nfc(f.name).lower() == want:
                    return f
        except OSError:
            continue
    return None


def target_dir(video_path: Path) -> Path:
    """Onde gravar uma transcrição nova: "Transcrições" dentro da pasta dos vídeos."""
    folder = Path(video_path).parent
    for d in _dirs_for(Path(video_path)):
        if d != folder and d.parent == folder:
            return d
    return folder / FOLDER_NAMES[0]


# ------------------------------------------------------------------ ler e conferir

def load(path: Path) -> dict:
    try:
        if path.stat().st_size > MAX_BYTES:
            raise TranscriptError("arquivo grande demais para uma transcrição")
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        raise TranscriptError(f"não deu para ler ({e})")
    if not isinstance(data, dict) or data.get("formato") != FORMAT:
        raise TranscriptError("não é uma transcrição do Revisor")
    words = data.get("words")
    if not isinstance(words, list):
        raise TranscriptError("transcrição sem palavras")
    clean = []
    for w in words:
        try:
            s, e, t = float(w[0]), float(w[1]), str(w[2])
            p = float(w[3]) if len(w) > 3 else 1.0
        except (TypeError, ValueError, IndexError):
            continue
        if t.strip():
            clean.append([round(s, 2), round(max(e, s), 2), t, round(p, 2)])
    data["words"] = clean
    segs = []
    for sg in data.get("segments") or []:
        try:
            segs.append([round(float(sg[0]), 2), round(float(sg[1]), 2), str(sg[2])])
        except (TypeError, ValueError, IndexError):
            continue
    data["segments"] = segs
    return data


def lookup(video_path: str | Path, duration: float | None) -> dict:
    """{"status": "ok" | "nao_bate" | "invalida" | "nenhuma", "file", "data"?, "motivo"?}"""
    vp = Path(video_path)
    f = _find_file(vp)
    if f is None:
        return {"status": "nenhuma"}
    try:
        data = load(f)
    except TranscriptError as e:
        return {"status": "invalida", "file": f.name, "motivo": str(e)}
    dur = ((data.get("video") or {}).get("duracao"))
    try:
        dur = float(dur)
    except (TypeError, ValueError):
        dur = None
    if duration is not None and (dur is None or abs(dur - float(duration)) > DURATION_TOL_S):
        return {"status": "nao_bate", "file": f.name, "path": str(f),
                "motivo": "a transcrição é de outra versão do vídeo (duração diferente)"}
    return {"status": "ok", "file": f.name, "path": str(f), "mtime": f.stat().st_mtime, "data": data}


def to_speech(found: dict, content: tuple[float, float] | None = None) -> dict:
    """Resultado no formato de speech.transcribe (para os avisos de fala)."""
    data = found["data"]
    words, segs = data["words"], data["segments"]
    if content is not None:
        a, b = content[0] - 1.0, content[1] + 1.0
        words = [w for w in words if w[1] >= a and w[0] <= b]
        segs = [s for s in segs if s[1] >= a and s[0] <= b]
    motor = data.get("motor") or {}
    return {"status": "ok", "source": "pronta", "file": found["file"], "approx": bool(data.get("aproximada")),
            "model": motor.get("modelo"), "chunks": 0, "chunks_done": 0, "seconds": 0.0,
            "words": words, "segments": segs, "backend": None, "gpu": None, "gpu_type": None,
            "at": time.time()}


# ------------------------------------------------------------------ gravar

def build(video_file: str, duration: float, words: list, segments: list, model: str | None = None,
          program: str = "whisper.cpp", approx: bool = False, origem: str | None = None) -> dict:
    d = {"formato": FORMAT, "versao": VERSION,
         "video": {"arquivo": video_file, "duracao": round(float(duration), 3)},
         "motor": {"programa": program, "modelo": model},
         "aproximada": bool(approx), "criado": time.strftime("%Y-%m-%d %H:%M:%S"),
         "words": [[round(float(w[0]), 2), round(float(w[1]), 2), str(w[2]), round(float(w[3]) if len(w) > 3 else 1.0, 2)]
                   for w in words],
         "segments": [[round(float(s[0]), 2), round(float(s[1]), 2), str(s[2])] for s in segments]}
    if origem:
        d["origem"] = origem
    return d


def write(folder: Path, video_file: str, data: dict) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    p = folder / file_name(video_file)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)
    return p


# ------------------------------------------------------------------ importar (adicionar à mão)

_TC = re.compile(r"(?:(\d+):)?(\d{1,2}):(\d{2})[,.](\d{1,3})")


def _tc(s: str) -> float:
    m = _TC.search(s)
    if not m:
        raise ValueError(s)
    h = int(m.group(1) or 0)
    ms = m.group(4).ljust(3, "0")
    return h * 3600 + int(m.group(2)) * 60 + int(m.group(3)) + int(ms) / 1000


def parse_subtitles(text: str) -> list[list]:
    """SRT ou VTT → [[início, fim, texto], ...]."""
    segs = []
    text = text.replace("\r\n", "\n").replace("\r", "\n").lstrip("﻿")
    for block in re.split(r"\n\s*\n", text):
        lines = [ln.strip() for ln in block.split("\n") if ln.strip()]
        k = next((i for i, ln in enumerate(lines) if "-->" in ln), None)
        if k is None:
            continue
        a, _, b = lines[k].partition("-->")
        try:
            s, e = _tc(a), _tc(b)
        except ValueError:
            continue
        body = " ".join(lines[k + 1:])
        body = re.sub(r"<[^>]+>", "", body)               # marcas de estilo do VTT
        body = re.sub(r"\s+", " ", body).strip()
        if body:
            segs.append([s, max(e, s), body])
    return segs


def spread_words(segs: list[list]) -> list[list]:
    """Sem tempo por palavra: espalha as palavras da frase pelo tempo dela (peso = nº de letras)."""
    out = []
    for s, e, text in segs:
        toks = text.split()
        if not toks:
            continue
        weights = [max(1, len(t)) for t in toks]
        tot = float(sum(weights))
        t = s
        for tok, w in zip(toks, weights):
            d = (e - s) * w / tot
            out.append([round(t, 2), round(t + d, 2), tok, 1.0])
            t += d
    return out


def _from_whisper_json(data: dict) -> tuple[list, list, bool, str] | None:
    # openai-whisper / mlx-whisper: {"segments": [{"start", "end", "text", "words": [{"word","start","end","probability"}]}]}
    if isinstance(data.get("segments"), list) and data["segments"] and isinstance(data["segments"][0], dict):
        segs, words, approx = [], [], False
        for sg in data["segments"]:
            try:
                s, e = float(sg["start"]), float(sg["end"])
            except (KeyError, TypeError, ValueError):
                continue
            txt = str(sg.get("text", "")).strip()
            segs.append([s, e, txt])
            ws = sg.get("words")
            if isinstance(ws, list) and ws:
                for w in ws:
                    try:
                        t = str(w.get("word", w.get("text", ""))).strip()
                        if t:
                            words.append([float(w["start"]), float(w["end"]), t, float(w.get("probability", w.get("p", 1.0)))])
                    except (KeyError, TypeError, ValueError):
                        continue
            else:
                approx = True
                words += spread_words([[s, e, txt]])
        return words, segs, approx, "whisper"
    # whisper.cpp -ojf: {"transcription": [{"offsets": {"from","to"}, "text", "tokens": [...]}]}
    if isinstance(data.get("transcription"), list):
        from . import speech
        words = [w.to_list() for w in speech.words_from_whisper_json(data)]
        segs = []
        for sg in data["transcription"]:
            try:
                segs.append([sg["offsets"]["from"] / 1000, sg["offsets"]["to"] / 1000, str(sg.get("text", "")).strip()])
            except (KeyError, TypeError):
                continue
        if not words:
            words = spread_words(segs)
        return words, segs, False, "whisper.cpp"
    return None


def import_file(src: str | Path, video_file: str, duration: float) -> dict:
    """Lê um arquivo escolhido à mão e devolve a transcrição no formato do Revisor (sem gravar)."""
    p = Path(src).expanduser()
    if not p.is_file():
        raise TranscriptError("Arquivo não encontrado.")
    ext = p.suffix.lower()
    if ext not in IMPORT_EXTS:
        raise TranscriptError("Use um arquivo .json, .srt ou .vtt.")
    if p.stat().st_size > MAX_BYTES:
        raise TranscriptError("Arquivo grande demais para uma transcrição.")
    raw = p.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    if ext == ".json":
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            raise TranscriptError("O .json não pôde ser lido.")
        if not isinstance(data, dict):
            raise TranscriptError("Esse .json não é uma transcrição conhecida.")
        if data.get("formato") == FORMAT:
            d = load(p)
            words, segs, approx, prog = d["words"], d["segments"], bool(d.get("aproximada")), \
                (d.get("motor") or {}).get("programa") or "whisper.cpp"
            model = (d.get("motor") or {}).get("modelo")
        else:
            r = _from_whisper_json(data)
            if r is None:
                raise TranscriptError("Esse .json não é uma transcrição conhecida (do Revisor ou do Whisper).")
            words, segs, approx, prog = r
            model = data.get("model") if isinstance(data.get("model"), str) else None
    else:
        segs = parse_subtitles(text)
        words, approx, prog, model = spread_words(segs), True, ext[1:].upper(), None
    if not words:
        raise TranscriptError("Não achei nenhuma fala com tempo nesse arquivo.")
    last = max(w[1] for w in words)
    if last > float(duration) + 2.0:
        raise TranscriptError(f"A transcrição vai até {_fmt(last)}, mas o vídeo tem {_fmt(duration)}: "
                              "parece ser de outro vídeo ou de outra versão.")
    words.sort(key=lambda w: w[0])
    segs.sort(key=lambda s: s[0])
    return build(video_file, duration, words, segs, model=model, program=prog, approx=approx, origem=p.name)


def _fmt(s: float) -> str:
    s = int(round(s))
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"
