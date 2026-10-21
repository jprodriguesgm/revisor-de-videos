"""Gera aulas sintéticas com erros em tempos conhecidos (gabarito).

Saída (em tools/testdata/):
  vinheta_inicio.mp4, vinheta_final.mp4
  aula_A_com_erros.mp4  + aula_A_com_erros.gabarito.json
  aula_B_limpa.mp4      + aula_B_limpa.gabarito.json

Formato igual ao que o núcleo recebe: H.264 1080p 29,97 fps, VBR 5–10 Mbps,
Rec.709 faixa limitada, AAC 48 kHz.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from fractions import Fraction
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

FPS = Fraction(30000, 1001)
W, H = 1920, 1080
SR = 48000
VIN_FRAMES = 120  # ~4,0 s
OUT = Path(__file__).resolve().parent / "testdata"
def _font(*names: str) -> str:
    """DejaVu (Linux); no Mac e no Windows, Arial (o teste do GitHub roda nos dois)."""
    for n in names:
        if Path(n).is_file():
            return n
    raise SystemExit(f"fonte não encontrada: {names[0]}")


FONT_B = _font("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
               "/System/Library/Fonts/Supplemental/Arial Bold.ttf", "C:/Windows/Fonts/arialbd.ttf")
FONT = _font("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
             "/System/Library/Fonts/Supplemental/Arial.ttf", "C:/Windows/Fonts/arial.ttf")


def f_of(sec: float) -> int:
    return int(round(sec * FPS))


def s_of(frame: int) -> float:
    return float(frame / FPS)


# ------------------------------------------------------------------ imagens

def make_background() -> np.ndarray:
    x = np.linspace(0, 1, W, dtype=np.float32)[None, :, None]
    y = np.linspace(0, 1, H, dtype=np.float32)[:, None, None]
    teal = np.array([18, 112, 128], np.float32)   # RGB
    pink = np.array([196, 104, 150], np.float32)
    navy = np.array([40, 60, 120], np.float32)
    t = np.clip(x * 1.1 - 0.05, 0, 1)
    bg = teal * (1 - t) + pink * t
    bg = bg * (1 - 0.25 * y) + navy * 0.25 * y
    return np.ascontiguousarray(np.broadcast_to(bg, (H, W, 3))).astype(np.uint8)


def text_layer(lines: list[str], size: int, color=(235, 235, 235), bold=True) -> tuple[np.ndarray, np.ndarray]:
    font = ImageFont.truetype(FONT_B if bold else FONT, size)
    pad = 10
    widths = [font.getbbox(t)[2] for t in lines]
    lh = int(size * 1.25)
    img = Image.new("RGBA", (max(widths) + 2 * pad, lh * len(lines) + 2 * pad), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for i, t in enumerate(lines):
        d.text((pad, pad + i * lh), t, font=font, fill=color + (255,))
    a = np.asarray(img)
    return a[..., :3].copy(), (a[..., 3:4].astype(np.float32) / 255.0)


def make_slide() -> np.ndarray:
    img = Image.new("RGB", (W, H), (246, 246, 242))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 150], fill=(30, 70, 120))
    d.text((90, 40), "Benefícios previdenciários", font=ImageFont.truetype(FONT_B, 64), fill=(255, 255, 255))
    f = ImageFont.truetype(FONT, 46)
    for i, t in enumerate(["• Aposentadoria por idade", "• Auxílio por incapacidade temporária",
                           "• Pensão por morte", "• Salário-maternidade"]):
        d.text((120, 260 + i * 110), t, font=f, fill=(40, 40, 40))
    return np.asarray(img).copy()


def draw_person(frame: np.ndarray, t: float) -> None:
    """Professor estilizado que se mexe o tempo todo (cabeça, braços, mãos)."""
    cx = int(1420 + 18 * np.sin(1.1 * t))
    hy = int(330 + 7 * np.sin(2.3 * t))
    suit = (58, 60, 66)
    # corpo
    pts = np.array([[cx - 300, H], [cx - 250, 560], [cx - 90, 500], [cx + 90, 500], [cx + 250, 560], [cx + 300, H]])
    cv2.fillPoly(frame, [pts], suit)
    cv2.fillPoly(frame, [np.array([[cx - 70, 500], [cx + 70, 500], [cx, 760]])], (236, 236, 236))
    cv2.fillPoly(frame, [np.array([[cx - 18, 520], [cx + 18, 520], [cx + 10, 760], [cx - 10, 760]])], (140, 30, 40))
    # cabeça (tom de pele) e cabelo
    cv2.ellipse(frame, (cx, hy), (105, 140), 0, 0, 360, (186, 150, 126), -1)
    cv2.ellipse(frame, (cx, hy - 70), (112, 80), 0, 180, 360, (50, 36, 30), -1)
    cv2.ellipse(frame, (cx, hy + 95), (60, 28), 0, 0, 180, (75, 55, 45), -1)
    # braços e mãos gesticulando
    for side, ph in ((-1, 0.0), (1, 1.7)):
        sx, sy = cx + side * 220, 600
        hx = int(cx + side * (120 + 90 * np.sin(2.7 * t + ph)) - 120)
        hy2 = int(820 + 70 * np.sin(3.3 * t + ph))
        cv2.line(frame, (sx, sy), (hx, hy2), suit, 70)
        cv2.circle(frame, (hx, hy2), 38, (186, 150, 126), -1)


def blend(frame: np.ndarray, rgb: np.ndarray, alpha: np.ndarray, x: int, y: int, k: float) -> None:
    h, w = rgb.shape[:2]
    roi = frame[y:y + h, x:x + w].astype(np.float32)
    a = alpha * k
    frame[y:y + h, x:x + w] = (roi * (1 - a) + rgb * a).astype(np.uint8)


def vinheta_frame(k: int, n: int, final: bool) -> np.ndarray:
    p = k / max(n - 1, 1)
    base = np.array([26, 22, 60] if final else [12, 30, 70], np.uint8)
    fr = np.empty((H, W, 3), np.uint8)
    fr[:] = base
    r = int(80 + 900 * p)
    cv2.circle(fr, (W // 2, H // 2), r, (240, 160, 40) if not final else (120, 200, 240), 18)
    cv2.circle(fr, (W // 2, H // 2), max(r // 2, 10), (255, 255, 255), 6)
    a = min(1.0, max(0.0, (p - 0.2) * 3))
    txt = "FIM DA AULA" if final else "NÚCLEO DE VÍDEO"
    font = cv2.FONT_HERSHEY_SIMPLEX
    tw = cv2.getTextSize(txt, font, 3, 8)[0][0]
    over = fr.copy()
    cv2.putText(over, txt, ((W - tw) // 2, H // 2 + 40), font, 3, (255, 255, 255), 8, cv2.LINE_AA)
    return cv2.addWeighted(over, a, fr, 1 - a, 0)


# ------------------------------------------------------------------ áudio

rng = np.random.default_rng(7)


def speech(seconds: float, level_db: float = -20.0) -> np.ndarray:
    n = int(seconds * SR)
    t = np.arange(n) / SR
    noise = rng.standard_normal(n).astype(np.float32)
    noise = np.convolve(noise, np.ones(6) / 6, mode="same")
    voice = sum(np.sin(2 * np.pi * f * t + rng.uniform(0, 6)) / (i + 1) for i, f in enumerate((140, 280, 420, 560, 980)))
    carrier = 0.6 * noise + 0.4 * voice.astype(np.float32)
    # frases de 2–4 s com pausas de 0,3–0,7 s; sílabas a ~5 Hz
    env = np.zeros(n, np.float32)
    pos = 0.0
    while pos < seconds:
        ln = rng.uniform(2.0, 4.0)
        a, b = int(pos * SR), int(min(pos + ln, seconds) * SR)
        tt = np.arange(b - a) / SR
        env[a:b] = (0.45 + 0.55 * np.abs(np.sin(2 * np.pi * rng.uniform(2.2, 2.8) * tt))) * \
                   np.clip(tt / 0.05, 0, 1) * np.clip((tt[-1] - tt) / 0.08, 0, 1)
        pos += ln + rng.uniform(0.3, 0.7)
    sig = carrier * env
    rms = np.sqrt(np.mean(sig[env > 0.1] ** 2))
    return (sig / rms * 10 ** (level_db / 20)).astype(np.float32)


def room_tone(n: int, level_db: float = -60.0) -> np.ndarray:
    x = rng.standard_normal(n).astype(np.float32)
    x = np.convolve(x, np.ones(20) / 20, mode="same")
    return (x / np.sqrt(np.mean(x ** 2)) * 10 ** (level_db / 20)).astype(np.float32)


def vinheta_audio(n: int) -> np.ndarray:
    t = np.arange(n) / SR
    s = sum(np.sin(2 * np.pi * f * t) for f in (220, 277.2, 329.6, 440))
    fade = np.clip(t / 0.3, 0, 1) * np.clip((t[-1] - t) / 0.5, 0, 1)
    s = s * fade
    return (s / np.sqrt(np.mean(s ** 2)) * 10 ** (-18 / 20)).astype(np.float32)


# ------------------------------------------------------------------ montagem

def _ffmpeg() -> str:
    """FFmpeg do app (pasta bin/) ou o do sistema."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from revisor import media
    return media.ffmpeg()


