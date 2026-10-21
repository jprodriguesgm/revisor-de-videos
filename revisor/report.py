"""Leitura do relatório de tempo (txt gerado pelo "Calculo de tempo").

O app não recalcula nada: usa os números que já vêm no txt.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

_TIME = re.compile(r"^\s*(\d{1,2}):(\d{2}):(\d{2})\s+(.+?)\s*$")
_IGNORED = re.compile(r"brutos\s+(\d+).*?editados\s+(\d+)", re.I)
# nome que o OBS dá ao bruto: "2026-09-18 10-41-13.mp4" (às vezes com "-002")
_RAW_NAME = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}-\d{2}-\d{2}(-\d+)?\.\w+$")


def hms_to_s(text: str) -> int:
    h, m, s = (int(x) for x in text.strip().split(":"))
    return h * 3600 + m * 60 + s


@dataclass
class TimeReport:
    path: str
    project: str = ""
    date: datetime | None = None
    raw: list[tuple[int, str]] = field(default_factory=list)       # (segundos, arquivo)
    edited: list[tuple[int, str]] = field(default_factory=list)
    total_raw_s: int | None = None
    total_edited_s: int | None = None
    usage_pct: float | None = None
    discarded_s: int | None = None
    ignored_raw: int | None = None       # "Ignorados por terminarem em -D ou -E"
    ignored_edited: int | None = None

    def to_dict(self):
        return {
            "path": self.path, "file": Path(self.path).name, "project": self.project,
            "date": self.date.strftime("%Y-%m-%d %H:%M") if self.date else None,
            "raw": [{"seconds": s, "file": f} for s, f in self.raw],
            "edited": [{"seconds": s, "file": f} for s, f in self.edited],
            "total_raw_s": self.total_raw_s, "total_edited_s": self.total_edited_s,
            "usage_pct": self.usage_pct, "discarded_s": self.discarded_s,
            "ignored_raw": self.ignored_raw, "ignored_edited": self.ignored_edited,
        }


def parse(path: str | Path) -> TimeReport:
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    rep = TimeReport(path=str(path))
    section = None
    for line in text.splitlines():
        s = line.strip()
        up = s.upper()
        if up.startswith("PROJETO"):
            rep.project = s.split(":", 1)[1].strip() if ":" in s else ""
        elif up.startswith("DATA:"):
            try:
                rep.date = datetime.strptime(s.split(":", 1)[1].strip(), "%d/%m/%Y %H:%M")
            except ValueError:
                pass
        elif up.startswith("BRUTOS"):
            section = "raw"
        elif up.startswith("EDITADOS"):
            section = "edited"
        elif up.startswith("TEMPO DE GRAVA"):
            rep.total_raw_s = hms_to_s(s.split(":", 1)[1])
            section = None
        elif up.startswith("TEMPO LÍQUIDO") or up.startswith("TEMPO LIQUIDO"):
            rep.total_edited_s = hms_to_s(s.split(":", 1)[1])
        elif up.startswith("APROVEITAMENTO"):
            v = s.split(":", 1)[1].strip().rstrip("%").replace(",", ".")
            try:
                rep.usage_pct = float(v)
            except ValueError:
                pass
        elif up.startswith("TEMPO DESCARTADO"):
            rep.discarded_s = hms_to_s(s.split(":", 1)[1])
        elif up.startswith("IGNORADOS"):
            m = _IGNORED.search(s)
            if m:
                rep.ignored_raw, rep.ignored_edited = int(m.group(1)), int(m.group(2))
            section = None
        elif up.startswith("---"):
            section = None
        elif section:
            m = _TIME.match(line)
            if m:
                secs = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
                (rep.raw if section == "raw" else rep.edited).append((secs, m.group(4)))
    return rep


def find_in_folder(folder: str | Path) -> Path | None:
    """O relatório fica na mesma pasta dos vídeos; pega o mais recente."""
    folder = Path(folder)
    cands = sorted(folder.glob("Relatorio_tempo*.txt")) or sorted(
        p for p in folder.glob("*.txt") if "relat" in p.name.lower())
    return cands[-1] if cands else None


# ------------------------------------------------------------------ casar com os vídeos

def norm_name(name: str) -> str:
    """Nome comparável: sem extensão, acento, maiúscula, espaço duplo e '-' no fim.

    Nas pastas reais o mesmo vídeo aparece como "… Parte 1-.mp4" no txt e
    "… Parte 1.mp4" na pasta (renomeado depois), e com espaço duplo ("04  Modalidades").
    """
    n = unicodedata.normalize("NFKD", name)
    n = "".join(c for c in n if not unicodedata.combining(c)).lower()
    n = re.sub(r"\.(mp4|mov|m4v)$", "", n.strip())
    n = re.sub(r"\s+", " ", n)
    return n.strip(" -_.")


def looks_raw(name: str) -> bool:
    return bool(_RAW_NAME.match(name.strip()))


@dataclass
class Match:
    video: str
    entry: tuple[int, str] | None          # (segundos, nome no txt)
    by: str = ""                           # "nome" | "duração" | ""


def match_videos(rep: TimeReport, videos: list[tuple[str, float]]) -> tuple[list[Match], list[str]]:
    """Liga cada vídeo da pasta à linha do txt. Devolve (casamentos, avisos).

    Primeiro pelo nome (tolerante); se não achar, pela duração (±1 s) quando só
    uma linha bate. Avisa: vídeo que não está no txt, linha do txt sem vídeo,
    e bruto listado entre os editados (o txt conta esse tempo como editado).
    """
    left = list(rep.edited)
    out: list[Match] = []
    for name, dur in videos:
        nn = norm_name(name)
        hit = next((e for e in left if norm_name(e[1]) == nn), None)
        by = "nome" if hit else ""
        if hit is None:
            cands = [e for e in left if abs(e[0] - dur) <= 1.0 and not looks_raw(e[1])]
            if len(cands) == 1:
                hit, by = cands[0], "duração"
        if hit is not None:
            left.remove(hit)
        out.append(Match(name, hit, by))
    warns: list[str] = []
    for m in out:
        if m.entry is None:
            warns.append(f"“{m.video}” não está no relatório de tempo.")
        elif m.by == "duração":
            warns.append(f"“{m.video}” está no relatório com outro nome: “{m.entry[1]}”.")
    for secs, name in left:
        if looks_raw(name):
            warns.append(f"O relatório conta “{name}” ({secs // 60}:{secs % 60:02d}) como editado, "
                         f"mas o nome é de bruto.")
        else:
            warns.append(f"“{name}” está no relatório, mas não está na pasta.")
    return out, warns
