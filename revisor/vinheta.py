"""Acha as vinhetas inicial e final dentro de cada aula, frame a frame.

Compara os frames do vídeo com os do arquivo da vinheta (salvo uma vez nas
configurações). Entrega o frame exato da transição, os 5 frames ao redor de
cada uma e avisa quando a vinheta está cortada ou não aparece.

As vinhetas do núcleo são ProRes 4444 com transparência: a inicial termina
sumindo por cima da aula e a final começa aparecendo por cima da aula. Nas
partes transparentes a imagem é a da aula, então a comparação usa só os
pixels opacos de cada frame; frames quase todos transparentes não contam.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from . import media
from .timecode import Rate

VW, VH = 80, 46          # assinatura pequena (46 para ficar par no 4:2:0)
SEARCH = 45              # procura a vinheta até ~1,5 s deslocada
MATCH_THR = 14.0         # diferença média (0–255) para considerar o mesmo frame
SAMPLE_FOR_ALIGN = 30
OPAQUE = 0.95            # pixel conta como opaco acima disso
FULL_COVER = 0.99        # só compara frames em que a vinheta cobre (quase) a tela toda:
                         # nas aulas reais, os frames do fade não batem com o arquivo nem
                         # nos pixels opacos (a montagem mistura diferente), então ficam de fora
VISIBLE = 0.5            # vinheta "visível" quando a opacidade média passa disso
END_TOLERANCE = 10       # frames que podem faltar no fim da vinheta final (o JP aceitou 6
                         # numa aula corrigida; o fim da vinheta é parado). Configurável.


@dataclass
class Signature:
    frames: np.ndarray       # (n, VH, VW) brilho
    rate: Rate
    alpha: np.ndarray | None = None   # (n, VH, VW) 0–1, ou None se não tem transparência

    @property
    def n(self) -> int:
        return int(self.frames.shape[0])

    def masks(self) -> np.ndarray:
        if self.alpha is None:
            return np.ones(self.frames.shape, bool)
        return self.alpha >= OPAQUE

    def coverage(self) -> np.ndarray:
        """Opacidade média de cada frame (1 = cobre a tela toda)."""
        if self.alpha is None:
            return np.ones(self.n)
        return self.alpha.mean(axis=(1, 2))

    def visible_from(self) -> int:
        """Primeiro frame em que a vinheta já cobre a tela (para a final)."""
        cov = self.coverage()
        idx = np.flatnonzero(cov >= VISIBLE)
        return int(idx[0]) if idx.size else 0

    def comparable(self) -> np.ndarray:
        """Índices dos frames que entram na comparação."""
        return np.flatnonzero(self.coverage() >= FULL_COVER)

    def visible_until(self) -> int:
        """Primeiro frame (a partir do fim) em que a vinheta já sumiu (para a inicial)."""
        cov = self.coverage()
        idx = np.flatnonzero(cov >= VISIBLE)
        return int(idx[-1]) + 1 if idx.size else self.n


def signature(path: str) -> Signature:
    info = media.probe(path)
    fr = [f.y.astype(np.float32) for f in media.iter_yuv(path, VW, VH, use_hw=False)]
    frames = np.stack(fr) if fr else np.zeros((0, VH, VW), np.float32)
    alpha = None
    if media.has_alpha(info.pix_fmt) and frames.shape[0]:
        al = [a.astype(np.float32) / 255.0 for a in media.iter_alpha(path, VW, VH)]
        if len(al) >= frames.shape[0]:
            alpha = np.stack(al[:frames.shape[0]])
        elif al:   # raro: completa com o último
            al += [al[-1]] * (frames.shape[0] - len(al))
            alpha = np.stack(al)
    return Signature(frames, info.rate, alpha)


def _read(path: str, rate: Rate, first: int, count: int) -> np.ndarray:
    frames = media.frames_window(path, rate, max(first, 0), count, VW, VH)
    if not frames:
        return np.zeros((0, VH, VW), np.float32)
    return np.stack([f.y.astype(np.float32) for f in frames])


def _diffs(video: np.ndarray, sig: Signature, off: int, k: int, start: int = 0) -> np.ndarray:
    """Diferença média só nos pixels opacos. NaN = frame transparente (não conta)."""
    k = min(k, sig.n - start, video.shape[0] - off)
    if k <= 0:
        return np.full(1, 255.0)
    v = video[off:off + k]
    s = sig.frames[start:start + k]
    m = sig.masks()[start:start + k]
    cnt = m.sum(axis=(1, 2)).astype(np.float64)
    tot = (np.abs(v - s) * m).sum(axis=(1, 2))
    out = np.full(k, np.nan)
    ok = sig.coverage()[start:start + k] >= FULL_COVER
    ok &= cnt > 0
    out[ok] = tot[ok] / cnt[ok]
    return out


def _score(d: np.ndarray) -> float:
    d = d[~np.isnan(d)]
    return float(d.mean()) if d.size else 1e9


def _five(center: int, total: int) -> list[int]:
    return [f for f in range(center - 2, center + 3) if 0 <= f < total]


@dataclass
class VinhetaResult:
    start_found: bool = False
    start_first_frame: int | None = None     # primeiro frame da vinheta inicial
    content_first_frame: int | None = None   # primeiro frame depois da vinheta inicial
    start_matched: int = 0
    end_found: bool = False
    end_first_frame: int | None = None       # primeiro frame em que a vinheta final aparece
    end_matched: int = 0
    end_expected: int = 0
    start_expected: int = 0
    frames_in: list[int] = field(default_factory=list)    # 5 frames vinheta → vídeo
    frames_out: list[int] = field(default_factory=list)   # 5 frames vídeo → vinheta
    warnings: list[dict] = field(default_factory=list)

    def to_dict(self):
        return self.__dict__.copy()


def _first_bad(d: np.ndarray) -> int:
    bad = np.flatnonzero(np.nan_to_num(d, nan=0.0) >= MATCH_THR)
    return int(bad[0]) if bad.size else int(d.size)


def find(path: str, rate: Rate, total_frames: int, vin_in: Signature | None,
         vin_out: Signature | None) -> VinhetaResult:
    r = VinhetaResult()

    # ---------------- inicial
    if vin_in is not None and vin_in.n:
        r.start_expected = vin_in.n
        until = vin_in.visible_until()            # depois disso a aula já domina
        video = _read(path, rate, 0, vin_in.n + SEARCH + 5)
        best, best_off = 1e9, 0
        for off in range(0, min(SEARCH, max(video.shape[0] - 5, 1))):
            d = _score(_diffs(video, vin_in, off, SAMPLE_FOR_ALIGN))
            if d < best:
                best, best_off = d, off
        if best < MATCH_THR:
            d = _diffs(video, vin_in, best_off, vin_in.n)
            matched = _first_bad(d)
            comp = vin_in.comparable()
            last_comp = int(comp[-1]) + 1 if comp.size else vin_in.n
            r.start_found = True
            r.start_first_frame = best_off
            r.start_matched = min(matched, until)
            # tolera os 2 últimos frames diferentes (transição/fusão)
            if matched < last_comp - 2:
                r.content_first_frame = best_off + matched
                r.warnings.append({"kind": "vinheta_inicial_cortada", "frame": best_off + matched,
                                   "note": f"vinheta inicial termina antes: {matched} de {until} frames"})
            else:
                r.content_first_frame = best_off + until
            if best_off > 2:
                r.warnings.append({"kind": "vinheta_inicial_atrasada", "frame": 0,
                                   "note": f"{best_off} frames antes da vinheta inicial"})
            r.frames_in = _five(r.content_first_frame, total_frames)
        else:
            r.warnings.append({"kind": "vinheta_inicial_ausente", "frame": 0,
                               "note": "vinheta inicial não encontrada"})

    # ---------------- final
    if vin_out is not None and vin_out.n:
        r.end_expected = vin_out.n
        vis = vin_out.visible_from()              # antes disso ainda é a aula por baixo
        first = max(0, total_frames - vin_out.n - SEARCH - 5)
        video = _read(path, rate, first, total_frames - first + 2)
        best, best_off = 1e9, 0
        for off in range(0, max(video.shape[0] - 10, 1)):
            d = _score(_diffs(video, vin_out, off, SAMPLE_FOR_ALIGN + vis))
            if d < best:
                best, best_off = d, off
        if best < MATCH_THR:
            d = _diffs(video, vin_out, best_off, vin_out.n)
            matched = _first_bad(d)
            if matched >= vin_out.n - 2 and video.shape[0] - best_off < vin_out.n - 2:
                matched = video.shape[0] - best_off      # o vídeo acaba antes da vinheta
            r.end_found = True
            r.end_first_frame = first + best_off + vis
            r.end_matched = matched
            if matched < vin_out.n - max(2, END_TOLERANCE):
                r.warnings.append({"kind": "vinheta_final_cortada",
                                   "frame": min(first + best_off + matched, total_frames - 1),
                                   "note": f"vinheta final cortada: {matched} de {vin_out.n} frames"})
            r.frames_out = _five(r.end_first_frame, total_frames)
        else:
            r.warnings.append({"kind": "vinheta_final_ausente", "frame": max(total_frames - 1, 0),
                               "note": "vinheta final não encontrada"})
    return r
