"""Lettering animado: o frame mostrado é quando o texto para (teste do JP, 19/10)."""
import subprocess

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFilter

from conftest import ffmpeg, video_codec
from revisor import media, video
from revisor.timecode import parse_rate

W, H = 640, 360


def _make(path, start=30, end=75, n=150):
    frames = []
    for k in range(n):
        im = Image.new("L", (W, H), 60)
        if k >= start:
            t = min(1.0, (k - start) / (end - start))
            x = int(40 + 260 * t)
            d = ImageDraw.Draw(im)
            d.rectangle([x, 60, x + 200, 100], fill=230)
            d.rectangle([x + 20, 70, x + 60, 90], fill=40)
            if t < 1.0:
                im = im.filter(ImageFilter.BoxBlur(int(12 * (1 - t)) + 1))
        frames.append(np.array(im))
    p = subprocess.Popen([ffmpeg(), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{W}x{H}",
                          "-r", "30000/1001", "-i", "-", "-pix_fmt", "yuv420p", *video_codec(quality=True),
                          str(path)], stdin=subprocess.PIPE)
    for f in frames:
        p.stdin.write(f.tobytes())
    p.stdin.close()
    assert p.wait() == 0


def test_lettering_para_depois_da_animacao(tmp_path):
    path = tmp_path / "lettering.mp4"
    _make(path)
    rate = parse_rate("30000/1001")
    region = (0.05, 0.15, 0.85, 0.15)
    f = video.settle_frame(str(path), rate, region, 40)        # no meio da animação
    assert f is not None and 74 <= f <= 80
    assert video.settle_frame(str(path), rate, region, 90) is None   # já parado: não mexe
