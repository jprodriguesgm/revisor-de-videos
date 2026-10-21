"""Ajudas dos testes: FFmpeg e nomes de pasta que funcionam no Mac, no Windows e no Linux."""
import os

from revisor import media

# "Carlos 21:09" é o nome real das pastas no Mac; no Windows ":" não pode em nome de pasta
PROJ = "Ana 19:10" if os.name != "nt" else "Ana 19-10"


def ffmpeg() -> str:
    return media.ffmpeg()


def video_codec(quality: bool = False) -> list[str]:
    """libx264 quando houver; senão MPEG-4 (o FFmpeg do app no Mac não traz libx264)."""
    if "libx264" in media._encoders():
        return ["-c:v", "libx264"] + (["-crf", "8"] if quality else [])
    return ["-c:v", "mpeg4"] + (["-qmin", "1", "-qmax", "1", "-q:v", "1"] if quality else ["-q:v", "2"])
