"""Diagnóstico 2 do corte no meio da fala: resíduo de predição linear (LPC).

Cada trecho de 10 ms é "previsto" a partir dos 30 ms anteriores. Numa emenda o som
muda de repente e a previsão erra feio, num estalo isolado; nos pulsos normais da
voz o erro se repete a cada período (e é parecido com os vizinhos).
Uso: python tools/cut_diag2.py <pasta do montar> <saída.json>"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from revisor import media  # noqa: E402

SR = 48000
ORDER = 16


def decode(p):
    r = subprocess.run([media.ffmpeg(), "-hide_banner", "-loglevel", "error", "-i", str(p), "-ac", "1",
                        "-ar", str(SR), "-f", "f32le", "pipe:1"], capture_output=True, check=True)
    return np.frombuffer(r.stdout, np.float32).astype(np.float64)


def levinson(r, order):
    a = np.zeros(order + 1); a[0] = 1.0; e = r[0]
    if e <= 1e-12:
        return None
    for i in range(1, order + 1):
        k = -(r[i] + np.dot(a[1:i], r[i - 1:0:-1])) / e
        a[1:i + 1] = a[1:i + 1] + k * np.concatenate([a[1:i][::-1], [1.0]])
        e *= (1 - k * k)
        if e <= 1e-15:
            return None
    return a


def residual(x):
    hop, ctx = SR // 100, 3 * SR // 100
    win = np.hanning(ctx)
    res = np.zeros_like(x)
    for s in range(ctx, x.size - hop, hop):
        seg = x[s - ctx:s] * win
        r = np.array([np.dot(seg[:ctx - k], seg[k:]) for k in range(ORDER + 1)])
        a = levinson(r, ORDER)
        if a is None:
            continue
        blk = np.lib.stride_tricks.sliding_window_view(x[s - ORDER:s + hop], ORDER + 1)[:, ::-1]
        res[s:s + hop] = blk @ a
    return res


def scores(x):
    res = residual(x)
    m = SR // 1000
    n = x.size // m
    pk = np.abs(res[:n * m]).reshape(n, m).max(axis=1)
    pw = (x[:n * m].reshape(n, m) ** 2).mean(axis=1)
    rpw = (res[:n * m].reshape(n, m) ** 2).mean(axis=1)
    from numpy.lib.stride_tricks import sliding_window_view as sw
    pad = np.concatenate([np.zeros(25), pk, np.zeros(25)])
    W = sw(pad, 51)                      # bins k-25 … k+25
    ctx = np.maximum(W[:, :22].max(axis=1), W[:, 29:].max(axis=1))     # ±4–25 ms
    s1 = 20 * np.log10((pk + 1e-9) / (ctx + 1e-9))
    padp = np.concatenate([np.zeros(25), pw, np.zeros(25)])
    P = sw(padp, 51)
    rb = 10 * np.log10(P[:, 0:21].mean(axis=1) + 1e-12)     # -25…-5 ms
    ra = 10 * np.log10(P[:, 30:].mean(axis=1) + 1e-12)      # +5…+25 ms
    padr = np.concatenate([np.zeros(25), rpw, np.zeros(25)])
    R = sw(padr, 51)
    # resíduo depois / antes (previsão continua ruim depois da emenda)
    s2 = 10 * np.log10((R[:, 27:37].mean(axis=1) + 1e-12) / (R[:, 10:20].mean(axis=1) + 1e-12))
    return s1, s2, rb, ra


def main(folder, out_json):
    folder = Path(folder)
    gab = json.loads((folder / "gabarito.json").read_text())
    out = {}
    for name in ("montado", "limpo"):
        x = decode(folder / f"{name}.m4a")
        s1, s2, rb, ra = scores(x)
        speech = (rb > -35) & (ra > -35)
        out[name] = {"minutes": x.size / SR / 60,
                     "s1_speech": np.round(s1[speech], 1).tolist()[::1],
                     "s2_speech": np.round(s2[speech], 1).tolist()}
        if name == "montado":
            pl = []
            for g in gab["events"]:
                if g["kind"] != "cut":
                    continue
                k = int(g["t"] * 1000)
                lo, hi = k - 3, k + 4
                j = lo + int(np.argmax(s1[lo:hi]))
                pl.append({"t": g["t"], "s1": float(s1[j]), "s2": float(s2[j]), "rb": float(rb[j]), "ra": float(ra[j]),
                           "dk": j - k})
            out["planted"] = pl
        # pares (s1, s2) dos picos do limpo, para ver a combinação
        if name == "limpo":
            idx = np.flatnonzero(speech & (s1 > 6))
            out["limpo_pairs"] = [[round(float(s1[i]), 1), round(float(s2[i]), 1)] for i in idx]
    Path(out_json).write_text(json.dumps(out))
    print("ok", len(out["planted"]))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
