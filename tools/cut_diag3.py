"""Diagnóstico 3: mesmas medidas do app (audio.cut_scores) no montado, no limpo e no
vídeo ORIGINAL (mesmo trecho), para ver se a re-codificação do teste muda os números.
Uso: python tools/cut_diag3.py <pasta do montar> <vídeo original> <saída.json>"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from revisor import audio  # noqa: E402

GRID = [(s1, s2) for s1 in (12, 14, 16, 18, 20, 22, 25) for s2 in (0, 3, 6, 10)]


def events(s1, s2, speech, t1, t2):
    hit = np.flatnonzero(speech & (s1 >= t1) & (s2 >= t2))
    if hit.size == 0:
        return []
    keep = [hit[0]]
    for k in hit[1:]:
        if k - keep[-1] >= 50:
            keep.append(k)
    return keep


def main(folder, original, out_json):
    folder = Path(folder)
    gab = json.loads((folder / "gabarito.json").read_text())
    c0 = gab["content_start"]
    out = {}
    for name, path in (("montado", folder / "montado.m4a"), ("limpo", folder / "limpo.m4a"), ("original", original)):
        fine = {}
        audio._windows(str(path), 48000, {}, fine)
        e, rp, rw = fine["e"], fine["res_peak"], fine["res_pow"]
        if name == "original":
            a = int(c0 * 1000)
            L = n_limpo
            e, rp, rw = e[a:a + L], rp[a:a + L], rw[a:a + L]
        if name == "limpo":
            n_limpo = e.size
        s1, s2, rb, ra = audio.cut_scores(e, rp, rw)
        speech = (rb > audio.CUT_SPEECH_DB) & (ra > audio.CUT_SPEECH_DB)
        speech[:50] = False
        speech[-50:] = False
        row = {"minutes": e.size / 60000}
        for t1, t2 in GRID:
            ev = events(s1, s2, speech, t1, t2)
            if name == "montado":
                pl = [g for g in gab["events"] if g["kind"] == "cut"]
                hits = sum(any(abs(k / 1000 - g["t"]) <= 0.03 for k in ev) for g in pl)
                row[f"{t1}/{t2}"] = [len(ev), hits, len(pl)]
            else:
                row[f"{t1}/{t2}"] = len(ev)
        if name == "montado":
            row["planted"] = []
            for g in gab["events"]:
                if g["kind"] == "cut":
                    k = int(g["t"] * 1000)
                    j = k - 4 + int(np.argmax(s1[k - 4:k + 5]))
                    row["planted"].append([g["t"], round(float(s1[j]), 1), round(float(s2[j]), 1)])
        out[name] = row
    Path(out_json).write_text(json.dumps(out, indent=0))
    for t1, t2 in GRID:
        k = f"{t1}/{t2}"
        m = out["montado"][k]
        print(f"s1≥{t1:2d} s2≥{t2:2d}: plantados {m[1]:2d}/{m[2]}  montado {m[0]:3d}  limpo {out['limpo'][k]:3d}  "
              f"original {out['original'][k]:3d}  (por {out['limpo']['minutes']:.1f} min)")
    print("plantados (t, s1, s2):", out["montado"]["planted"])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
