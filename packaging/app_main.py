"""Ponto de entrada do app empacotado (PyInstaller).

Dois cliques: abre o servidor local e a página no navegador; fecha sozinho quando não
há página aberta (ou pelo botão "Sair"). Se já estiver aberto, só abre a página.

Pelo Terminal também aceita os comandos de teste do "python3 -m revisor", ex.:
  "Revisor de Videos.app/Contents/MacOS/Revisor de Videos" analisar <pasta> --cache <cache>
  "Revisor de Videos.exe" diagnostico
"""
from __future__ import annotations

import os
import sys
import time


def _log_to_file():
    """Sem janela de terminal: o que o app escreveria vai para revisor.log na pasta do app."""
    from revisor import appdata
    try:
        home = appdata.home()
        home.mkdir(parents=True, exist_ok=True)
        log = home / "revisor.log"
        if log.is_file() and log.stat().st_size > 2_000_000:
            log.replace(home / "revisor.log.1")
        fh = open(log, "a", encoding="utf-8", buffering=1, errors="replace")
        fh.write(f"\n--- {time.strftime('%Y-%m-%d %H:%M:%S')} abrindo (pid {os.getpid()})\n")
        sys.stdout = fh
        sys.stderr = fh
    except OSError:
        pass


def diagnostico() -> int:
    """Confere se tudo o que vai dentro do app está lá e abre."""
    import platform
    import subprocess
    from revisor import __version__, media, ocr, speech
    print(f"Revisor de Vídeos {__version__} · {platform.system()} {platform.machine()} · Python {platform.python_version()}")
    ok = True
    for name, fn in (("ffmpeg", media.ffmpeg), ("ffprobe", media.ffprobe), ("tesseract", ocr.tesseract)):
        try:
            p = fn()
            arg = "--version" if name == "tesseract" else "-version"
            out = subprocess.run([p, arg], capture_output=True, text=True, errors="replace", **media._hidden_window_kwargs())
            print(f"{name:<12} ok   {(out.stdout or out.stderr).splitlines()[0]}  ({p})")
        except Exception as e:
            ok = False
            print(f"{name:<12} FALTA {e}")
    print(f"{'H.264':<12} {media.h264_encoder() or 'FALTA'}")
    print(f"{'tessdata':<12} {'ok' if ocr.available() else 'FALTA'}  ({ocr.tessdata_dir()})")
    cli, model = speech.find_cli(), speech.find_model()
    print(f"{'whisper-cli':<12} {'ok' if cli else 'FALTA'}  ({cli})")
    gpu_cli = speech.find_gpu_cli()
    if platform.system() == "Windows":
        print(f"{'whisper-vk':<12} {'ok' if gpu_cli else 'não usado: ' + (speech.gpu_problem() or 'FALTA')}  ({gpu_cli})")
    print(f"{'modelo':<12} {'ok' if model else 'FALTA'}  ({model})")
    ok = ok and bool(media.h264_encoder()) and ocr.available() and bool(cli and model)
    if ok:
        ok = _testes_rapidos(media, ocr, speech, cli, model) and ok
    print("TUDO OK" if ok else "FALTA ALGUMA COISA")
    return 0 if ok else 1


def _testes_rapidos(media, ocr, speech, cli, model) -> bool:
    """Usa de verdade cada programa: vídeo de 2 s, trecho H.264, OCR de uma frase e Whisper."""
    import subprocess
    import tempfile
    import numpy as np
    from pathlib import Path
    from PIL import Image, ImageDraw, ImageFont
    ok = True
    hid = media._hidden_window_kwargs()
    with tempfile.TemporaryDirectory(prefix="revisor_diag_") as tmp:
        src = Path(tmp) / "teste.mp4"
        r = subprocess.run([media.ffmpeg(), "-v", "error", "-y", "-f", "lavfi", "-i",
                            "testsrc2=size=640x360:rate=30000/1001:duration=2", "-f", "lavfi", "-i",
                            "sine=frequency=440:sample_rate=48000:duration=2", "-c:v", "mpeg4", "-c:a", "aac",
                            "-shortest", str(src)], capture_output=True, text=True, **hid)
        print(f"{'vídeo teste':<12} {'ok' if r.returncode == 0 else 'ERRO ' + r.stderr[-200:]}")
        ok &= r.returncode == 0
        t = time.time()
        try:
            media.save_clip(str(src), 0, 2, Path(tmp) / "trecho.mp4", width=640)
            print(f"{'trecho H.264':<12} ok ({media.h264_encoder()}, {time.time() - t:.1f} s)")
        except Exception as e:
            print(f"{'trecho H.264':<12} ERRO {e}")
            ok = False
        im = Image.new("L", (900, 90), 255)
        try:
            font = ImageFont.load_default(size=48)
        except TypeError:
            font = ImageFont.load_default()
        ImageDraw.Draw(im).text((20, 15), "Revisão das aulas", font=font, fill=0)
        try:
            words = [r[11] for r in ocr.run_tesseract(np.array(im), psm=7, invert_auto=False)]
            txt = " ".join(words)
            good = "aulas" in txt.lower()
            print(f"{'OCR':<12} {'ok' if good else 'ERRO'} (leu: {txt!r})")
            ok &= good
        except Exception as e:
            print(f"{'OCR':<12} ERRO {e}")
            ok = False
        t = time.time()
        try:
            res = speech.transcribe_chunk(str(src), 0.0, 2.0, model=model, cli=cli)
            print(f"{'Whisper':<12} ok ({time.time() - t:.1f} s para 2 s de áudio; {len(res['words'])} palavras; "
                  f"{speech.where_text(res.get('backend'), res.get('gpu'))})")
        except Exception as e:
            print(f"{'Whisper':<12} ERRO {str(e)[-300:]}")
            ok = False
        gpu_cli = speech.find_gpu_cli()
        if gpu_cli:
            # placa de vídeo (Windows, Vulkan): não é erro se esta máquina não tiver placa (o app usa o processador)
            t = time.time()
            try:
                res = speech.transcribe_chunk(str(src), 0.0, 2.0, model=model, cli=gpu_cli)
                print(f"{'Whisper VK':<12} ok ({time.time() - t:.1f} s; "
                      f"{speech.where_text(res.get('backend'), res.get('gpu'))}"
                      f"{' · ' + res['gpu_type'] if res.get('gpu_type') else ''})")
            except Exception as e:
                print(f"{'Whisper VK':<12} não funcionou nesta máquina (o app usa o processador): {str(e)[-200:]}")
    return ok


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("-psn_")]   # o Finder antigo manda "-psn_…"
    if args and args[0] == "diagnostico":
        return diagnostico()
    if args:
        from revisor.__main__ import main as cli
        return cli(args) or 0
    if getattr(sys, "frozen", False):
        _log_to_file()
    from revisor import server
    server.serve(auto_exit=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
