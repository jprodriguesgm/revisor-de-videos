"""Transições entre câmera e slide em tela cheia (regra do núcleo).

Regra: o slide ENTRA descendo (vem de cima) e SAI subindo (vai para cima),
com a mesma duração em todas as transições. Entre um slide e outro, ou entre
câmera e screencast, o normal é corte seco.

Como medimos: para cada corte já achado, lemos ~40 frames ao redor e, em
cada frame, procuramos o deslocamento vertical do slide que melhor explica a
imagem (slide deslocado por cima da câmera). Isso dá a trajetória do slide:
de onde vem, para onde vai e em quantos frames.

Medido nas aulas reais (out/2026, 64 transições em 4 aulas corrigidas): o
slide se move durante 9 frames (do último frame parado ao primeiro frame
parado, com precisão de ~4 px), entra vindo de cima e sai indo para cima,
sempre igual. Os primeiros e últimos frames da transição de 12f do Premiere
quase não se movem (suavização), por isso o movimento visível é 9.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from . import media
from .timecode import Rate

TW, TH = 48, 270          # leitura: 48 colunas × 270 linhas (4 px do 1080p por linha)
HALF = 20                  # frames lidos antes e depois do corte
STEP = 3                   # busca grossa do deslocamento (linhas)
EXPECTED_FRAMES = 9        # frames de movimento visível (medido nas aulas reais; configurável)
TOLERANCE = 2              # ± frames
PREMIERE_FRAMES = 12       # a mesma transição como o editor monta no Premiere (12f ≈ 9 visíveis)
RING_W, RING_H = 32, 18    # assinatura da moldura (bordas do slide)


@dataclass
class CutInfo:
    kind: str                     # "entra" | "sai" | "corte_seco" | "outro"
    frames: int = 0               # duração do movimento (último parado → primeiro parado)
    direction: str = ""           # "desce" | "sobe" (sentido do movimento do slide)
    from_side: str = ""           # entrada: "cima"/"baixo"; saída: para onde foi
    fit: float = 0.0              # quanto o modelo explica os frames do meio (0–1)
    screen_side: str = ""         # "antes" | "depois": de que lado está o slide
    first_moving: int | None = None
    last_moving: int | None = None
    trajectory: list[int] = field(default_factory=list)

    def to_dict(self):
        d = self.__dict__.copy()
        d["trajectory"] = [int(x) for x in self.trajectory]
        return d


def _compose(S: np.ndarray, C: np.ndarray, o: int) -> np.ndarray:
    """Slide S deslocado o linhas (o<0: mais para cima) por cima de C."""
    H = S.shape[0]
    if o == 0:
        return S
    M = C.copy()
    if o < 0:
        M[:H + o] = S[-o:]
    else:
        M[o:] = S[:H - o]
    return M


def _best_offset(F: np.ndarray, S: np.ndarray, C: np.ndarray) -> tuple[int, float]:
    H = S.shape[0]
    best, bo = 1e9, 0
    for o in range(-H, H + 1, STEP):
        e = float(np.abs(F - _compose(S, C, o)).mean())
        if e < best:
            best, bo = e, o
    for o in range(max(-H, bo - STEP + 1), min(H, bo + STEP - 1) + 1):
        e = float(np.abs(F - _compose(S, C, o)).mean())
        if e < best:
            best, bo = e, o
    return bo, best


def _trajectory(Y: np.ndarray, S: np.ndarray, C: np.ndarray, mixed: list[int]):
    """Deslocamento do slide em cada frame. Frames longe da transição recebem
    0 (slide parado no lugar) ou ±H (fora da tela) sem busca."""
    H = S.shape[0]
    lo, hi = max(mixed[0] - 3, 0), min(mixed[-1] + 3, Y.shape[0] - 1)
    traj = []
    gains = []
    for k in range(Y.shape[0]):
        F = Y[k]
        dS = float(np.abs(F - S).mean())
        dC = float(np.abs(F - C).mean())
        if not lo <= k <= hi:
            traj.append(0 if dS <= dC else -H)
            continue
        o, e = _best_offset(F, S, C)
        traj.append(o)
        if k in mixed:
            triv = min(dS, dC)
            gains.append(1.0 - e / triv if triv > 1e-6 else 0.0)
    fit = float(np.mean(gains)) if gains else 0.0
    return np.array(traj), fit


def _span(traj: np.ndarray, H: int, entering: bool) -> tuple[int, int]:
    """(último frame parado antes, primeiro frame parado depois) do movimento.

    "Parado no lugar" = até 1 linha (≈4 px no 1080p); "fora da tela" = até
    3 linhas da borda. A suavização do começo e do fim (ease) quase não move a
    imagem, então o movimento visível é um pouco menor que a duração no Premiere.
    """
    placed = np.abs(traj) <= 1
    away = np.abs(traj) >= H - 3
    n = len(traj)
    if entering:
        first_placed = next((k for k in range(n) if placed[k] and placed[k:].all()), n - 1)
        last_away = max((k for k in range(first_placed) if away[k]), default=0)
        return last_away, first_placed
    first_away = next((k for k in range(n) if away[k] and away[k:].all()), n - 1)
    last_placed = max((k for k in range(first_away) if placed[k]), default=0)
    return last_placed, first_away


def analyze_cut(path: str, rate: Rate, frame: int) -> CutInfo | None:
    frames = media.frames_window(path, rate, max(frame - HALF, 0), 2 * HALF + 1, TW, TH)
    if len(frames) < 2 * HALF + 1:
        return None
    Y = np.stack([f.y.astype(np.float32) for f in frames])
    H = TH
    A, B = Y[1], Y[-2]                    # bem antes / bem depois
    dA = np.abs(Y - A).mean(axis=(1, 2))
    dB = np.abs(Y - B).mean(axis=(1, 2))
    gap = float(np.abs(A - B).mean())
    if gap < 4.0:
        return CutInfo("outro")
    # frames "misturados": nem parecidos com antes nem com depois
    tol = max(2.0, 0.12 * gap)
    mixed = [k for k in range(Y.shape[0]) if dA[k] > tol and dB[k] > tol]
    if not mixed:
        return CutInfo("corte_seco", frames=1)
    if len(mixed) > 2 * HALF - 4:
        return CutInfo("outro")

    # testa as duas hipóteses: slide depois (entra) ou slide antes (sai)
    tin, fin = _trajectory(Y, B, A, mixed)
    tout, fout = _trajectory(Y, A, B, mixed)
    if max(fin, fout) < 0.35:
        # nada desliza: fusão, flash, zoom… (conferir na revisão)
        return CutInfo("outro", fit=max(fin, fout), frames=len(mixed))

    if fin >= fout:
        traj, fit, kind, side = tin, fin, "entra", "depois"
        a, b = _span(traj, H, True)
        start_val = int(traj[a + 1]) if a + 1 < len(traj) else -1
        from_side = "cima" if start_val < 0 else "baixo"
        direction = "desce" if start_val < 0 else "sobe"
    else:
        traj, fit, kind, side = tout, fout, "sai", "antes"
        a, b = _span(traj, H, False)
        end_val = int(traj[b - 1]) if b - 1 >= 0 else -1
        from_side = "cima" if end_val < 0 else "baixo"
        direction = "sobe" if end_val < 0 else "desce"
    moving = list(range(a + 1, b))
    base = max(frame - HALF, 0)
    return CutInfo(kind, frames=int(b - a), direction=direction,
                   from_side=from_side, fit=round(fit, 3), screen_side=side,
                   first_moving=base + (moving[0] if moving else mixed[0]),
                   last_moving=base + (moving[-1] if moving else mixed[-1]),
                   trajectory=traj.tolist())


# ------------------------------------------------------------------ moldura

def ring_signature(path: str, rate: Rate, frame: int) -> np.ndarray | None:
    """Brilho das bordas do frame (moldura do slide/screencast)."""
    fr = media.frames_window(path, rate, frame, 1, RING_W, RING_H)
    if not fr:
        return None
    y = fr[0].y.astype(np.float32)
    ring = np.ones_like(y, bool)
    ring[2:-2, 2:-2] = False
    return y[ring]


def ring_distance(a: np.ndarray | None, b: np.ndarray | None) -> float:
    if a is None or b is None:
        return 1e9
    return float(np.abs(a - b).mean())


# ------------------------------------------------------------------ regra da aula

def lesson_rule(cuts: list[dict], expected: int = EXPECTED_FRAMES, tol: int = TOLERANCE) -> list[dict]:
    """Recebe os cortes já medidos e devolve os avisos.

    Cada item de `cuts`: {"frame", "info": CutInfo, "ring_before", "ring_after"}.
    - entrada/saída com movimento: confere sentido e duração;
    - corte seco entre câmera e um slide do MESMO modelo dos que entram com
      movimento nesta aula: avisa (o slide deveria ter entrado descendo);
    - corte seco com tela de outro modelo (screencast): normal.
    """
    warns = []
    slide_rings = []
    for c in cuts:
        info = c["info"]
        if info.kind in ("entra", "sai"):
            r = c["ring_after"] if info.kind == "entra" else c["ring_before"]
            if r is not None:
                slide_rings.append(r)
            want = "desce" if info.kind == "entra" else "sobe"
            verb = "entrou" if info.kind == "entra" else "saiu"
            if info.direction != want:
                warns.append({"frame": c["frame"], "kind": "slide_transition",
                              "note": f"slide {verb} {'subindo' if info.direction == 'sobe' else 'descendo'} "
                                      f"(esperado: {'desce' if want == 'desce' else 'sobe'} em {PREMIERE_FRAMES}f no Premiere)"})
            if abs(info.frames - expected) > tol:
                warns.append({"frame": c["frame"], "kind": "slide_transition",
                              "note": f"slide {verb} em {info.frames} frames de movimento visível "
                                      f"(padrão: {PREMIERE_FRAMES}f no Premiere ≈ {expected} visíveis; "
                                      f"{'mais rápido' if info.frames < expected else 'mais lento'})"})
    if slide_rings:
        for c in cuts:
            info = c["info"]
            if info.kind != "corte_seco":
                continue
            db = min(ring_distance(c["ring_before"], r) for r in slide_rings)
            da = min(ring_distance(c["ring_after"], r) for r in slide_rings)
            # um lado é slide do modelo e o outro não (slide → slide é normal)
            if (da < 8.0) != (db < 8.0):
                verb = "entrou" if da < 8.0 else "saiu"
                want = "desce" if verb == "entrou" else "sobe"
                warns.append({"frame": c["frame"], "kind": "slide_transition",
                              "note": f"slide {verb} com corte seco (esperado: {want} em {PREMIERE_FRAMES}f no Premiere)"})
    return warns
