"""Abrir o app: python3 -m revisor   (abre as telas no navegador)

Linha de comando para testes: python3 -m revisor analisar <pasta> ...
"""
from __future__ import annotations

import argparse
import sys
import time

from . import analyze
from .timecode import fmt_duration


def main(argv=None):
    ap = argparse.ArgumentParser(prog="revisor")
    sub = ap.add_subparsers(dest="cmd")
    ab = sub.add_parser("abrir", help="abre o app no navegador (padrão)")
    ab.add_argument("--porta", type=int, default=None)
    ab.add_argument("--sem-navegador", action="store_true", help="não abrir o navegador sozinho")
    ab.add_argument("--fechar-sozinho", action="store_true",
                    help="fechar quando nenhuma página do app estiver aberta (como o app empacotado)")
    a = sub.add_parser("analisar", help="analisa todos os vídeos de uma pasta")
    a.add_argument("pasta")
    a.add_argument("--cache", default="cache")
    a.add_argument("--vinheta-inicio")
    a.add_argument("--vinheta-final")
    a.add_argument("--sensibilidade", type=int, default=55)
    a.add_argument("--juntar", type=float, default=8.0, help="segundos para juntar listas (0 = não juntar)")
    a.add_argument("--nome-tarja", help="nome que deve aparecer na tarja (ex.: \"Maria Clara Souza\")")
    a.add_argument("--lista-propria", help="arquivo .txt com palavras aceitas (uma por linha)")
    a.add_argument("--sem-texto", action="store_true", help="não ler o texto da tela (sem OCR/ortografia/tarja)")
    a.add_argument("--sem-fala", action="store_true", help="não transcrever as falas (sem Whisper)")
    args = ap.parse_args(argv)

    if args.cmd in (None, "abrir"):
        from . import server
        server.serve(port=getattr(args, "porta", None), open_browser=not getattr(args, "sem_navegador", False),
                     auto_exit=getattr(args, "fechar_sozinho", False))
        return 0

    if args.cmd == "analisar":
        st = analyze.Settings(sensitivity=args.sensibilidade, group_gap_s=args.juntar,
                              vinheta_in=args.vinheta_inicio, vinheta_out=args.vinheta_final,
                              read_text=not args.sem_texto, name_expected=args.nome_tarja,
                              custom_words_file=args.lista_propria, transcribe=not args.sem_fala)
        t0 = time.time()

        def on_video(k, a):
            vis = analyze.visible_events(a, st.sensitivity)
            au = a.get("audio") or {}
            print(f"[{k + 1}] {a['file']}  {fmt_duration(a['duration'])}  "
                  f"{len(vis)} frames marcados  áudio mín {au.get('min_db')} / máx {au.get('peak_dbfs')} / "
                  f"média {au.get('avg_db')} dB  ({a['timings']['total_s']} s)")
            for e in vis:
                extra = f"  {e['note']}" if e["kind"] in analyze.THUMB_KINDS else ""
                print(f"      {e['tc']}  {e['kind']:<11} nota {e['score']:>7}  grupo {e['group']}{extra}")
            sp = a.get("speech") or {}
            if sp.get("status"):
                print(f"      fala: {sp['status']}  {len(sp.get('words', []))} palavras  ({sp.get('seconds', 0)} s)")
            nt = a.get("name_tag")
            if nt:
                print(f"      tarja: {nt['note']}")
            for e in au.get("events", []):
                print(f"      {e['start']:>8.2f}s  áudio {e['kind']:<12} {e['note']}")
            for w in a["vinheta"]["warnings"]:
                print(f"      vinheta: {w['note']}")

        res = analyze.analyze_folder(args.pasta, args.cache, st, on_video=on_video)
        for w in res.warnings:
            print("AVISO:", w)
        print(f"pronto em {time.time() - t0:.1f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
