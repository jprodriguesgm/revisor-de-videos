"""Acesso ao FFmpeg: localizar os executáveis, ler metadados e decodificar.

Toda leitura de imagem e som passa por aqui. As cores sempre vêm do arquivo
original (YUV), nunca de uma captura de tela.
"""
from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Iterator

import numpy as np

from .timecode import Rate, parse_rate


class MediaError(RuntimeError):
    pass


# ---------------------------------------------------------------- executáveis

def _bundled_dirs() -> list[Path]:
    dirs = []
    if os.environ.get("REVISOR_FFMPEG_DIR"):
        dirs.append(Path(os.environ["REVISOR_FFMPEG_DIR"]))
    base = getattr(sys, "_MEIPASS", None)  # app empacotado (PyInstaller)
    if base:
        dirs.append(Path(base) / "bin")
    dirs.append(Path(__file__).resolve().parent.parent / "bin")
    return dirs


def find_tool(name: str) -> str:
    exe = name + (".exe" if platform.system() == "Windows" else "")
    for d in _bundled_dirs():
        p = d / exe
        if p.is_file():
            return str(p)
    found = shutil.which(name)
    if not found:
        raise MediaError(f"{name} não encontrado")
    return found


FFMPEG = None
FFPROBE = None


def ffmpeg() -> str:
    global FFMPEG
    if FFMPEG is None:
        FFMPEG = find_tool("ffmpeg")
    return FFMPEG


def ffprobe() -> str:
    global FFPROBE
    if FFPROBE is None:
        FFPROBE = find_tool("ffprobe")
    return FFPROBE


def _hidden_window_kwargs() -> dict:
    """No Windows, evita abrir uma janela preta para cada chamada ao FFmpeg."""
    if platform.system() == "Windows":
        return {"creationflags": 0x08000000}  # CREATE_NO_WINDOW
    return {}


def hwaccel_args() -> list[str]:
    """Decodificação por hardware quando existir; o FFmpeg cai para CPU sozinho se falhar."""
    mode = os.environ.get("REVISOR_HWACCEL", "auto")
    if mode == "off":
        return []
    if platform.system() == "Darwin":
        return ["-hwaccel", "videotoolbox"]
    if platform.system() == "Windows":
        return ["-hwaccel", "auto"]
    return []


# ---------------------------------------------------------------- metadados

@dataclass
class VideoInfo:
    path: str
    duration: float
    width: int
    height: int
    rate: Rate
    frames: int
    pix_fmt: str
    color_matrix: str
    color_range: str
    has_audio: bool
    audio_rate: int = 48000
    audio_channels: int = 2
    extra: dict = field(default_factory=dict)

    @property
    def name(self) -> str:
        return Path(self.path).name


def probe(path: str | os.PathLike) -> VideoInfo:
    cmd = [ffprobe(), "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)]
    try:
        out = subprocess.run(cmd, capture_output=True, check=True, **_hidden_window_kwargs()).stdout
    except subprocess.CalledProcessError as e:
        raise MediaError(f"não consegui ler {path}: {e.stderr.decode(errors='ignore')[-300:]}") from e
    data = json.loads(out)
    v = next((s for s in data["streams"] if s.get("codec_type") == "video"), None)
    a = next((s for s in data["streams"] if s.get("codec_type") == "audio"), None)
    if v is None:
        raise MediaError(f"{path} não tem vídeo")
    rate = parse_rate(v.get("avg_frame_rate") or v.get("r_frame_rate") or "30000/1001")
    if rate.fps == 0:
        rate = parse_rate(v.get("r_frame_rate", "30000/1001"))
    duration = float(data["format"].get("duration") or v.get("duration") or 0)
    nb = v.get("nb_frames")
    frames = int(nb) if nb and nb.isdigit() else int(round(duration * float(rate.fps)))
    return VideoInfo(
        path=str(path),
        duration=duration,
        width=int(v["width"]),
        height=int(v["height"]),
        rate=rate,
        frames=frames,
        pix_fmt=v.get("pix_fmt", ""),
        color_matrix=v.get("color_space", "unknown"),
        color_range=v.get("color_range", "unknown"),
        has_audio=a is not None,
        audio_rate=int(a.get("sample_rate", 48000)) if a else 48000,
        audio_channels=int(a.get("channels", 2)) if a else 0,
        extra={"codec": v.get("codec_name"), "bit_rate": data["format"].get("bit_rate")},
    )


# ---------------------------------------------------------------- vídeo

@dataclass
class YUVFrame:
    """Um frame YUV 4:2:0 já separado em planos (uint8)."""
    y: np.ndarray
    u: np.ndarray
    v: np.ndarray


def _run_pipe(cmd: list[str]) -> subprocess.Popen:
    """FFmpeg com a saída (vídeo/áudio) num cano e as mensagens em outro.

    As mensagens são lidas O TEMPO TODO numa linha de execução separada. Antes elas só eram
    lidas no fim: no Windows o cano das mensagens é pequeno, enchia no meio do áudio, o FFmpeg
    parava esperando e o app ficava esperando o FFmpeg (análise "travada em 93%", 21/10/2026).
    """
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=10**7,
                            **_hidden_window_kwargs())
    chunks: list[bytes] = []

    def drain():
        try:
            for chunk in iter(lambda: proc.stderr.read(65536), b""):
                chunks.append(chunk)
                if len(chunks) > 64:                  # guarda só o fim (o resumo do ebur128 vem no fim)
                    del chunks[:-48]
        except (OSError, ValueError):
            pass

    t = threading.Thread(target=drain, name="ffmpeg-stderr", daemon=True)
    t.start()
    proc._rv_err = (t, chunks)          # type: ignore[attr-defined]
    return proc


