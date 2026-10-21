"""Vectorscope, waveform e conta-gotas, sempre a partir do YUV original.

Padrão: Rec.709, faixa limitada (Y 16–235, Cb/Cr 16–240).
Ângulos medidos a partir do eixo +Cb, no sentido anti-horário, como no
vectorscope do DaVinci/Premiere (Cb para a direita, Cr para cima).
"""
from __future__ import annotations

import math

import numpy as np

from . import media
from .timecode import Rate

KR, KB = 0.2126, 0.0722
KG = 1 - KR - KB
SKIN_LINE_DEG = 123.0


def rgb_to_pbpr(r: float, g: float, b: float) -> tuple[float, float, float]:
    y = KR * r + KG * g + KB * b
    return y, (b - y) / (2 * (1 - KB)), (r - y) / (2 * (1 - KR))


def ycbcr_to_rgb(y: np.ndarray, cb: np.ndarray, cr: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Códigos 8 bits faixa limitada → RGB 0–1 (sem cortar)."""
    yn = (y.astype(np.float32) - 16) / 219
    pb = (cb.astype(np.float32) - 128) / 224
    pr = (cr.astype(np.float32) - 128) / 224
    r = yn + 2 * (1 - KR) * pr
    b = yn + 2 * (1 - KB) * pb
    g = (yn - KR * r - KB * b) / KG
    return r, g, b


def targets(level: float = 0.75) -> dict:
    """Alvos de cor (barras a 75%) em coordenadas Pb/Pr e ângulo."""
    out = {}
    for name, rgb in {"R": (1, 0, 0), "Mg": (1, 0, 1), "B": (0, 0, 1),
                      "Cy": (0, 1, 1), "G": (0, 1, 0), "Yl": (1, 1, 0)}.items():
        _, pb, pr = rgb_to_pbpr(*(c * level for c in rgb))
        out[name] = {"pb": round(pb, 4), "pr": round(pr, 4),
                     "angle": round(math.degrees(math.atan2(pr, pb)) % 360, 1),
                     "radius": round(math.hypot(pb, pr), 4)}
    return out


def angle_text(delta: float) -> str:
    if abs(delta) < 1:
        return "em cima da linha de pele"
    side = "amarelo" if delta > 0 else "vermelho/magenta"
    return f"{abs(delta):.0f}° para o lado do {side}"


def pick(path: str, rate: Rate, frame: int, x: int, y: int, size: int = 9,
         width: int | None = None, height: int | None = None) -> dict:
    """Conta-gotas: média de uma área size×size no frame original.

    x, y em pixels do vídeo original (ex.: 0–1919, 0–1079).
    """
    fr = media.read_frame_full(path, rate, frame, width, height)
    return pick_yuv(fr, frame, x, y, size)


def pick_yuv(fr: media.YUVFrame, frame: int, x: int, y: int, size: int = 9) -> dict:
    """Conta-gotas num frame já decodificado (a tela de revisão guarda o frame na memória)."""
    H, W = fr.y.shape
    x = int(min(max(x, 0), W - 1))
    y = int(min(max(y, 0), H - 1))
    h = size // 2
    x0, x1 = max(0, x - h), min(W, x + h + 1)
    y0, y1 = max(0, y - h), min(H, y + h + 1)
    Y = float(fr.y[y0:y1, x0:x1].mean())
    cx0, cx1 = x0 // 2, max(x0 // 2 + 1, (x1 + 1) // 2)
    cy0, cy1 = y0 // 2, max(y0 // 2 + 1, (y1 + 1) // 2)
    Cb = float(fr.u[cy0:cy1, cx0:cx1].mean())
    Cr = float(fr.v[cy0:cy1, cx0:cx1].mean())
    r, g, b = ycbcr_to_rgb(np.array(Y), np.array(Cb), np.array(Cr))
    pb, pr = (Cb - 128) / 224, (Cr - 128) / 224
    ang = math.degrees(math.atan2(pr, pb)) % 360
    sat = math.hypot(pb, pr) / 0.5 * 100       # 100% ≈ cor primária cheia
    delta = ang - SKIN_LINE_DEG
    if delta > 180:
        delta -= 360
    return {
        "frame": frame, "x": x, "y": y, "size": size,
        "Y": round(Y, 1), "Cb": round(Cb, 1), "Cr": round(Cr, 1),
        "luma_pct": round((Y - 16) / 219 * 100, 1),
        "rgb": [int(np.clip(round(float(c) * 255), 0, 255)) for c in (r, g, b)],
        "angle": round(ang, 1), "saturation_pct": round(sat, 1),
        "skin_delta": round(delta, 1), "skin_text": angle_text(delta),
        "pb": round(pb, 4), "pr": round(pr, 4),
    }


def frame_scopes(path: str, rate: Rate, frame: int, cols: int = 480) -> dict:
    """Gráficos do frame (tecla G): waveform de luma, parade RGB e vectorscope."""
    fr = media.read_frame_full(path, rate, frame)
    return frame_scopes_yuv(fr, frame, cols)


def frame_scopes_yuv(fr: media.YUVFrame, frame: int, cols: int = 480, full: bool = False) -> dict:
    """full=False: waveform e parade em meia resolução (1 pixel de cada 2×2), que casa
    exatamente com a cor 4:2:0 do H.264 e é ~4× mais rápido. A forma do gráfico é a mesma."""
    if full:
        Y = fr.y
        H, W = Y.shape
        # cor em resolução cheia (repete a amostra de croma)
        U = np.repeat(np.repeat(fr.u, 2, axis=0), 2, axis=1)[:H, :W]
        V = np.repeat(np.repeat(fr.v, 2, axis=0), 2, axis=1)[:H, :W]
    else:
        h = min(fr.u.shape[0], (fr.y.shape[0] + 1) // 2)
        w = min(fr.u.shape[1], (fr.y.shape[1] + 1) // 2)
        Y = fr.y[::2, ::2][:h, :w]
        U, V = fr.u[:h, :w], fr.v[:h, :w]
        H, W = Y.shape
    col = (np.arange(W) * cols // W).astype(np.int64)

    def wave(ch: np.ndarray, ncols: int, colmap: np.ndarray) -> np.ndarray:
        idx = colmap[None, :].repeat(H, 0).ravel() * 256 + ch.ravel().astype(np.int64)
        return np.bincount(idx, minlength=ncols * 256).reshape(ncols, 256).T[::-1]  # linha 0 = topo

    luma = wave(Y, cols, col)
    r, g, b = ycbcr_to_rgb(Y, U, V)
    pcols = cols // 3
    pcol = (np.arange(W) * pcols // W).astype(np.int64)
    parade = [wave(np.clip(c * 255, 0, 255).astype(np.uint8), pcols, pcol) for c in (r, g, b)]
    vs = np.bincount(fr.u.ravel().astype(np.int64) * 256 + fr.v.ravel(), minlength=65536).reshape(256, 256)
    vs = vs.T[::-1]   # x = Cb, y = Cr (para cima)
    return {"luma": luma, "parade": parade, "vectorscope": vs, "frame": frame}


def scope_png(hist: np.ndarray, color=(235, 235, 235), gamma: float = 0.45):
    """Converte um histograma em imagem RGBA (Pillow) com escala logarítmica."""
    from PIL import Image
    h = np.log1p(hist.astype(np.float64))
    if h.max() > 0:
        h = (h / h.max()) ** gamma
    a = (h * 255).astype(np.uint8)
    rgba = np.zeros(a.shape + (4,), np.uint8)
    rgba[..., 0], rgba[..., 1], rgba[..., 2] = color
    rgba[..., 3] = a
    return Image.fromarray(rgba, "RGBA")


def average_scope_png(scope128: np.ndarray):
    """Vectorscope médio (128×128 casas de Cb×Cr) → imagem."""
    vs = scope128.T[::-1]
    return scope_png(vs)


# cores dos gráficos do frame (tecla G e conta-gotas)
LUMA_COLOR = (200, 236, 210)
PARADE_COLORS = ((255, 105, 97), (110, 226, 130), (110, 160, 255))
PARADE_GAP = 6


def frame_scope_images(sc: dict) -> dict:
    """Gráficos do frame como imagens RGBA (Pillow): luma, parade e vectorscope.

    Linha 0 de cada waveform = código 255 (topo). O vectorscope tem 256×256 casas:
    x = Cb (0–255, para a direita), y = Cr (255 no topo). A tela desenha as linhas
    de referência (0%/100%, alvos Rec.709, linha de pele) por cima.
    """
    from PIL import Image
    luma = scope_png(sc["luma"], LUMA_COLOR, 0.5)
    parts = [scope_png(p, c, 0.5) for p, c in zip(sc["parade"], PARADE_COLORS)]
    pw = parts[0].width
    parade = Image.new("RGBA", (pw * 3 + PARADE_GAP * 2, parts[0].height), (0, 0, 0, 0))
    for k, im in enumerate(parts):
        parade.paste(im, (k * (pw + PARADE_GAP), 0))
    vector = scope_png(sc["vectorscope"], (235, 235, 235), 0.45)
    return {"luma": luma, "parade": parade, "vector": vector}
