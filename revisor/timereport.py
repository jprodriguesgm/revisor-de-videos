"""Relatório de tempo (bruto × editado) feito pelo próprio app.

Faz o mesmo que o script "Calculo de tempo.command" do núcleo, e grava o txt IGUAL (mesmo nome,
mesmo texto, mesmas contas), porque ele sobe para a planilha do Google que confere o tempo
produzido por disciplina:

- Brutos: todos os vídeos da pasta e das subpastas. Editados: só os que estão direto na pasta.
- Arquivo cujo nome (sem a extensão) termina em -D ou -E fica de fora (divisão feita pelo
  Estúdio Encoder: só o arquivo sem sufixo é a gravação).
- Duração lida do cabeçalho do vídeo (bloco "mvhd"; "mehd" no MP4 fragmentado do OBS), como o
  script. No Mac tenta antes o Spotlight (mdls), que é o primeiro jeito do script. Se nada disso
  der, o FFprobe que vai dentro do app (o script usava o afinfo do Mac nesse caso).
- Contas do script: cada linha arredonda o próprio tempo; o total soma os valores com casas
  decimais (por isso a soma das linhas pode diferir do total em ~1 s); aproveitamento com uma casa
  e vírgula; descartado = bruto − editado (nunca negativo).
- Salva "Relatorio_tempo_AAAA-MM-DD_HHMM.txt" na pasta dos editados (se não der: Mesa, depois
  Documentos), em UTF-8 com fim de linha "\\n", como o script.

Funciona igual no Mac e no Windows (o .command só rodava no Mac).
"""
from __future__ import annotations

import os
import struct
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import media

# extensões que o script soma (find -iname)
VIDEO_EXT = (".mp4", ".mov", ".m4v", ".mxf", ".mts", ".avi", ".mkv")
REPORT_PREFIX = "Relatorio_tempo_"


class TimeReportError(Exception):
    pass


# ---------------------------------------------------------------- duração do arquivo

def _atoms(f, start: int, end: int):
    """Percorre os blocos (átomos) de um MP4/MOV entre start e end: (tipo, posição, tamanho, cabeçalho)."""
    pos, guard = start, 0
    while pos < end and guard < 500:
        guard += 1
        f.seek(pos)
        head = f.read(16)
        if len(head) < 8:
            return
        size, kind = struct.unpack(">I4s", head[:8])
        hdr = 8
        if size == 1:
            if len(head) < 16:
                return
            size = struct.unpack(">Q", head[8:16])[0]
            hdr = 16
        elif size == 0:
            size = end - pos
        if size < 8:
            return
        yield kind, pos, size, hdr
        pos += size


def _find(f, start: int, end: int, kind: bytes):
    for k, pos, size, hdr in _atoms(f, start, end):
        if k == kind:
            return pos, size, hdr
    return None


def _mvhd_mehd(path: Path) -> tuple[float | None, float | None]:
    """(duração do mvhd, duração do mehd) em segundos; None quando não há ou é zero."""
    try:
        total = path.stat().st_size
        with open(path, "rb") as f:
            moov = _find(f, 0, total, b"moov")
            if not moov:
                return None, None
            m_ini, m_end = moov[0] + moov[2], moov[0] + moov[1]
            mv = _find(f, m_ini, m_end, b"mvhd")
            if not mv:
                return None, None
            f.seek(mv[0] + 8)
            ver = f.read(1)
            if ver == b"\x01":
                f.seek(mv[0] + 28)
                ts, dur = struct.unpack(">IQ", f.read(12))
            else:
                f.seek(mv[0] + 20)
                ts, dur = struct.unpack(">II", f.read(8))
            if ts <= 0:
                return None, None
            mvhd = round(dur / ts, 3) if dur > 0 else None
            mehd = None
            mvex = _find(f, m_ini, m_end, b"mvex")
            if mvex:
                me = _find(f, mvex[0] + mvex[2], mvex[0] + mvex[1], b"mehd")
                if me:
                    f.seek(me[0] + 8)
                    mver = f.read(1)
                    f.seek(me[0] + 12)
                    raw = f.read(8 if mver == b"\x01" else 4)
                    fd = struct.unpack(">Q" if mver == b"\x01" else ">I", raw)[0]
                    if fd > 0:
                        mehd = round(fd / ts, 3)
            return mvhd, mehd
    except (OSError, struct.error):
        return None, None


