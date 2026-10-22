"""Imagens da tela de revisão, feitas na hora a partir do vídeo original.

- miniatura (640 px) e frame cheio (resolução original, para o zoom até 400%),
  guardados no cache: <cache>/<id>/thumbs/ e <cache>/<id>/full/
- frame YUV decodificado na memória (os últimos poucos), para o conta-gotas e os
  gráficos não lerem o vídeo de novo a cada movimento do mouse
- gráficos do frame (tecla G): waveform de luma, parade RGB e vectorscope em PNG
- trecho em volta do frame (padrão 8 s) em MP4 quando o navegador não toca o vídeo original

Tudo é cache: apagar a pasta não perde nada (o app refaz).
"""
from __future__ import annotations

import io
import threading
from collections import OrderedDict
from pathlib import Path

from . import media, scopes
from .timecode import Rate

THUMB_W = 640
FULL_QUALITY = 2
CLIP_HALF_S = 4.0                       # padrão: 4 s antes e 4 s depois (o JP escolhe na tela)
CLIP_HALF_CHOICES = (1.0, 2.0, 3.0, 4.0, 6.0, 8.0, 10.0, 15.0)


def clip_half(value) -> float:
    """Metade do trecho (segundos antes = depois do frame), só entre as opções da tela."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return CLIP_HALF_S
    return v if v in CLIP_HALF_CHOICES else CLIP_HALF_S


class FrameService:
    def __init__(self, cache_root_fn):
        self._cache_root = cache_root_fn      # função: a pasta do cache pode mudar nas configurações
        self._ffmpeg_slots = threading.BoundedSemaphore(3)
        self._file_locks: dict[str, threading.Lock] = {}
        self._locks_lock = threading.Lock()
        self._yuv: OrderedDict = OrderedDict()
        self._scopes: OrderedDict = OrderedDict()
        self._mem_lock = threading.Lock()

    # ------------------------------------------------------------ utilidades
    def _lock_for(self, key: str) -> threading.Lock:
        with self._locks_lock:
            lk = self._file_locks.get(key)
            if lk is None:
                lk = self._file_locks[key] = threading.Lock()
            return lk

    def _remember(self, store: OrderedDict, key, value, limit: int):
        with self._mem_lock:
            store[key] = value
            store.move_to_end(key)
            while len(store) > limit:
                store.popitem(last=False)

    def _recall(self, store: OrderedDict, key):
        with self._mem_lock:
            v = store.get(key)
            if v is not None:
                store.move_to_end(key)
            return v

    def forget(self, vid: str) -> None:
        """Esquece o que está na memória de um vídeo (ele vai ser analisado de novo)."""
        with self._mem_lock:
            for store in (self._yuv, self._scopes):
                for key in [k for k in store if k[0] == vid]:
                    del store[key]

    # ------------------------------------------------------------ JPEG
    def jpeg(self, vid: str, video_path: str | None, rate: Rate, frame: int, size: str = "thumb",
             width: int = 1920) -> Path | None:
        """Caminho do JPEG do frame (faz na hora se não existir). None se o vídeo não está aqui."""
        root = Path(self._cache_root()) / vid
        if size == "thumb":
            dst = root / "thumbs" / f"f{frame:07d}.jpg"
            w, q = THUMB_W, 3
        else:
            dst = root / "full" / f"f{frame:07d}.jpg"
            w, q = width, FULL_QUALITY
        if dst.exists() and dst.stat().st_size > 0:
            return dst
        if not video_path or not Path(video_path).exists():
            # vídeo em outro computador: frame cheio vira a miniatura (se houver)
            alt = root / "thumbs" / f"f{frame:07d}.jpg"
            return alt if alt.exists() else None
        with self._lock_for(str(dst)):
            if dst.exists() and dst.stat().st_size > 0:
                return dst
            dst.parent.mkdir(parents=True, exist_ok=True)
            with self._ffmpeg_slots:
                media.save_jpeg(video_path, rate, frame, dst, w, q)
        return dst

    # ------------------------------------------------------------ YUV, conta-gotas e gráficos
    def yuv(self, vid: str, video_path: str, rate: Rate, frame: int, width: int, height: int) -> media.YUVFrame:
        key = (vid, frame)
        fr = self._recall(self._yuv, key)
        if fr is not None:
            return fr
        with self._lock_for(f"yuv:{vid}:{frame}"):
            fr = self._recall(self._yuv, key)
            if fr is not None:
                return fr
            with self._ffmpeg_slots:
                fr = media.read_frame_full(video_path, rate, frame, width, height)
            self._remember(self._yuv, key, fr, 4)
            return fr

    def pick(self, vid: str, video_path: str, rate: Rate, frame: int, width: int, height: int,
             x: int, y: int, size: int = 9) -> dict:
        fr = self.yuv(vid, video_path, rate, frame, width, height)
        return scopes.pick_yuv(fr, frame, x, y, size)

    def scope_png(self, vid: str, video_path: str, rate: Rate, frame: int, width: int, height: int,
                  kind: str) -> bytes:
        if kind not in ("luma", "parade", "vector"):
            raise ValueError(kind)
        key = (vid, frame)
        imgs = self._recall(self._scopes, key)
        if imgs is None:
            fr = self.yuv(vid, video_path, rate, frame, width, height)
            sc = scopes.frame_scopes_yuv(fr, frame, cols=480)
            imgs = {}
            for k, im in scopes.frame_scope_images(sc).items():
                buf = io.BytesIO()
                im.save(buf, "PNG", optimize=False, compress_level=3)
                imgs[k] = buf.getvalue()
            self._remember(self._scopes, key, imgs, 6)
        return imgs[kind]

    # ------------------------------------------------------------ trecho em volta do frame
    def clip(self, vid: str, video_path: str, rate: Rate, frame: int, duration: float,
             fmt: str = "mp4", half: float = CLIP_HALF_S) -> tuple[Path, float]:
        """Trecho em volta do frame (padrão 4 s antes e 4 s depois). Devolve (arquivo, segundo em que começa)."""
        fmt = "webm" if fmt == "webm" else "mp4"
        half = clip_half(half)
        t = rate.seconds_of(frame)
        start = max(0.0, t - half)
        dur = min(t + half - start, max(duration - start, 0.5))
        name = f"c{frame:07d}.{fmt}" if half == CLIP_HALF_S else f"c{frame:07d}_{int(half * 10):03d}.{fmt}"
        dst = Path(self._cache_root()) / vid / "clips" / name
        if dst.exists() and dst.stat().st_size > 0:
            return dst, start
        with self._lock_for(str(dst)):
            if not (dst.exists() and dst.stat().st_size > 0):
                dst.parent.mkdir(parents=True, exist_ok=True)
                with self._ffmpeg_slots:
                    media.save_clip(video_path, start, dur, dst, fmt=fmt)
        return dst, start
