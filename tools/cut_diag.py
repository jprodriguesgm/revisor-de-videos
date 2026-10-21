"""Diagnóstico do "corte no meio da fala": mede, em cada candidato, várias
características (só números, nada de áudio) no áudio montado (com emendas
plantadas) e no limpo. Uso: python tools/cut_diag.py <pasta do montar> <saída.json>"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from revisor import audio, media  # noqa: E402

SR = 48000


def decode(p):
    r = subprocess.run([media.ffmpeg(), "-hide_banner", "-loglevel", "error", "-i", str(p), "-ac", "1",
                        "-ar", str(SR), "-f", "f32le", "pipe:1"], capture_output=True, check=True)
    return np.frombuffer(r.stdout, np.float32).astype(np.float64)


def lpc(x, order=20):
    x = x * np.hanning(x.size)
    r = np.correlate(x, x, "full")[x.size - 1:x.size + order]
    if r[0] <= 0:
        return None
    a = np.zeros(order + 1); a[0] = 1.0; e = r[0]
    for i in range(1, order + 1):
        k = -(r[i] + np.dot(a[1:i], r[i - 1:0:-1])) / e
        a[1:i + 1] = a[1:i + 1] + k * np.concatenate([a[1:i][::-1], [1.0]])
        e *= (1 - k * k)
        if e <= 0:
            return None
    return a


def voicing(x):
    x = x - x.mean()
    if np.dot(x, x) <= 1e-12:
        return 0.0
    ac = np.correlate(x, x, "full")[x.size - 1:]
    lo, hi = SR // 400, SR // 70
    return float(ac[lo:hi].max() / ac[0])


def spec(x):
    X = np.abs(np.fft.rfft(x * np.hanning(x.size))) + 1e-9
    return 20 * np.log10(X[3:200])      # até ~19 kHz em passos de ~94 Hz


def feats(x, t):
    c = int(t * SR)
    m = SR // 1000
    if c - 40 * m < 0 or c + 40 * m > x.size:
        return None
    pre = x[c - 25 * m:c - 3 * m]
    a = lpc(pre)
    out = {}
    if a is not None:
        seg = x[c - 26 * m:c + 4 * m]
        res = np.convolve(seg, a, "full")[a.size - 1:seg.size]
        base = res[: 21 * m]
        peak = np.abs(res[22 * m:]).max()
        out["lpc_ratio_db"] = float(20 * np.log10(peak / (np.sqrt((base ** 2).mean()) + 1e-12)))
    n = 512
    s_b = spec(x[c - m - n:c - m]); s_a = spec(x[c + m:c + m + n])
    s_bb = spec(x[c - m - 2 * n:c - m - n])
    s_aa = spec(x[c + m + n:c + m + 2 * n])
    d_cross = np.sqrt(((s_a - s_b) ** 2).mean())
    d_nat = (np.sqrt(((s_b - s_bb) ** 2).mean()) + np.sqrt(((s_aa - s_a) ** 2).mean())) / 2
    out["spec_jump"] = float(d_cross)
    out["spec_nat"] = float(d_nat)
    out["voice_b"] = voicing(x[c - 25 * m:c - 2 * m])
    out["voice_a"] = voicing(x[c + 2 * m:c + 25 * m])
    out["rms_b"] = float(10 * np.log10((x[c - 25 * m:c - 2 * m] ** 2).mean() + 1e-12))
    out["rms_a"] = float(10 * np.log10((x[c + 2 * m:c + 25 * m] ** 2).mean() + 1e-12))
    return out


def main(folder, out_json):
    folder = Path(folder)
    gab = json.loads((folder / "gabarito.json").read_text())
    old = audio.CUT_HF_DB
    audio.CUT_HF_DB = 8.0
    res = {}
    for name in ("montado", "limpo"):
        x = decode(folder / f"{name}.m4a")
        fine = {}
        audio._windows(str(folder / f"{name}.m4a"), SR, {}, fine)
        cands = audio.find_speech_cuts(fine["e"], fine["hf"], details=True)
        rows = []
        for cd in cands:
            f = feats(x, cd["t"])
            if f:
                rows.append({**cd, **f})
        res[name] = rows
        if name == "montado":
            planted = []
            for g in gab["events"]:
                if g["kind"] != "cut":
                    continue
                near = [r for r in rows if abs(r["t"] - g["t"]) <= 0.03]
                f = feats(x, g["t"]) or {}
                planted.append({"t": g["t"], "removed_ms": g["removed_ms"], "cand": near[0] if near else None,
                                "at": f})
            res["planted"] = planted
    audio.CUT_HF_DB = old
    Path(out_json).write_text(json.dumps(res))
    print({k: len(v) for k, v in res.items()})


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