def _spotlight(path: Path) -> float | None:
    """Mac: a duração que o Finder mostra (Spotlight). Desligado em muitos discos externos."""
    if sys.platform != "darwin":
        return None
    try:
        out = subprocess.run(["mdls", "-raw", "-name", "kMDItemDurationSeconds", str(path)],
                             capture_output=True, text=True, timeout=10).stdout.strip()
        v = float(out)
        return v if v > 0 else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def _ffprobe(path: Path) -> float | None:
    try:
        v = media.probe(path).duration
        return round(v, 3) if v > 0 else None
    except (media.MediaError, OSError, ValueError, KeyError, subprocess.SubprocessError):
        return None


def duration_of(path: str | os.PathLike) -> float | None:
    """Duração em segundos, na ordem do script; None = não lido (fica fora da soma)."""
    p = Path(path)
    v = _spotlight(p)
    if v:
        return v
    if p.suffix.lower() in (".mp4", ".mov", ".m4v"):
        mvhd, mehd = _mvhd_mehd(p)
        if mvhd:
            return mvhd
        if mehd:
            return mehd
    return _ffprobe(p)


# ---------------------------------------------------------------- listas

def is_split(name: str) -> bool:
    """Arquivo dividido pelo Estúdio Encoder (termina em -D ou -E antes da extensão)."""
    base = name.rsplit(".", 1)[0] if "." in name else name
    return base[-2:].lower() in ("-d", "-e")


def list_videos(folder: str | os.PathLike, recursive: bool) -> list[Path]:
    """Vídeos da pasta como o script lista: sem arquivos ocultos, em ordem do caminho."""
    folder = Path(folder)
    out: list[Path] = []
    if recursive:
        for root, _dirs, files in os.walk(folder):
            for fn in files:
                if not fn.startswith(".") and fn.lower().endswith(VIDEO_EXT):
                    out.append(Path(root) / fn)
    else:
        for p in folder.iterdir():
            if p.is_file() and not p.name.startswith(".") and p.name.lower().endswith(VIDEO_EXT):
                out.append(p)
    return sorted(out, key=lambda p: str(p))


# ---------------------------------------------------------------- contas iguais às do script

def _awk_num(x: float) -> float:
    """O awk do script guarda a soma como texto ("print a + b" usa %.6g a cada passo)."""
    if x == int(x) and abs(x) < 1e16:
        return float(int(x))
    return float("%.6g" % x)