def _finish_pipe(proc: subprocess.Popen) -> tuple[str, int]:
    """Fecha o cano da saída, espera o FFmpeg acabar e devolve (mensagens, código de saída)."""
    try:
        proc.stdout.close()
    except OSError:
        pass
    rc = proc.wait()
    t, chunks = proc._rv_err            # type: ignore[attr-defined]
    t.join(timeout=10)
    try:
        proc.stderr.close()
    except OSError:
        pass
    return b"".join(chunks).decode(errors="ignore"), rc


def _read_exact(stream, n: int) -> bytes | None:
    buf = bytearray()
    while len(buf) < n:
        chunk = stream.read(n - len(buf))
        if not chunk:
            return None if not buf else bytes(buf)
        buf += chunk
    return bytes(buf)


def iter_yuv(path: str, width: int, height: int, *, fps: str | None = None,
             start: float | None = None, duration: float | None = None,
             use_hw: bool = True) -> Iterator[YUVFrame]:
    """Decodifica o vídeo em YUV 4:2:0 reduzido.

    `fps=None` entrega todos os frames (para achar o frame exato).
    `start` usa busca precisa: o primeiro frame entregue é o primeiro com
    tempo >= start.
    """
    vf = []
    if fps:
        vf.append(f"fps={fps}")
    # 'area' faz média dos pixels: bom para notas de diferença e cor média
    vf.append(f"scale={width}:{height}:flags=area")
    vf.append("format=yuv420p")
    cmd = [ffmpeg(), "-hide_banner", "-nostdin", "-loglevel", "error"]
    if use_hw:
        cmd += hwaccel_args()
    if start is not None:
        cmd += ["-ss", f"{max(start, 0):.6f}"]
    cmd += ["-i", str(path)]
    if duration is not None:
        cmd += ["-t", f"{duration:.6f}"]
    cmd += ["-map", "0:v:0", "-vf", ",".join(vf), "-f", "rawvideo", "-pix_fmt", "yuv420p", "pipe:1"]
    ysz = width * height
    csz = (width // 2) * (height // 2)
    fsz = ysz + 2 * csz
    proc = _run_pipe(cmd)
    got_any = False
    try:
        while True:
            buf = _read_exact(proc.stdout, fsz)
            if buf is None or len(buf) < fsz:
                break
            got_any = True
            arr = np.frombuffer(buf, dtype=np.uint8)
            yield YUVFrame(
                y=arr[:ysz].reshape(height, width),
                u=arr[ysz:ysz + csz].reshape(height // 2, width // 2),
                v=arr[ysz + csz:].reshape(height // 2, width // 2),
            )
    finally:
        err, rc = _finish_pipe(proc)
    if not got_any and use_hw and hwaccel_args():
        # algumas máquinas recusam a aceleração; tenta de novo só com CPU
        yield from iter_yuv(path, width, height, fps=fps, start=start, duration=duration, use_hw=False)
        return
    if rc not in (0, None) and not got_any:
        raise MediaError(f"FFmpeg falhou em {path}: {err[-400:]}")


def has_alpha(pix_fmt: str) -> bool:
    """yuva444p12le, rgba, argb, ya8… têm canal de transparência."""
    p = pix_fmt or ""
    return p.startswith(("yuva", "rgba", "bgra", "argb", "abgr", "ya", "gbrap"))


def iter_alpha(path: str, width: int, height: int) -> Iterator[np.ndarray]:
    """Canal de transparência de cada frame (0 = transparente, 255 = opaco).

    Usado nas vinhetas em ProRes 4444: o começo da vinheta final e o fim da
    vinheta inicial são transparentes e deixam a aula aparecer por baixo.
    """
    cmd = [ffmpeg(), "-hide_banner", "-nostdin", "-loglevel", "error", "-i", str(path),
           "-map", "0:v:0", "-vf", f"alphaextract,scale={width}:{height}:flags=area,format=gray",
           "-f", "rawvideo", "-pix_fmt", "gray", "pipe:1"]
    fsz = width * height
    proc = _run_pipe(cmd)
    try:
        while True:
            buf = _read_exact(proc.stdout, fsz)
            if buf is None or len(buf) < fsz:
                break
            yield np.frombuffer(buf, dtype=np.uint8).reshape(height, width)
    finally:
        _finish_pipe(proc)


def read_frame_full(path: str, rate: Rate, frame: int, width: int | None = None,
                    height: int | None = None) -> YUVFrame:
    """Lê um único frame exato, na resolução original (ou reduzida)."""
    t = rate.seconds_of(frame)
    start = t - 0.25 / float(rate.fps)
    info_w, info_h = width, height
    if info_w is None:
        vi = probe(path)
        info_w, info_h = vi.width, vi.height
    for fr in iter_yuv(path, info_w, info_h, start=start, duration=1.5 / float(rate.fps)):
        return fr
    raise MediaError(f"não consegui ler o frame {frame} de {path}")


def frames_window(path: str, rate: Rate, first_frame: int, count: int, width: int,
                  height: int) -> list[YUVFrame]:
    """Lê `count` frames consecutivos a partir de `first_frame` (todos os frames)."""
    start = rate.seconds_of(first_frame) - 0.25 / float(rate.fps)
    dur = (count + 0.5) / float(rate.fps)
    out = []
    for fr in iter_yuv(path, width, height, start=start, duration=dur):
        out.append(fr)
        if len(out) >= count:
            break
    return out


def save_jpeg(path: str, rate: Rate, frame: int, out_path: str | os.PathLike, width: int = 1280,
              quality: int = 3) -> None:
    """Exporta um frame como JPEG (para miniaturas, cópia e pacote de revisão).

    quality: escala do FFmpeg (2 = melhor, 31 = pior). Miniatura usa 3; o frame
    cheio da tela de revisão (zoom até 400%) usa 2.
    """
    t = rate.seconds_of(frame) - 0.25 / float(rate.fps)
    tmp = Path(str(out_path) + ".part.jpg")
    cmd = [ffmpeg(), "-hide_banner", "-nostdin", "-loglevel", "error", "-y",
           "-ss", f"{max(t, 0):.6f}", "-i", str(path), "-frames:v", "1",
           "-vf", f"scale={width}:-2:flags=lanczos:in_color_matrix=bt709:out_color_matrix=bt709",
           "-q:v", str(quality), str(tmp)]
    try:
        subprocess.run(cmd, check=True, capture_output=True, **_hidden_window_kwargs())
        if not tmp.exists() or tmp.stat().st_size == 0:
            raise MediaError(f"não consegui exportar o frame {frame} de {path}")
        tmp.replace(out_path)        # nunca deixa um JPEG pela metade no cache
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def save_clip(path: str, start_s: float, dur_s: float, out_path: str | os.PathLike, width: int = 960,
              fmt: str = "mp4") -> None:
    """Trecho curto (ex.: 8 s) para o navegador tocar quando o vídeo original não toca
    direto (ProRes, HEVC no Windows…). fmt="mp4": H.264 + AAC (Chrome, Safari, Edge);
    fmt="webm": VP9/VP8 + Opus/Vorbis (último recurso, navegador sem H.264)."""
    if fmt == "webm":
        names = _encoders()
        vc = "libvpx-vp9" if "libvpx-vp9" in names else "libvpx" if "libvpx" in names else None
        ac = "libopus" if "libopus" in names else "libvorbis" if "libvorbis" in names else None
        if vc is None or ac is None:
            raise MediaError("o FFmpeg deste computador não gera WebM")
        venc = ["-c:v", vc, "-b:v", "2M", "-deadline", "realtime", "-cpu-used", "8"]
        aenc = ["-c:a", ac, "-b:a", "96k"]
        mux = ["-f", "webm"]
    else:
        enc = h264_encoder()
        if enc is None:
            raise MediaError("o FFmpeg deste computador não tem codificador H.264")
        venc = {"libx264": ["-c:v", "libx264", "-preset", "veryfast", "-crf", "24"],
                "h264_videotoolbox": ["-c:v", "h264_videotoolbox", "-b:v", "4M"],
                "h264_mf": ["-c:v", "h264_mf", "-b:v", "4M"],
                "h264_nvenc": ["-c:v", "h264_nvenc", "-b:v", "4M"]}[enc]
        aenc = ["-c:a", "aac", "-b:a", "128k"]
        mux = ["-movflags", "+faststart", "-f", "mp4"]
    tmp = Path(str(out_path) + ".part")
    cmd = [ffmpeg(), "-hide_banner", "-nostdin", "-loglevel", "error", "-y",
           "-ss", f"{max(start_s, 0):.3f}", "-i", str(path), "-t", f"{dur_s:.3f}",
           "-vf", f"scale={width}:-2", "-pix_fmt", "yuv420p", *venc, *aenc, *mux, str(tmp)]
    try:
        subprocess.run(cmd, check=True, capture_output=True, **_hidden_window_kwargs())
        tmp.replace(out_path)
    except subprocess.CalledProcessError as e:
        raise MediaError(f"não consegui gerar o trecho: {e.stderr.decode(errors='ignore')[-300:]}") from e
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


_ENCODERS: list[set] = []


def _encoders() -> set:
    if not _ENCODERS:
        try:
            out = subprocess.run([ffmpeg(), "-hide_banner", "-encoders"], capture_output=True, text=True,
                                 **_hidden_window_kwargs()).stdout
        except (OSError, MediaError):
            out = ""
        _ENCODERS.append(set(re.findall(r"^\s*[VA]\S*\s+(\S+)", out, re.M)))
    return _ENCODERS[0]


def h264_encoder() -> str | None:
    """Codificador H.264 disponível no FFmpeg (o empacotado da etapa 6 precisa ter um)."""
    names = _encoders()
    return next((e for e in ("libx264", "h264_videotoolbox", "h264_mf", "h264_nvenc") if e in names), None)


# ---------------------------------------------------------------- áudio

def iter_audio(path: str, sample_rate: int = 48000, chunk_seconds: float = 10.0,
               loudness: dict | None = None) -> Iterator[np.ndarray]:
    """Entrega o áudio em mono float32, em blocos.

    Se `loudness` for um dicionário, no fim ele recebe a medição EBU R128
    do próprio FFmpeg (LUFS integrado, LRA e pico verdadeiro).
    """
    # framelog=verbose: o log por frame só sai em nível "verbose", então com
    # loglevel=info fica só o resumo. ("quiet" não existe no FFmpeg 4.x.)
    graph = "[0:a:0]aformat=sample_fmts=fltp,asplit=2[p][m];" \
            "[m]ebur128=peak=true:framelog=verbose[e]"
    cmd = [ffmpeg(), "-hide_banner", "-nostdin", "-nostats", "-loglevel", "info", "-i", str(path),
           "-filter_complex", graph,
           "-map", "[p]", "-ac", "1", "-ar", str(sample_rate), "-f", "f32le", "pipe:1",
           "-map", "[e]", "-f", "null", "-"]
    proc = _run_pipe(cmd)
    n = int(sample_rate * chunk_seconds) * 4
    got_any = False
    try:
        while True:
            buf = _read_exact(proc.stdout, n)
            if not buf:
                break
            usable = len(buf) - len(buf) % 4
            got_any = got_any or usable > 0
            yield np.frombuffer(buf[:usable], dtype=np.float32)
    finally:
        err, rc = _finish_pipe(proc)
    if not got_any and rc not in (0, None):
        # melhor avisar do que mostrar -120 dB como se fosse silêncio
        raise MediaError(f"FFmpeg não leu o áudio de {path}: {err.strip()[-400:]}")
    if loudness is not None:
        loudness.update(_parse_ebur128(err))


def _parse_ebur128(text: str) -> dict:
    out = {}
    tail = text[text.rfind("Summary:"):] if "Summary:" in text else ""
    for line in tail.splitlines():
        line = line.strip()
        try:
            if line.startswith("I:"):
                out["lufs"] = float(line.split()[1])
            elif line.startswith("LRA:"):
                out["lra"] = float(line.split()[1])
            elif line.startswith("Peak:"):
                out["true_peak_dbfs"] = float(line.split()[1])
        except (IndexError, ValueError):
            pass
    return out
