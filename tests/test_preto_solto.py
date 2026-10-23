"""Tela preta, frames soltos entre dois cortes e vinheta sem fundo (pedido do JP, 22/10)."""
import subprocess

import numpy as np
import pytest

from conftest import ffmpeg, video_codec
from revisor import analyze, summary, vinheta
from revisor.timecode import parse_rate
from test_fila import needs_ffmpeg

FPS = "30000/1001"


def _clip(path, src, frames):
    subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    f"{src}{':' if '=' in src else '='}size=640x360:rate={FPS}", "-frames:v", str(frames), *video_codec(quality=True),
                    "-pix_fmt", "yuv420p", str(path)], check=True)


def _join(tmp, parts, name):
    """Junta trechos (fonte lavfi, nº de frames) num vídeo com áudio (o app precisa de áudio)."""
    files = []
    for k, (src, n) in enumerate(parts):
        f = tmp / f"p{k}.mp4"
        _clip(f, src, n)
        files.append(f)
    lst = tmp / "lista.txt"
    lst.write_text("".join(f"file '{f.as_posix()}'\n" for f in files))
    total = sum(n for _, n in parts)
    out = tmp / name
    subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
                    "-f", "lavfi", "-i", "sine=frequency=300:sample_rate=48000", "-frames:v", str(total),
                    *video_codec(quality=True), "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(out)], check=True)
    return out


def _run(tmp, video):
    st = analyze.Settings(read_text=False, transcribe=False)
    return analyze.analyze_video(video, tmp / "cache", st)


A = "testsrc2"
B = "mandelbrot"
C = "smptebars"
BLACK = "color=c=black"


@needs_ffmpeg
def test_frame_solto_entre_cortes(tmp_path):
    v = _join(tmp_path, [(A, 120), (C, 2), (B, 120)], "solto.mp4")
    a = _run(tmp_path, v)
    fl = [e for e in a["events"] if e["kind"] == "flash"]
    assert len(fl) == 1, [(e["kind"], e["frame"], e["note"]) for e in a["events"]]
    assert abs(fl[0]["frame"] - 120) <= 1 and fl[0]["extra"]["frames"] == 2 and not fl[0]["extra"]["black"]
    w = [x for x in summary.warnings_of(a) if x["kind"] == "flash"]
    assert w and w[0]["label"] == "frame solto entre cortes" and "sobra de outro plano" in w[0]["note"]


@needs_ffmpeg
def test_frame_preto_entre_cortes_e_tela_preta(tmp_path):
    v = _join(tmp_path, [(A, 120), (BLACK, 1), (B, 120), (BLACK, 45), (A, 120)], "preto.mp4")
    a = _run(tmp_path, v)
    fl = [e for e in a["events"] if e["kind"] == "flash"]
    bl = [e for e in a["events"] if e["kind"] == "black"]
    assert len(fl) == 1 and fl[0]["extra"]["black"] and abs(fl[0]["frame"] - 120) <= 1, fl
    assert "frame preto" in fl[0]["note"]
    assert len(bl) == 1 and abs(bl[0]["frame"] - 241) <= 2 and 40 <= bl[0]["extra"]["frames"] <= 47, bl
    assert "tela preta" in bl[0]["note"]


@needs_ffmpeg
def test_cortes_normais_sem_alarme(tmp_path):
    # cortes secos comuns, um frame de cada vez: nenhum aviso de frame solto nem de tela preta
    v = _join(tmp_path, [(A, 90), (B, 90), (C, 90), (A, 90)], "normal.mp4")
    a = _run(tmp_path, v)
    assert not [e for e in a["events"] if e["kind"] in ("flash", "black")]
    assert len([e for e in a["events"] if e["kind"] == "cut"]) >= 3


def test_vinheta_sem_fundo():
    n, h, w = 10, 46, 80
    sig = vinheta.Signature(frames=np.full((n, h, w), 120.0, np.float32), rate=parse_rate(FPS),
                            alpha=np.ones((n, h, w), np.float32))
    sig.alpha[:, :, :20] = 0.0                       # 25% da largura transparente (onde vai o fundo)
    com_fundo = np.full((n, h, w), 120.0, np.float32)
    com_fundo[:, :, :20] = 90.0                      # o fundo aparece
    sem_fundo = com_fundo.copy()
    sem_fundo[:, :, :20] = 16.0                      # preto (faixa limitada)
    assert vinheta.black_under(com_fundo, sig, 0, 0, n) == []
    assert vinheta.black_under(sem_fundo, sig, 0, 0, n) == list(range(n))
    sig.alpha[:] = 1.0                               # vinheta toda opaca: nada a conferir
    assert vinheta.black_under(sem_fundo, sig, 0, 0, n) == []
    sig.alpha = None
    assert vinheta.black_under(sem_fundo, sig, 0, 0, n) == []


def test_aula_de_tv_fundo_escuro_nao_e_tela_preta():
    from revisor import video
    m = np.full((video.GH, video.GW), 18.0, np.float32)    # fundo do estúdio escuro
    assert video.is_black(m)
    m[4:12, 10:26] = 200.0                                  # a TV clara no meio
    m[6:16, 4:9] = 90.0                                     # o professor
    assert not video.is_black(m)
