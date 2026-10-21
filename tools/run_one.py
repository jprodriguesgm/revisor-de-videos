"""Analisa UM vídeo (todas as etapas) e grava no cache. Para rodar aos poucos no Mac.
Uso: python tools/run_one.py <cache> <vinheta entrada> <vinheta saída> <vídeo>"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from revisor import analyze, vinheta  # noqa: E402

cache, vi, vo, v = sys.argv[1:5]
st = analyze.Settings(vinheta_in=vi, vinheta_out=vo)
t = time.time()
a = analyze.analyze_video(v, cache, st, vinheta.signature(vi), vinheta.signature(vo))
sp = a.get("speech") or {}
au = a.get("audio") or {}
cuts = [e for e in au.get("events", []) if e["kind"] == "speech_cut"]
vc = sum(e["kind"] == "cut" for e in a["events"])
print(f"{a['file']}: {time.time() - t:.0f} s  fala {sp.get('status')}  cortes do vídeo {vc}  "
      f"corte no meio da fala {len(cuts)}  avisos de fala {sum(e['kind'] in analyze.SPEECH_KINDS for e in a['events'])}  "
      f"tempos {a['timings']}")
for e in cuts:
    print(f"   {e['start']:.2f}s  {e['note']}  s1={e['value']}")