def hms(seconds: float) -> str:
    """formatar() do script: arredonda (int(s + 0,5)) e escreve HH:MM:SS."""
    s = int(seconds + 0.5)
    return "%02d:%02d:%02d" % (s // 3600, (s % 3600) // 60, s % 60)


@dataclass
class Side:
    total: float = 0.0
    lines: list[tuple[float, str]] = field(default_factory=list)   # (segundos, nome)
    failed: list[str] = field(default_factory=list)
    ignored: int = 0

    def add_folder(self, folder: Path, recursive: bool, progress=None) -> None:
        for p in list_videos(folder, recursive):
            if is_split(p.name):
                self.ignored += 1
                continue
            if progress:
                progress(p.name)
            d = duration_of(p)
            if not d:
                self.failed.append(p.name)
                continue
            self.total = _awk_num(self.total + d)
            self.lines.append((d, p.name))


@dataclass
class Result:
    text: str
    filename: str
    raw: Side
    edited: Side
    project: str

    def summary(self) -> dict:
        return {"raw_files": len(self.raw.lines), "edited_files": len(self.edited.lines),
                "raw_failed": self.raw.failed, "edited_failed": self.edited.failed,
                "ignored_raw": self.raw.ignored, "ignored_edited": self.edited.ignored}


def build(raw_folder: str | os.PathLike, edited_folder: str | os.PathLike, now: datetime | None = None,
          progress=None) -> Result:
    raw_folder, edited_folder = Path(raw_folder), Path(edited_folder)
    if not raw_folder.is_dir():
        raise TimeReportError("Pasta dos brutos não encontrada.")
    if not edited_folder.is_dir():
        raise TimeReportError("Pasta dos editados não encontrada.")
    if raw_folder.resolve() == edited_folder.resolve():
        raise TimeReportError("A pasta dos brutos e a dos editados são a mesma. Escolha as duas pastas certas.")
    now = now or datetime.now()
    raw, ed = Side(), Side()
    raw.add_folder(raw_folder, recursive=True, progress=progress)        # brutos: inclui subpastas
    ed.add_folder(edited_folder, recursive=False, progress=progress)     # editados: só a pasta
    if not raw.lines or not ed.lines:
        msg = (f"Não consegui ler vídeos em uma das pastas (brutos lidos: {len(raw.lines)}, "
               f"editados lidos: {len(ed.lines)}).")
        if raw.failed or ed.failed:
            msg += " Não lidos: " + ", ".join(raw.failed + ed.failed) + "."
        raise TimeReportError(msg)
    b, n = raw.total, ed.total
    pct = ("%.1f" % ((n / b) * 100)).replace(".", ",") if b > 0 else "0"
    discard = _awk_num(max(0.0, b - n))
    lst = lambda side: "".join(f"  {hms(s)}  {name}\n" for s, name in side.lines)
    text = (
        "RELATÓRIO DE TEMPO DE VÍDEO\n"
        f"Projeto (pasta editados): {edited_folder.name}\n"
        f"Data: {now.strftime('%d/%m/%Y %H:%M')}\n"
        "\n"
        f"BRUTOS ({len(raw.lines)} arquivos)\n"
        f"{lst(raw)}\n"
        f"EDITADOS ({len(ed.lines)} arquivos)\n"
        f"{lst(ed)}\n"
        "----------------------------------------------\n"
        f"TEMPO DE GRAVAÇÃO (bruto): {hms(b)}\n"
        f"TEMPO LÍQUIDO (editado):   {hms(n)}\n"
        f"APROVEITAMENTO:            {pct}%\n"
        f"TEMPO DESCARTADO:          {hms(discard)}"
    )
    if raw.ignored or ed.ignored:
        text += f"\n\nIgnorados por terminarem em -D ou -E: brutos {raw.ignored}, editados {ed.ignored}"
    if raw.failed or ed.failed:
        text += "\n\nATENÇÃO - arquivos não lidos (NÃO entraram na soma):\n" + \
                "".join(f"  - {x}\n" for x in raw.failed + ed.failed)
    text += "\n"                                   # printf '%s\n'
    return Result(text=text, filename=f"{REPORT_PREFIX}{now.strftime('%Y-%m-%d_%H%M')}.txt",
                  raw=raw, edited=ed, project=edited_folder.name)


def save(res: Result, edited_folder: str | os.PathLike) -> Path:
    """Grava na pasta dos editados; se não der, na Mesa e depois em Documentos (como o script)."""
    home = Path.home()
    for d in (Path(edited_folder), home / "Desktop", home / "Documents"):
        try:
            if not d.is_dir():
                continue
            p = d / res.filename
            with open(p, "w", encoding="utf-8", newline="\n") as f:
                f.write(res.text)
            if p.stat().st_size > 0:
                return p
        except OSError:
            continue
    raise TimeReportError("Não consegui salvar o relatório em nenhuma pasta (editados, Mesa ou Documentos).")


def make(raw_folder, edited_folder, now: datetime | None = None, progress=None) -> tuple[Result, Path]:
    res = build(raw_folder, edited_folder, now=now, progress=progress)
    return res, save(res, edited_folder)
