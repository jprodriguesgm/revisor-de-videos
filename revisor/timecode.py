"""Conversão de tempo para os formatos usados no app.

Tudo dentro do app é guardado como número de frame (int) + taxa de frames
(fração). Os textos mostrados ao usuário são gerados aqui, para que copiar,
exportar e SRT usem exatamente a mesma regra.

Formatos:
- "seconds":  00:00:44           (tempo real, arredondado para baixo)
- "ndf":      00:00:44:12        (timecode sem drop frame)
- "df":       00:00:44;12        (timecode drop frame, só para 29,97/59,94)
- SRT:        00:00:44,040       (tempo real em milissegundos)
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

NTSC_2997 = Fraction(30000, 1001)


@dataclass(frozen=True)
class Rate:
    fps: Fraction

    @property
    def nominal(self) -> int:
        """Frames por segundo "de contagem" (30 para 29,97)."""
        return int(round(float(self.fps)))

    @property
    def is_drop_capable(self) -> bool:
        return self.nominal in (30, 60) and self.fps.denominator == 1001

    def frame_at(self, seconds: float) -> int:
        """Frame que está na tela no instante `seconds` (tempo real)."""
        # pequeno epsilon para que 1001/30000*N vire exatamente N
        return int(seconds * self.fps + Fraction(1, 10_000))

    def seconds_of(self, frame: int) -> float:
        return float(Fraction(frame) / self.fps)


def parse_rate(text: str) -> Rate:
    """Aceita '30000/1001', '29.97', '25'."""
    text = text.strip()
    if "/" in text:
        n, d = text.split("/", 1)
        fr = Fraction(int(n), int(d))
    else:
        f = float(text)
        if abs(f - 29.97) < 0.01:
            fr = NTSC_2997
        elif abs(f - 59.94) < 0.01:
            fr = Fraction(60000, 1001)
        elif abs(f - 23.976) < 0.01:
            fr = Fraction(24000, 1001)
        else:
            fr = Fraction(f).limit_denominator(1001)
    return Rate(fr)


def fmt_seconds(rate: Rate, frame: int) -> str:
    # usa o meio do frame: o frame 107892 (início em 3599,996 s) é mostrado como 01:00:00,
    # igual ao timecode drop frame do Premiere
    s = int((Fraction(frame) + Fraction(1, 2)) / rate.fps)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def fmt_ndf(rate: Rate, frame: int) -> str:
    n = rate.nominal
    ff = frame % n
    total_s = frame // n
    return f"{total_s // 3600:02d}:{total_s % 3600 // 60:02d}:{total_s % 60:02d}:{ff:02d}"


def fmt_df(rate: Rate, frame: int) -> str:
    """Drop frame (SMPTE): pula os números 00 e 01 de cada minuto, exceto a cada 10 minutos."""
    if not rate.is_drop_capable:
        return fmt_ndf(rate, frame)
    n = rate.nominal
    drop = 2 if n == 30 else 4
    frames_per_10min = n * 600 - drop * 9
    frames_per_min = n * 60 - drop
    d, m = divmod(frame, frames_per_10min)
    if m > drop:
        frame += drop * 9 * d + drop * ((m - drop) // frames_per_min)
    else:
        frame += drop * 9 * d
    ff = frame % n
    s = frame // n
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d};{ff:02d}"


def fmt_srt(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def fmt(rate: Rate, frame: int, style: str = "seconds") -> str:
    if style == "seconds":
        return fmt_seconds(rate, frame)
    if style == "ndf":
        return fmt_ndf(rate, frame)
    if style == "df":
        return fmt_df(rate, frame)
    raise ValueError(f"formato desconhecido: {style}")


def fmt_duration(seconds: float) -> str:
    s = int(round(seconds))
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
