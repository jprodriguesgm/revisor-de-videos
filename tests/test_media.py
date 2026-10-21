"""Confere que a leitura cai no frame exato (base do timecode certo)."""
import subprocess

import numpy as np
import pytest

from conftest import video_codec
from revisor import media


@pytest.fixture(scope="module")
def numbered(tmp_path_factory):
    """Vídeo 29,97 em que o brilho de cada frame codifica o número do frame."""
    p = tmp_path_factory.mktemp("v") / "numerado.mp4"
    subprocess.run([
        media.ffmpeg(), "-v", "error", "-y", "-f", "lavfi",
        "-i", "color=c=black:s=320x180:r=30000/1001:d=6",
        "-vf", "geq=lum='mod(N*3\\,200)+20':cb=128:cr=128,format=yuv420p",
        *video_codec(quality=True), "-g", "45",
        # B-frames como nas aulas (H.264); o MPEG-4 de reserva no MP4 não acerta o tempo deles
        "-bf", "2" if "libx264" in media._encoders() else "0", str(p)], check=True)
    return str(p)


def expected(n):
    return (n * 3) % 200 + 20


def test_probe(numbered):
    info = media.probe(numbered)
    assert info.rate.nominal == 30 and info.rate.fps.denominator == 1001
    assert abs(info.frames - 180) <= 1


@pytest.mark.parametrize("frame", [0, 1, 29, 44, 45, 46, 100, 151])
def test_read_exact_frame(numbered, frame):
    info = media.probe(numbered)
    fr = media.read_frame_full(numbered, info.rate, frame)
    assert abs(float(fr.y.mean()) - expected(frame)) < 2.5


def test_window_is_consecutive(numbered):
    info = media.probe(numbered)
    frames = media.frames_window(numbered, info.rate, 40, 12, 320, 180)
    assert len(frames) == 12
    got = [round(float(f.y.mean())) for f in frames]
    want = [expected(n) for n in range(40, 52)]
    assert max(abs(a - b) for a, b in zip(got, want)) <= 2
