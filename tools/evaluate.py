"""Compara a análise com o gabarito dos vídeos de teste.

Uso: python tools/evaluate.py <pasta do cache> <pasta com os .gabarito.json> [sensibilidade]
"""
from __future__ import annotations

import json
import sys
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from revisor import analyze  # noqa: E402
from revisor.spell import norm  # noqa: E402

FPS = Fraction(30000, 1001)
VIDEO_KINDS = {
    "cut": {"cut"}, "slide_in": {"cut", "change"}, "slide_out": {"cut", "change"},
    "text_in": {"text_in"}, "text_out": {"text_out"},
    "color_jump": {"color_jump", "bright_jump"}, "color_mismatch_cut": {"color_jump", "bright_jump", "cut"},
    "freeze": {"freeze"}, "slide_transition": {"slide_transition"},
}
AUDIO_KINDS = {"audio_spike": {"spike", "clip"}, "audio_gap": {"gap"}, "audio_clip": {"clip"},
               "audio_noise_change": {"noise_change"}}
OPTIONAL = {"mesmo enquadramento"}   # corte seco sem mudança de cor: não dá para ver (e não é erro)


def main(cache: str, gab_dir: str, sens: int = 55):
    analyses = {}
    for p in Path(cache).glob("*/analysis.json"):
        a = json.loads(p.read_text(encoding="utf-8"))
        analyses[a["file"]] = a
    total_hit = total_need = total_fp = 0
    worst = 0
    for g in sorted(Path(gab_dir).glob("*.gabarito.json")):
        gab = json.loads(g.read_text(encoding="utf-8"))
        a = analyses.get(gab["video"])
        if not a:
            print("sem análise:", gab["video"])
            continue
        vis = analyze.visible_events(a, sens)
        # saída de texto ligada à entrada não aparece na lista (vira a duração do
        # texto), mas foi achada: conta como acerto
        vis += [e for e in a["events"] if (e.get("extra") or {}).get("pair_of_frame") is not None]
        used = set()
        aud = (a.get("audio") or {}).get("events", [])
        used_a = set()
        print(f"\n== {gab['video']}")
        for ev in gab["events"]:
            k = ev["kind"]
            optional = (any(o in ev.get("note", "") for o in OPTIONAL) and k == "cut") or ev.get("optional")
            # etapa 2: erro de ortografia e tarja ligados ao texto
            if ev.get("spelling_error"):
                want = norm(ev["spelling_error"])
                hit = [e for e in vis if e["kind"] == "spelling" and e["id"] not in used
                       and norm(e["extra"]["word"]) == want and -5 <= e["frame"] - ev["frame"] <= 60]
                total_need += 1
                if hit:
                    used.add(hit[0]["id"])
                    total_hit += 1
                    print(f"  OK   {'ortografia':<20} '{ev['spelling_error']}'  achado {hit[0]['tc']}  ({hit[0]['note']})")
                else:
                    print(f"  FALTOU ortografia          '{ev['spelling_error']}'")
            if ev.get("name_tag") and ev["name_tag"] != "ok":
                hit = [e for e in vis if e["kind"] == "name_tag" and e["id"] not in used
                       and e["extra"]["status"] == ev["name_tag"]]
                total_need += 1
                if hit:
                    used.add(hit[0]["id"])
                    total_hit += 1
                    print(f"  OK   {'tarja':<20} {ev['name_tag']}  ({hit[0]['note']})")
                else:
                    print(f"  FALTOU tarja {ev['name_tag']}  (resultado: {(a.get('name_tag') or {}).get('note')})")
            if k in VIDEO_KINDS:
                tol = {"cut": 4, "text_in": 4, "text_out": 4, "freeze": 3,
                       "slide_in": 8, "slide_out": 8, "slide_transition": 10}.get(k, 8)
                best = None
                for e in vis:
                    if e["id"] in used or e["kind"] not in VIDEO_KINDS[k] or e["frame"] is None:
                        continue
                    d = e["frame"] - ev["frame"]
                    if abs(d) <= tol and (best is None or abs(d) < abs(best[1])):
                        best = (e, d)
                if best:
                    used.add(best[0]["id"])
                    worst = max(worst, abs(best[1]))
                    print(f"  OK   {k:<20} frame {ev['frame']:>5}  achado {best[0]['frame']:>5} ({best[1]:+d})  {best[0]['tc']}")
                    total_hit += 1
                    total_need += 1
                elif optional:
                    print(f"  --   {k:<20} frame {ev['frame']:>5}  (opcional: {ev.get('note')})")
                else:
                    print(f"  FALTOU {k:<18} frame {ev['frame']:>5}")
                    total_need += 1
            elif k in AUDIO_KINDS:
                t = float(ev["frame"] / FPS) if "start" not in ev else ev["start"]
                # o gabarito guarda o frame do conteúdo; tempo em segundos do arquivo:
                t = float(Fraction(ev["frame"]) / FPS)
                hit = [i for i, e in enumerate(aud) if e["kind"] in AUDIO_KINDS[k] and abs(e["start"] - t) <= 1.2
                       and i not in used_a]
                if hit:
                    used_a.add(hit[0])
                    print(f"  OK   {k:<20} {t:7.2f}s  achado {aud[hit[0]]['start']:.2f}s")
                    total_hit += 1
                else:
                    print(f"  FALTOU {k:<18} {t:7.2f}s")
                total_need += 1
            elif k.startswith("vinheta"):
                ok = any(w["kind"] == k for w in a["vinheta"]["warnings"])
                print(f"  {'OK  ' if ok else 'FALTOU'} {k}")
                total_need += 1
                total_hit += ok
        extra = [e for e in vis if e["id"] not in used]
        # saída de texto opcional achada: não é alarme
        opt_out = [ev for ev in gab["events"] if ev.get("optional")]
        extra = [e for e in extra if not any(e["kind"] == o["kind"] and abs(e["frame"] - o["frame"]) <= 6
                                             for o in opt_out)]
        # pico+clip no mesmo ponto contam como um aviso só
        extra_a = [e for i, e in enumerate(aud) if i not in used_a and not any(
            abs(e["start"] - aud[j]["start"]) < 0.5 for j in used_a)]
        for e in extra:
            print(f"  ALARME FALSO {e['kind']:<12} {e['tc']} frame {e['frame']} nota {e['score']}"
                  + (f"  {e['note']}" if e["kind"] in ("spelling", "name_tag") else ""))
        for e in extra_a:
            print(f"  ALARME FALSO áudio {e['kind']:<12} {e['start']:.2f}s")
        for w in a["vinheta"]["warnings"]:
            if not any(ev["kind"] == w["kind"] for ev in gab["events"]):
                print(f"  ALARME FALSO vinheta {w['kind']}")
                total_fp += 1
        total_fp += len(extra) + len(extra_a)
    print(f"\nAcertos: {total_hit}/{total_need}   alarmes falsos: {total_fp}   maior erro de frame: {worst}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 55)