def _vcodec() -> list[str]:
    """H.264 (libx264) como as aulas reais; sem libx264 (FFmpeg do app no Mac), MPEG-4 de alta qualidade."""
    from revisor import media
    if "libx264" in media._encoders():
        return ["-c:v", "libx264", "-preset", "veryfast", "-profile:v", "high",
                "-b:v", "6M", "-maxrate", "10M", "-bufsize", "12M"]
    return ["-c:v", "mpeg4", "-q:v", "2"]


def encode(path: Path, frames_iter, n_frames: int, audio: np.ndarray) -> None:
    with tempfile.NamedTemporaryFile(suffix=".f32", delete=False) as af:
        st = np.repeat(audio[:, None], 2, axis=1).astype("<f4")
        af.write(st.tobytes())
        apath = af.name
    cmd = [_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", "30000/1001", "-i", "-",
           "-f", "f32le", "-ar", str(SR), "-ac", "2", "-i", apath,
           "-map", "0:v", "-map", "1:a",
           "-vf", "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p",
           *_vcodec(), "-g", "60",
           "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv",
           "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(path)]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    k = 0
    for fr in frames_iter:
        p.stdin.write(fr.tobytes())
        k += 1
    p.stdin.close()
    if p.wait() != 0:
        raise SystemExit(f"ffmpeg falhou em {path}")
    Path(apath).unlink()
    assert k == n_frames, (k, n_frames)


def make_vinhetas() -> None:
    for final, name in ((False, "vinheta_inicio.mp4"), (True, "vinheta_final.mp4")):
        n = VIN_FRAMES
        encode(OUT / name, (vinheta_frame(k, n, final) for k in range(n)), n,
               vinheta_audio(int(round(s_of(n) * SR))))


# Trajetória real do slide (medida nas aulas do núcleo, transição de 12f do
# Premiere): fração da altura que falta andar (entrada) ou já andou (saída)
ENTRY_REAL = [0.863, 0.552, 0.324, 0.196, 0.117, 0.065, 0.031, 0.011, 0.002]
EXIT_REAL = [0.006, 0.020, 0.046, 0.089, 0.156, 0.259, 0.452, 0.793]
EXIT_FAST = [0.10, 0.45, 0.85]          # errado: rápido demais


def slide_offset(t: float, f_rel: int, t_in: float, t_out: float, mode_in: str, mode_out: str):
    """Deslocamento vertical do slide (px; negativo = acima) ou None = câmera.

    mode_in: "desce" (vem de cima, certo), "sobe" (vem de baixo), "corte".
    mode_out: "sobe" (vai para cima, certo), "desce", "rapido" (sobe rápido), "corte".
    """
    fi, fo = f_of(t_in), f_of(t_out)
    if f_rel < fi:
        return None
    if f_rel < fo:
        k = f_rel - fi
        if mode_in == "corte" or k >= len(ENTRY_REAL):
            return 0
        frac = ENTRY_REAL[k]
        return int(round(-H * frac)) if mode_in == "desce" else int(round(H * frac))
    k = f_rel - fo
    seq = EXIT_FAST if mode_out == "rapido" else EXIT_REAL
    if mode_out == "corte" or k >= len(seq):
        return None
    frac = seq[k]
    return int(round(H * frac)) if mode_out == "desce" else int(round(-H * frac))


def overlay_slide(cam: np.ndarray, slide: np.ndarray, off: int) -> np.ndarray:
    if off == 0:
        return slide.copy()
    out = cam.copy()
    if off < 0:
        out[:H + off] = slide[-off:]
    else:
        out[off:] = slide[:H - off]
    return out


def make_lesson(name: str, with_errors: bool) -> None:
    content_frames = f_of(110.0)
    end_vin = 66 if with_errors else VIN_FRAMES  # vinheta final cortada no A
    total = VIN_FRAMES + content_frames + end_vin
    c0 = VIN_FRAMES  # primeiro frame do conteúdo

    bg = make_background()
    slide = make_slide()
    t1 = text_layer(["BPC/LOAS"], 96)
    t2 = text_layer(["Bolsa Família"], 96)
    t3 = text_layer(["Previdênsia Social" if with_errors else "Previdência Social"], 72)
    # tarja de nome (etapa 2): A tem texto genérico, B tem o nome certo
    tag_name = "Nome do Professor" if with_errors else "Maria Clara Souza"
    t_tag = text_layer([tag_name], 60)
    t_tag_box = np.zeros((t_tag[0].shape[0] + 20, t_tag[0].shape[1] + 60, 3), np.uint8)
    t_tag_box[:] = (20, 60, 110)
    t_tag_a = np.ones(t_tag_box.shape[:2] + (1,), np.float32)
    t_tag_box[10:10 + t_tag[0].shape[0], 30:30 + t_tag[0].shape[1]] = (
        t_tag_box[10:10 + t_tag[0].shape[0], 30:30 + t_tag[0].shape[1]] * (1 - t_tag[1]) + t_tag[0] * t_tag[1]).astype(np.uint8)
    # termos em inglês e latim (não podem virar aviso) e um erro de acento no A
    t4 = text_layer(["Habeas corpus e machine learning",
                     "Contribuição previdenciaria" if with_errors else "Contribuição previdenciária"], 56)
    noise = [rng.integers(0, 5, (H, W, 3), dtype=np.uint8) for _ in range(6)]
    fade = 12

    def k_in(f, start):
        return float(np.clip((f - start + 1) / fade, 0, 1))

    ev = []  # gabarito

    def add(kind, sec, **kw):
        ev.append({"kind": kind, "frame": c0 + f_of(sec), **kw})

    # slides em tela cheia: (entra, sai, modo de entrada, modo de saída)
    if with_errors:
        slides = [(40.0, 50.0, "desce", "desce"),      # saída para baixo (errado)
                  (100.0, 106.0, "corte", "rapido")]   # entrada seca e saída rápida (errado)
    else:
        slides = [(40.0, 50.0, "desce", "sobe"), (100.0, 106.0, "desce", "sobe")]

    add("cut", 8.0, note="aberto → close")
    add("cut", 20.0, note="close → aberto")
    add("text_in", 24.0, group="lista1", region=[200, 160, 700, 140], text="BPC/LOAS")
    add("text_in", 27.0, group="lista1", region=[200, 290, 760, 140], text="Bolsa Família")
    add("text_out", 34.0, region=[200, 160, 760, 270])
    add("slide_in", 40.0)
    add("slide_out", 50.0)
    add("slide_in", 100.0)
    add("slide_out", 106.0)
    add("text_in", 70.0, region=[140, 820, 820, 110],
        text="Previdênsia Social" if with_errors else "Previdência Social",
        spelling_error="Previdênsia" if with_errors else None)
    add("text_out", 80.0, region=[140, 820, 820, 110])
    add("cut", 85.0, note="corte seco no mesmo enquadramento")
    # a tarja entra no começo, logo depois da vinheta: a etapa 1 não a vê como
    # "texto que entrou" (igual nas aulas reais); quem acha é a varredura da tarja
    add("text_in", 2.0, region=[120, 880, 700, 100], text=tag_name,
        name_tag="generico" if with_errors else "ok", optional=True)
    add("text_out", 6.0, region=[120, 880, 700, 100], optional=True)
    add("text_in", 88.0, region=[140, 120, 1000, 160], text="Habeas corpus e machine learning / Contribuição",
        spelling_error="previdenciaria" if with_errors else None)
    add("text_out", 96.0, region=[140, 120, 1000, 160])
    if with_errors:
        add("color_jump", 58.0, note="balanço de branco muda de repente")
        add("color_jump", 63.0, note="volta ao normal")
        add("color_mismatch_cut", 85.0, note="mesmo enquadramento, cor diferente")
        add("audio_spike", 45.0, end=45.25)
        add("audio_gap", 66.0, end=67.2)
        add("audio_clip", 92.0, end=92.3)
        add("audio_noise_change", 95.0)
        add("freeze", 9.0, end=19.0, note="câmera travou 10 s no meio da fala")
        add("slide_transition", 50.0, note="slide saiu descendo")
        add("slide_transition", 100.0, note="slide entrou com corte seco")
        add("slide_transition", 106.0, note="slide saiu rápido demais")
        ev.append({"kind": "vinheta_final_cortada", "frame": c0 + content_frames,
                   "note": f"{end_vin} de {VIN_FRAMES} frames"})

    def frames():
        for f in range(total):
            if f < c0:
                yield vinheta_frame(f, VIN_FRAMES, False)
                continue
            if f >= c0 + content_frames:
                yield vinheta_frame(f - c0 - content_frames, VIN_FRAMES, True)
                continue
            t = s_of(f - c0)
            frozen = with_errors and f_of(9.0) <= f - c0 < f_of(19.0)
            if frozen:          # câmera travada: repete o frame de 9,0 s, inclusive o ruído
                t = s_of(f_of(9.0))
            off = None
            for (ti, to, mi, mo) in slides:
                o = slide_offset(t, f - c0, ti, to, mi, mo)
                if o is not None and f - c0 < f_of(to) + 20:
                    off = o
                    break
            if off == 0:
                fr = slide.copy()
            else:
                fr = bg.copy()
                draw_person(fr, t)
                if f_of(8.0) <= f - c0 < f_of(20.0):  # close-up
                    fr = cv2.resize(fr[60:780, 620:1900], (W, H), interpolation=cv2.INTER_LINEAR)
                if f_of(24.0) <= f - c0 < f_of(34.0) + fade:
                    out_k = 1 - k_in(f - c0, f_of(34.0))
                    blend(fr, *t1, 200, 160, min(k_in(f - c0, f_of(24.0)), out_k))
                    if f - c0 >= f_of(27.0):
                        blend(fr, *t2, 200, 290, min(k_in(f - c0, f_of(27.0)), out_k))
                if f_of(2.0) <= f - c0 < f_of(6.0) + fade:
                    blend(fr, t_tag_box, t_tag_a, 120, 880, min(k_in(f - c0, f_of(2.0)), 1 - k_in(f - c0, f_of(6.0))))
                if f_of(88.0) <= f - c0 < f_of(96.0) + fade:
                    blend(fr, *t4, 140, 120, min(k_in(f - c0, f_of(88.0)), 1 - k_in(f - c0, f_of(96.0))))
                if f_of(70.0) <= f - c0 < f_of(80.0) + fade:
                    blend(fr, *t3, 140, 820, min(k_in(f - c0, f_of(70.0)), 1 - k_in(f - c0, f_of(80.0))))
                if with_errors and f_of(58.0) <= f - c0 < f_of(63.0):
                    fr = cv2.merge([cv2.multiply(fr[..., 0], 0.92), cv2.multiply(fr[..., 1], 1.08),
                                    cv2.multiply(fr[..., 2], 0.86)])
                if with_errors and f - c0 >= f_of(85.0):
                    fr = cv2.merge([cv2.multiply(fr[..., 0], 1.07), fr[..., 1], cv2.multiply(fr[..., 2], 0.93)])
                if off is not None:
                    fr = overlay_slide(fr, slide, off)
            nf = (c0 + f_of(9.0)) if frozen else f
            fr = cv2.add(fr, noise[nf % 6])
            fr = cv2.subtract(fr, noise[(nf + 3) % 6])
            yield fr

    # ---- áudio
    n_total = int(round(s_of(total) * SR))
    a_vin = vinheta_audio(int(round(s_of(VIN_FRAMES) * SR)))
    content_n = int(round(s_of(content_frames) * SR))
    body = speech(content_n / SR) + room_tone(content_n)

    def idx(sec):
        return int(sec * SR)

    if with_errors:
        # pico: estalo de 0,25 s perto de 0 dBFS
        a, b = idx(45.0), idx(45.25)
        body[a:b] += (rng.standard_normal(b - a) * 0.35).astype(np.float32)
        # buraco: silêncio digital no meio da fala
        body[idx(66.0):idx(67.2)] = 0.0
        # clipping
        a, b = idx(92.0), idx(92.3)
        body[a:b] = np.clip(body[a:b] * 14, -1.0, 1.0)
        # ruído de fundo sobe
        a = idx(95.0)
        tt = np.arange(content_n - a) / SR
        body[a:] += (0.004 * np.sin(2 * np.pi * 60 * tt) + room_tone(content_n - a, -44.0)).astype(np.float32)
    else:
        pass
    audio = np.zeros(n_total, np.float32)
    audio[:len(a_vin)] = a_vin
    s0 = len(a_vin)
    audio[s0:s0 + content_n] = body[: n_total - s0]
    e0 = s0 + content_n
    end_audio = vinheta_audio(int(round(s_of(VIN_FRAMES) * SR)))[: n_total - e0]
    audio[e0:e0 + len(end_audio)] = end_audio

    encode(OUT / f"{name}.mp4", frames(), total, audio)
    gab = {"video": f"{name}.mp4", "fps": "30000/1001", "total_frames": total, "name_expected": "Maria Clara Souza",
           "content_first_frame": c0, "content_last_frame": c0 + content_frames - 1,
           "end_vinheta_frames": end_vin, "events": sorted(ev, key=lambda e: e["frame"])}
    (OUT / f"{name}.gabarito.json").write_text(json.dumps(gab, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    which = sys.argv[1:] or ["vin", "A", "B"]
    if "vin" in which:
        make_vinhetas()
    if "A" in which:
        make_lesson("aula_A_com_erros", True)
    if "B" in which:
        make_lesson("aula_B_limpa", False)
    print("ok")
