"""Detecção de mudanças de frame (texto, slide, corte) e de cor.

Duas passadas:
1. Passada leve: o vídeo inteiro a 4 quadros/s em 320×180. Para cada quadro
   guardamos "notas" por bloco (brilho médio e quantidade de bordas) e a cor
   média. Daí saem os candidatos.
2. Refino: para cada candidato, lemos todos os frames ao redor (≈1 s) e
   achamos o frame exato em que a mudança começa e termina.

A nota de cada evento é guardada; o controle de sensibilidade da interface só
filtra por nota, sem precisar analisar de novo.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from . import media
from .timecode import Rate

SAMPLE_FPS = 4
SW, SH = 320, 180          # resolução da passada leve
BS = 10                    # bloco de 10×10 px (60×60 px no 1080p)
GH, GW = SH // BS, SW // BS          # grade de 18×32 blocos (brilho)
CGH, CGW = GH // 2, GW // 2          # grade de 9×16 blocos (cor)

# limiares (unidades de 0–255); ajustados nos testes
T_NET = 9.0        # mudança mínima que fica (bloco)
T_QUIET = 7.0      # movimento máximo antes/depois para contar como "parado"
T_CUT = 12.0       # mudança por bloco que conta para corte
CUT_FRACTION = 0.5 # fração de blocos mudando para ser corte/troca de plano
T_COLOR = 1.6      # mudança de cor (Cb/Cr, mediana dos blocos)
T_BRIGHT = 6.0     # mudança de brilho (Y, mediana dos blocos)
# imagem congelada (câmera travou): nas aulas reais, plano de câmera nunca fica
# com diferença média < ~0,17 entre amostras; frame repetido dá 0
FREEZE_GLOBAL = 0.05   # diferença média do quadro todo abaixo disso = frames iguais
FREEZE_ZONE = 0.3      # e na zona do professor também
FREEZE_MIN_S = 1.0     # duração mínima para avisar
CAMERA_NOISE = 0.15    # plano com diferença típica acima disso = câmera (não slide)


@dataclass
class Coarse:
    """Resultado da passada leve."""
    rate: Rate
    n: int
    M: np.ndarray          # (n, GH, GW) brilho médio por bloco
    E: np.ndarray          # (n, GH, GW) bordas por bloco
    CU: np.ndarray         # (n, CGH, CGW) Cb médio por bloco
    CV: np.ndarray         # (n, CGH, CGW) Cr médio por bloco
    scope: np.ndarray      # (128, 128) histograma Cb×Cr do vídeo todo
    luma_hist: np.ndarray  # (64,) histograma de brilho do vídeo todo

    def t(self, i: int) -> float:
        return i / SAMPLE_FPS


@dataclass
class Event:
    kind: str                      # text_in | text_out | change | cut | color_jump | bright_jump | slide_transition | freeze
                                   # (etapa 2, criados no analyze: spelling | name_tag)
    sample: int
    score: float
    region: tuple[float, float, float, float] | None = None   # x, y, w, h (0–1)
    frame: int | None = None       # frame exato (começo da mudança)
    show_frame: int | None = None  # frame em que a mudança terminou (bom para print)
    value: float = 0.0
    note: str = ""
    group: int | None = None
    extra: dict = field(default_factory=dict)

    def to_dict(self):
        d = {"kind": self.kind, "sample": self.sample, "score": round(float(self.score), 1),
             "frame": self.frame, "show_frame": self.show_frame, "value": round(float(self.value), 2),
             "note": self.note, "group": self.group}
        if self.region:
            d["region"] = [round(float(v), 4) for v in self.region]
        if self.extra:
            d["extra"] = self.extra
        return d


# ------------------------------------------------------------------ passada leve

def _block_mean(a: np.ndarray, gh: int, gw: int) -> np.ndarray:
    h, w = a.shape
    return a[: gh * (h // gh), : gw * (w // gw)].reshape(gh, h // gh, gw, w // gw).mean(axis=(1, 3))


def frame_features(y: np.ndarray, u: np.ndarray, v: np.ndarray):
    yf = y.astype(np.float32)
    m = _block_mean(yf, GH, GW)
    gx = np.abs(np.diff(yf, axis=1, append=yf[:, -1:]))
    gy = np.abs(np.diff(yf, axis=0, append=yf[-1:, :]))
    e = _block_mean(gx + gy, GH, GW)
    cu = _block_mean(u.astype(np.float32), CGH, CGW)
    cv = _block_mean(v.astype(np.float32), CGH, CGW)
    return m, e, cu, cv


def coarse_pass(path: str, rate: Rate, expected_frames: int | None = None, progress=None) -> Coarse:
    Ms, Es, CUs, CVs = [], [], [], []
    scope = np.zeros((128, 128), np.int64)
    lh = np.zeros(64, np.int64)
    total = int(expected_frames / float(rate.fps) * SAMPLE_FPS) + 2 if expected_frames else None
    for k, fr in enumerate(media.iter_yuv(path, SW, SH, fps=str(SAMPLE_FPS))):
        m, e, cu, cv = frame_features(fr.y, fr.u, fr.v)
        Ms.append(m.astype(np.float16))
        Es.append(e.astype(np.float16))
        CUs.append(cu.astype(np.float16))
        CVs.append(cv.astype(np.float16))
        # vectorscope médio: histograma Cb × Cr (2 níveis por casa)
        idx = (fr.u.ravel() >> 1).astype(np.int64) * 128 + (fr.v.ravel() >> 1)
        scope += np.bincount(idx, minlength=128 * 128).reshape(128, 128)
        lh += np.bincount(fr.y.ravel() >> 2, minlength=64)
        if progress and total and k % 20 == 0:
            progress(min(k / total, 0.999))
    n = len(Ms)
    z = np.zeros((0, GH, GW), np.float16)
    zc = np.zeros((0, CGH, CGW), np.float16)
    return Coarse(rate=rate, n=n,
                  M=np.stack(Ms) if n else z, E=np.stack(Es) if n else z,
                  CU=np.stack(CUs) if n else zc, CV=np.stack(CVs) if n else zc,
                  scope=scope, luma_hist=lh)


# ------------------------------------------------------------------ candidatos

def _components(mask: np.ndarray) -> list[np.ndarray]:
    """Componentes conectados (vizinhança 8) de uma máscara pequena."""
    seen = np.zeros_like(mask, bool)
    comps = []
    H, W = mask.shape
    for y0, x0 in zip(*np.nonzero(mask)):
        if seen[y0, x0]:
            continue
        stack = [(y0, x0)]
        seen[y0, x0] = True
        pts = []
        while stack:
            y, x = stack.pop()
            pts.append((y, x))
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    yy, xx = y + dy, x + dx
                    if 0 <= yy < H and 0 <= xx < W and mask[yy, xx] and not seen[yy, xx]:
                        seen[yy, xx] = True
                        stack.append((yy, xx))
        comps.append(np.array(pts))
    return comps


def _bbox(pts: np.ndarray) -> tuple[float, float, float, float]:
    y0, x0 = pts.min(axis=0)
    y1, x1 = pts.max(axis=0) + 1
    return (x0 / GW, y0 / GH, (x1 - x0) / GW, (y1 - y0) / GH)


def _nms(cands: list[Event], radius: int) -> list[Event]:
    cands = sorted(cands, key=lambda e: -e.score)
    kept: list[Event] = []
    for c in cands:
        if all(abs(c.sample - k.sample) > radius or c.kind != k.kind for k in kept):
            kept.append(c)
    return sorted(kept, key=lambda e: e.sample)


def detect(c: Coarse, content: tuple[int, int] | None = None) -> list[Event]:
    """Acha candidatos na passada leve. `content` = (amostra inicial, final) sem vinhetas."""
    n = c.n
    if n < 12:
        return []
    M = c.M.astype(np.float32)
    E = c.E.astype(np.float32)
    F = M + 0.5 * E                        # nota combinada por bloco
    D = np.zeros_like(F)
    D[1:] = np.abs(F[1:] - F[:-1])
    c_lo, c_hi = content if content else (0, n)
    c_lo, c_hi = max(c_lo, 0), min(c_hi, n)
    lo, hi = max(c_lo + 2, 2), min(c_hi - 2, n - 2)
    if hi - lo < 4:
        return []

    events: list[Event] = []
    cut_at = np.zeros(n, bool)

    # ---- cortes / troca de plano: muita coisa muda de uma amostra para a outra, de uma vez
    frac = (D > T_CUT).mean(axis=(1, 2))
    md = D.mean(axis=(1, 2))
    for i in range(lo, hi):
        neigh = max(frac[i - 1], frac[i + 1])
        by_frac = frac[i] >= CUT_FRACTION or (frac[i] >= 0.3 and frac[i] >= 2.5 * neigh)
        # zoom/close: o fundo muda pouco por bloco, mas tudo muda de uma vez
        by_mean = md[i] >= 4.0 and md[i] >= 3.0 * max(md[i - 1], md[i + 1])
        if (by_frac or by_mean) and md[i] >= md[i - 1] and md[i] >= md[i + 1]:
            cut_at[i] = True
            events.append(Event("cut", i, float(max(frac[i], md[i] / 20) * 1000), (0, 0, 1, 1),
                                value=float(frac[i]), note="corte ou troca de plano"))
    near_cut = np.convolve(cut_at.astype(np.int8), np.ones(9, np.int8), mode="same") > 0
    # cor/brilho: a transição do slide (10 frames, com desfoque) e fusões começam
    # um pouco antes do pico do corte; aulas reais deram alarme a ~1 s do corte
    near_cut_wide = np.convolve(cut_at.astype(np.int8), np.ones(17, np.int8), mode="same") > 0

    # ---- zona de movimento de cada plano (onde o professor está)
    bounds = [lo] + [i for i in range(lo, hi) if cut_at[i]] + [hi]
    zone_of = np.zeros(n, np.int32)
    zones = []
    for z, (s, e) in enumerate(zip(bounds[:-1], bounds[1:])):
        seg = D[s + 1:e]
        if seg.shape[0] < 4:
            act = np.zeros((GH, GW))
            noise = 0.5
        else:
            noise = float(np.median(seg))
            act = (seg > max(1.5, 4 * noise)).mean(axis=0)
        zm = act > 0.06
        # dilata 1 bloco
        zd = zm.copy()
        zd[1:] |= zm[:-1]; zd[:-1] |= zm[1:]; zd[:, 1:] |= zm[:, :-1]; zd[:, :-1] |= zm[:, 1:]
        zones.append(zd)
        zone_of[s:e] = z

    # ---- imagem congelada: plano de câmera em que tudo para de mudar
    frz = _freezes(D, bounds, zones, c_lo, c_hi)
    # quando a câmera volta, a imagem pula: isso é o fim do congelamento, não um corte
    ends = [f.extra["end_sample"] for f in frz]
    events = [e for e in events if not (e.kind == "cut" and any(abs(e.sample - x) <= 2 for x in ends))]
    events += frz

    # ---- mudanças locais que ficam (texto, gráfico, slide parcial)
    cands = []
    for i in range(lo, hi):
        if near_cut[i]:
            continue
        net = np.abs(F[min(i + 1, c_hi - 1)] - F[max(i - 2, c_lo)])
        # ~2 s parado antes e depois (sem olhar dentro das vinhetas)
        b0, b1 = max(i - 9, c_lo + 1), i - 1
        a0, a1 = i + 2, min(i + 10, c_hi)
        qb = D[b0:b1].max(axis=0) if b1 > b0 else np.zeros_like(net)
        qa = D[a0:a1].max(axis=0) if a1 > a0 else np.zeros_like(net)
        ev = (net > T_NET) & (qb < T_QUIET) & (qa < T_QUIET)
        # fora da zona onde o professor se mexe
        ev &= ~zones[zone_of[i]]
        if ev.sum() < 2:
            continue
        comps = [p for p in _components(ev) if len(p) >= 2]
        if not comps:
            continue
        pts = np.concatenate(comps)
        mask = np.zeros_like(ev)
        mask[pts[:, 0], pts[:, 1]] = True
        score = float(net[mask].sum())
        de = float((E[i + 1] - E[i - 2])[mask].sum())
        kind = "text_in" if de > 0 else "text_out"
        if mask.mean() > 0.45:
            kind = "change"
        big = max(comps, key=len)
        cands.append(Event(kind, i, score, _bbox(pts), value=float(mask.sum()),
                           extra={"blocks": int(mask.sum()), "main_region": _bbox(big)}))
    events += _nms(cands, 3)

    # ---- cor e brilho que mudam de repente (mesmo plano)
    CU = c.CU.astype(np.float32)
    CV = c.CV.astype(np.float32)
    Mb = M
    for i in range(lo, hi):
        if near_cut_wide[i]:
            continue
        a0, a1 = max(i - 4, c_lo), i            # antes: i-4..i-1
        b0, b1 = i + 1, min(i + 5, c_hi)        # depois: i+1..i+4
        if a1 - a0 < 3 or b1 - b0 < 3:
            continue
        du = np.median(CU[b0:b1].mean(0) - CU[a0:a1].mean(0))
        dv = np.median(CV[b0:b1].mean(0) - CV[a0:a1].mean(0))
        dc = float(np.hypot(du, dv))
        dy = float(np.median(Mb[b0:b1].mean(0) - Mb[a0:a1].mean(0)))
        stable_b = np.median(np.abs(np.diff(CU[a0:a1], axis=0)).mean(axis=(1, 2))) < 0.6
        stable_a = np.median(np.abs(np.diff(CU[b0:b1], axis=0)).mean(axis=(1, 2))) < 0.6
        if dc >= T_COLOR and stable_b and stable_a:
            ang = float(np.degrees(np.arctan2(dv, du)))
            events.append(Event("color_jump", i, dc * 100, value=dc, note="cor muda de repente",
                                extra={"dcb": round(float(du), 2), "dcr": round(float(dv), 2), "angle": round(ang)}))
        elif abs(dy) >= T_BRIGHT and stable_b and stable_a:
            events.append(Event("bright_jump", i, abs(dy) * 50, value=dy, note="brilho muda de repente"))
    out = [e for e in events if e.kind not in ("color_jump", "bright_jump")]
    # texto que entra com faixa escura por trás muda o brilho junto: o aviso de
    # texto já cobre, então não repete como "brilho muda"
    text_s = [e.sample for e in out if e.kind in ("text_in", "text_out", "change")]
    cj = [e for e in events if e.kind in ("color_jump", "bright_jump")
          and all(abs(e.sample - t) > 4 for t in text_s)]
    out += _nms(cj, 4)
    return sorted(out, key=lambda e: e.sample)


def _freezes(D: np.ndarray, bounds: list[int], zones: list[np.ndarray], c_lo: int, c_hi: int) -> list[Event]:
    """Trechos de ≥ 1 s com frames idênticos dentro de um plano de câmera.

    Slide, screencast e lousa são parados desde o começo do plano (e não têm
    ruído de câmera); congelamento acontece no MEIO de um plano que vinha
    mexendo normalmente.
    """
    out: list[Event] = []
    min_run = int(round(FREEZE_MIN_S * SAMPLE_FPS))
    for z, (s, e) in enumerate(zip(bounds[:-1], bounds[1:])):
        s1, e1 = max(s + 1, c_lo + 1), min(e, c_hi)
        if e1 - s1 < min_run + 4:
            continue
        seg = D[s1:e1]
        gm = seg.mean(axis=(1, 2))
        zm = zones[z]
        mz = seg[:, zm].mean(axis=1) if zm.any() else gm
        still = (gm < FREEZE_GLOBAL) & (mz < FREEZE_ZONE)
        # tolera 1 amostra solta (quadro-chave do H.264 muda um pouquinho)
        st = still.copy()
        for i in range(1, len(st) - 1):
            if not st[i] and st[i - 1] and st[i + 1] and gm[i] < 0.3:
                st[i] = True
        moving = ~st
        if moving.sum() < 8 or float(np.median(gm[moving])) < CAMERA_NOISE:
            continue          # não é plano de câmera (ou quase não tem trecho normal)
        d = np.diff(np.concatenate([[0], st.astype(np.int8), [0]]))
        for a, b in zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1)):
            if b - a < min_run:
                continue
            if a <= 1 or b >= len(st) - 1:
                continue      # colado no corte: provavelmente outra coisa (plano parado)
            ev = Event("freeze", s1 + int(a) - 1, 10000.0, (0, 0, 1, 1), value=(b - a) / SAMPLE_FPS,
                       note="imagem congelada")
            ev.extra["end_sample"] = s1 + int(b)
            out.append(ev)
    return out


def refine_freeze(path: str, rate: Rate, ev: Event) -> None:
    """Frame exato em que a imagem trava e em que volta a mexer."""
    fps = float(rate.fps)

    def diffs(t0: float, t1: float):
        f0 = max(0, rate.frame_at(max(t0, 0)))
        fr = media.frames_window(path, rate, f0, max(2, rate.frame_at(t1) - f0), 160, 90)
        Y = [x.y.astype(np.float32) for x in fr]
        return f0, np.array([np.abs(Y[k + 1] - Y[k]).mean() for k in range(len(Y) - 1)])

    t_start = ev.sample / SAMPLE_FPS
    f0, d = diffs(t_start - 1.5, t_start + 0.75)   # a passada leve pode achar o começo até ~1 s depois
    # frames repetidos dão ~0; o quadro-chave do H.264 no meio do congelamento
    # muda até ~0,1 (medido), e a câmera voltando muda bem mais
    tiny = 0.15
    start = None
    for k in range(len(d)):
        if (d[k:] < tiny).all():
            start = k
            break
    ev.frame = ev.show_frame = f0 + (start if start is not None else len(d) // 2)
    t_end = ev.extra["end_sample"] / SAMPLE_FPS
    f1, d2 = diffs(t_end - 0.75, t_end + 0.75)
    end = None
    for k in range(len(d2)):
        if d2[k] >= tiny and (d2[:k] < tiny).all():
            end = k
            break
    end_frame = f1 + (end if end is not None else len(d2) // 2)   # último frame igual
    ev.extra["end_frame"] = int(end_frame)
    dur = (end_frame - ev.frame + 1) / fps
    ev.value = dur
    ev.extra["duration_s"] = round(dur, 2)
    ev.note = f"imagem congelada {dur:.1f} s".replace(".", ",")


# ------------------------------------------------------------------ refino

def refine(path: str, rate: Rate, ev: Event) -> None:
    """Acha o frame exato do evento lendo todos os frames ao redor."""
    if ev.kind == "freeze":
        refine_freeze(path, rate, ev)
        return
    fps = float(rate.fps)
    t0 = (ev.sample - 3) / SAMPLE_FPS
    t1 = (ev.sample + 2) / SAMPLE_FPS
    f0 = max(0, rate.frame_at(max(t0, 0)))
    count = max(2, rate.frame_at(t1) - f0)
    frames = media.frames_window(path, rate, f0, count, SW, SH)
    if len(frames) < 2:
        ev.frame = ev.show_frame = rate.frame_at(ev.sample / SAMPLE_FPS)
        return
    feats = [frame_features(fr.y, fr.u, fr.v) for fr in frames]
    if ev.kind in ("color_jump",):
        s = np.array([[np.median(f[2]), np.median(f[3])] for f in feats])
        series = np.hypot(s[:, 0] - s[0, 0], s[:, 1] - s[0, 1])
    elif ev.kind == "bright_jump":
        series = np.array([np.median(f[0]) for f in feats])
        series = np.abs(series - series[0])
    else:
        if ev.region and ev.kind != "cut":
            x, y, w, h = ev.region
            ys, ye = int(round(y * GH)), int(round((y + h) * GH))
            xs, xe = int(round(x * GW)), int(round((x + w) * GW))
        else:
            ys, ye, xs, xe = 0, GH, 0, GW
        Fs = np.stack([(f[0] + 0.5 * f[1])[ys:ye, xs:xe] for f in feats])
        if ev.kind == "cut":
            d = np.abs(np.diff(Fs, axis=0)).mean(axis=(1, 2))
            k = int(np.argmax(d)) + 1
            ev.frame = ev.show_frame = f0 + k
            return
        series = np.abs(Fs - Fs[0]).sum(axis=(1, 2))
    total = series[-1] if series[-1] > 0 else series.max()
    if total <= 0:
        ev.frame = ev.show_frame = rate.frame_at(ev.sample / SAMPLE_FPS)
        return
    start = int(np.argmax(series >= 0.15 * total))
    done = start
    for k in range(start, len(series)):
        if series[k:].min() >= 0.85 * total:
            done = k
            break
    ev.frame = f0 + start
    ev.show_frame = f0 + done
    ev.extra["transition_frames"] = int(done - start)
    if ev.kind in ("text_in", "change") and ev.region:
        settled = settle_frame(path, rate, ev.region, ev.show_frame)
        if settled is not None and settled > ev.show_frame:
            ev.show_frame = settled
            ev.extra["transition_frames"] = int(settled - ev.frame)


SETTLE_MAX_S = 4.0     # lettering animado (desfoque, deslizando) leva até ~3 s para parar
SETTLE_RUN = 10        # frames seguidos sem mexer = texto parado


def settle_frame(path: str, rate: Rate, region, from_frame: int) -> int | None:
    """Primeiro frame em que a região para de mexer (o lettering já está no lugar).

    Teste do JP (19/10): "texto entrou" mostrava o lettering no meio da animação
    (borrado, deslizando). Lê até 4 s depois e procura 10 frames seguidos sem mudança
    na região. A mudança "parada" é medida contra o maior movimento do trecho.
    """
    fps = float(rate.fps)
    count = int(SETTLE_MAX_S * fps)
    try:
        frames = media.frames_window(path, rate, from_frame, count, SW, SH)
    except media.MediaError:
        return None
    if len(frames) < SETTLE_RUN + 2:
        return None
    x, y, w, h = region
    ys, ye = int(round(y * SH)), max(int(round((y + h) * SH)), int(round(y * SH)) + 1)
    xs, xe = int(round(x * SW)), max(int(round((x + w) * SW)), int(round(x * SW)) + 1)
    Y = np.stack([fr.y[ys:ye, xs:xe].astype(np.float32) for fr in frames])
    d = np.abs(np.diff(Y, axis=0)).mean(axis=(1, 2))      # mudança de um frame para o outro
    peak = float(d.max())
    if peak < 1.0:                                           # já estava parado
        return None
    calm = max(0.12 * peak, 0.6)
    for k in range(len(d) - SETTLE_RUN + 1):
        if (d[k:k + SETTLE_RUN] < calm).all():
            return from_frame + k
    return None


# ------------------------------------------------------------------ agrupamento

def group_lists(events: list[Event], rate: Rate, max_gap_s: float = 8.0) -> None:
    """Junta textos que entram aos poucos na mesma região (listas)."""
    if max_gap_s <= 0:
        return
    gid = 0
    open_groups: list[dict] = []
    for ev in events:
        if ev.kind != "text_in" or not ev.region or ev.frame is None:
            continue
        t = rate.seconds_of(ev.frame)
        x, y, w, h = ev.region
        mx, my = 3 / GW, 3 / GH          # margem de 3 blocos (~180 px no 1080p)
        joined = False
        for g in open_groups:
            if t - g["t_last"] > max_gap_s:
                continue
            gx, gy, gw, gh = g["box"]
            inter = not (x > gx + gw + mx or x + w < gx - mx or y > gy + gh + my or y + h < gy - my)
            if inter:
                ev.group = g["id"]
                g["t_last"] = t
                nx0, ny0 = min(gx, x), min(gy, y)
                g["box"] = (nx0, ny0, max(gx + gw, x + w) - nx0, max(gy + gh, y + h) - ny0)
                g["n"] += 1
                joined = True
                break
        if not joined:
            gid += 1
            ev.group = gid
            open_groups.append({"id": gid, "t_last": t, "box": ev.region, "n": 1})
    # grupo de um item só não é grupo
    sizes = {}
    for ev in events:
        if ev.group is not None:
            sizes[ev.group] = sizes.get(ev.group, 0) + 1
    for ev in events:
        if ev.group is not None and sizes[ev.group] < 2:
            ev.group = None


# ------------------------------------------------------------------ entrada × saída do texto

def pair_text(events: list[Event], rate: Rate, max_s: float = 90.0) -> None:
    """Liga cada saída de texto à entrada correspondente (mesma região).

    Na revisão o que importa é o texto que ENTROU; a saída vira só a duração
    ("na tela por 2,1 s") e some da lista. Saída sem entrada continua visível.
    """
    open_in: list[Event] = []
    for ev in events:
        if ev.frame is None or not ev.region:
            continue
        if ev.kind == "text_in":
            open_in.append(ev)
        elif ev.kind == "text_out":
            x, y, w, h = ev.region
            best, score = None, 0.0
            for cand in reversed(open_in):
                if rate.seconds_of(ev.frame) - rate.seconds_of(cand.frame) > max_s:
                    break
                boxes = [cand.region]
                if cand.group is not None:      # lista: compara com a caixa do grupo
                    boxes += [e.region for e in open_in if e.group == cand.group and e.region]
                for gx, gy, gw, gh in boxes:
                    iw = max(0.0, min(x + w, gx + gw) - max(x, gx))
                    ih = max(0.0, min(y + h, gy + gh) - max(y, gy))
                    inter = iw * ih
                    sc = inter / max(min(w * h, gw * gh), 1e-6)
                    if sc > score:
                        best, score = cand, sc
            if best is not None and score >= 0.4:
                ev.extra["pair_of_frame"] = best.frame
                members = [e for e in open_in if best.group is not None and e.group == best.group] or [best]
                for m in members:
                    m.extra["until_frame"] = ev.frame
                    m.extra["on_screen_s"] = round(rate.seconds_of(ev.frame) - rate.seconds_of(m.frame), 2)
                    if m in open_in:
                        open_in.remove(m)


# ------------------------------------------------------------------ sensibilidade

def score_threshold(kind: str, sensitivity: int) -> float:
    """Sensibilidade 0–100 → nota mínima. 55 é o padrão."""
    s = max(0, min(100, sensitivity)) / 100.0
    if kind in ("text_in", "text_out", "change"):
        hi, lo = 400.0, 25.0
    elif kind in ("cut", "slide_transition", "freeze", "spelling", "name_tag", "speech_phrase", "speech_repeat"):
        return 0.0
    else:
        hi, lo = 600.0, 120.0
    return float(10 ** (np.log10(hi) + (np.log10(lo) - np.log10(hi)) * s))
