"""Confere a versão mínima do macOS de cada programa/biblioteca dentro do .app.

    python packaging/check_macos_min.py "dist/Revisor de Videos.app" 11.0

Motivo (20/10/2026): o app não abriu no Mac do trabalho do JP. O numpy que o pip escolhe
num Mac 14 é o feito para macOS 14+ (Accelerate); em Mac mais antigo o app nem abre.
Lê o "minos" de cada arquivo Mach-O (otool -l) e falha se algum pedir mais que o limite.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

MAGIC = {b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe", b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca"}


def ver(s: str) -> tuple[int, ...]:
    return tuple(int(x) for x in s.split("."))


def main(app: str, limit: str) -> int:
    worst, bad, n = (0,), [], 0
    for p in Path(app).rglob("*"):
        if p.is_symlink() or not p.is_file():
            continue
        try:
            with open(p, "rb") as fh:
                if fh.read(4) not in MAGIC:
                    continue
        except OSError:
            continue
        n += 1
        out = subprocess.run(["otool", "-l", str(p)], capture_output=True, text=True).stdout
        mins = re.findall(r"minos (\d+(?:\.\d+)*)", out) + re.findall(r"cmd LC_VERSION_MIN_MACOSX\s+cmdsize \d+\s+version (\d+(?:\.\d+)*)", out)
        if not mins:
            continue
        m = max(mins, key=ver)
        worst = max(worst, ver(m))
        if ver(m) > ver(limit):
            bad.append((m, str(p.relative_to(app))))
    print(f"{n} arquivos Mach-O; maior macOS mínimo: {'.'.join(map(str, worst))} (limite {limit})")
    for m, f in sorted(bad, reverse=True)[:40]:
        print(f"  pede macOS {m}: {f}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "11.0"))
