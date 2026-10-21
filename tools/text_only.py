"""Calibragem da etapa 2: roda só a leitura do texto (OCR + ortografia + tarja)
em análises que já estão no cache, sem refazer a etapa 1.

Uso: python tools/text_only.py <cache> [--so-checar] [--nome "Nome"] [trecho do nome do vídeo ...]
  --so-checar  não lê o vídeo de novo: refaz ortografia/tarja com as leituras guardadas
Grava <cache>/<id>/reads.json e mostra o que foi lido e os avisos.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from revisor import analyze, media, ocr, spell, video  # noqa: E402


def events_of(a: dict) -> list[video.Event]:
    out = []
    for d in a["events"]:
        if d["kind"] in analyze.TEXT_KINDS:
            continue
        out.append(video.Event(d["kind"], d["sample"], d["score"], tuple(d["region"]) if d.get("region") else None,
                               d["frame"], d["show_frame"], d["value"], d["note"], d["group"], d.get("extra") or {}))
    return out


def main(argv):
    cache = Path(argv[0])
    only_check = "--so-checar" in argv
    name = None
    if "--nome" in argv:
        name = argv[argv.index("--nome") + 1]
    which = [x for x in argv[1:] if not x.startswith("--") and x != name]
    st = analyze.Settings(name_expected=name)
    checker = analyze.make_checker(st)
    total_t = 0.0
    for p in sorted(cache.glob("*/analysis.json")):
        a = json.loads(p.read_text(encoding="utf-8"))
        if which and not any(spell.nfc(w).lower() in spell.nfc(a["file"]).lower() for w in which):
            continue
        rp = p.parent / "reads.json"
        t = time.time()
        if only_check and rp.exists():
            reads = json.loads(rp.read_text(encoding="utf-8"))
        else:
            info = media.probe(a["path"])

            def verify(rd, gray):
                for ln in rd.lines:
                    for w in ln.words:
                        if spell.word_problems(w.to_dict(), checker):
                            w.reread = ocr.reread_word(gray, w.box, info.width, info.height)
            rr = ocr.read_video(a["path"], info.rate, events_of(a),
                                (a["content"]["first_frame"], a["content"]["end_frame"]),
                                info.width, info.height, on_frame=verify)
            reads = [r.to_dict() for r in rr]
            rp.write_text(json.dumps(reads, ensure_ascii=False), encoding="utf-8")
        dt = time.time() - t
        total_t += dt
        a["text"] = {"status": "ok", "reads": reads}
        analyze.refresh_text_checks(a, st, checker)
        if not only_check:      # guarda o resultado (ortografia/tarja) no cache também
            (p.parent / "analysis_e2.json").write_text(json.dumps(a, ensure_ascii=False), encoding="utf-8")
        print(f"== {a['file']}  ({round(a['duration'] / 60, 1)} min)  {len(reads)} leituras em {dt:.1f} s", flush=True)
        if "-v" in argv:
            for rd in reads:
                txt = " | ".join(f"{ln['text']} ({ln['conf']:.0f})" for ln in rd["lines"])
                if txt:
                    print(f"   {rd['frame']:6d} {rd['source']:8s} {'crop' if rd['region'] else 'full'}: {txt}")
        for e in a["events"]:
            if e["kind"] in analyze.TEXT_KINDS:
                ex = e.get("extra") or {}
                rr = f" [releitura: {ex.get('reread')}]" if ex.get("reread") else ""
                print(f"   {e['tc']}  {e['kind']:<9} {e['note']}  · linha: {ex.get('line', '')}{rr}")
        print(f"   tarja: {a['name_tag']['note'] if a.get('name_tag') else '-'}")
    print(f"tempo de leitura: {total_t:.1f} s")


if __name__ == "__main__":
    main(sys.argv[1:])
