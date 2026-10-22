"""Janelas do sistema para escolher pasta ou arquivo (o navegador não dá o caminho).

Mac: AppleScript (osascript). Windows: NENHUMA janela do sistema — só o navegador de pastas do
próprio app (decisão do JP, 22/10: a janela do Windows era aberta pelo PowerShell com comando
codificado, padrão que o antivírus do Windows confunde com vírus; e ela ainda abria atrás do
navegador). Outros: tkinter, se houver. Se nada funcionar, a tela usa o navegador do app.
Devolve o caminho escolhido, None se o usuário cancelar, ou levanta Unsupported.
"""
from __future__ import annotations

import os
import shutil
import string
import subprocess
import sys
from pathlib import Path


class Unsupported(Exception):
    pass


def _osa_quote(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def choose_folder(prompt: str = "Escolha a pasta", start: str | None = None) -> str | None:
    if sys.platform == "darwin":
        script = f'POSIX path of (choose folder with prompt "{_osa_quote(prompt)}"'
        if start and Path(start).is_dir():
            script += f' default location (POSIX file "{_osa_quote(start)}")'
        script += ")"
        return _run_osa(script)
    if os.name == "nt":
        raise Unsupported("Windows: navegador de pastas do app")
    return _tk(lambda fd: fd.askdirectory(title=prompt, initialdir=start or None))


def choose_file(prompt: str = "Escolha o arquivo", start: str | None = None,
                exts: tuple[str, ...] = ("mp4", "mov", "m4v")) -> str | None:
    if sys.platform == "darwin":
        script = f'POSIX path of (choose file with prompt "{_osa_quote(prompt)}"'
        if start and Path(start).is_dir():
            script += f' default location (POSIX file "{_osa_quote(start)}")'
        script += ")"
        return _run_osa(script)
    if os.name == "nt":
        raise Unsupported("Windows: navegador de pastas do app")
    return _tk(lambda fd: fd.askopenfilename(title=prompt, initialdir=start or None,
                                             filetypes=[("Vídeos", " ".join(f"*.{e}" for e in exts)),
                                                        ("Todos", "*")]))


def _run_osa(script: str) -> str | None:
    if not shutil.which("osascript"):
        raise Unsupported()
    # a janela aparece na frente do navegador
    full = f'tell application "System Events" to activate\n{script}'
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if r.returncode != 0:
        if "-128" in r.stderr:          # usuário cancelou
            return None
        r = subprocess.run(["osascript", "-e", full], capture_output=True, text=True)
        if r.returncode != 0:
            if "-128" in r.stderr:
                return None
            raise Unsupported(r.stderr.strip()[:200])
    p = r.stdout.strip()
    return p.rstrip("/") or "/" if p else None


def _tk(fn) -> str | None:
    if not os.environ.get("DISPLAY") and sys.platform not in ("darwin", "win32"):
        raise Unsupported()
    try:
        import tkinter
        from tkinter import filedialog
    except ImportError:
        raise Unsupported()
    try:
        root = tkinter.Tk()
    except Exception:
        raise Unsupported()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        p = fn(filedialog)
    finally:
        root.destroy()
    return p or None


# ------------------------------------------------------------------ navegador de pastas do app

def roots() -> list[dict]:
    """Pontos de partida: pasta do usuário, discos externos (Mac) ou letras de disco (Windows)."""
    out = [{"name": "Pasta do usuário", "path": str(Path.home())}]
    for name, sub in (("Área de Trabalho", "Desktop"), ("Downloads", "Downloads"), ("Vídeos", "Videos"),
                      ("Filmes", "Movies"), ("Documentos", "Documents")):
        q = Path.home() / sub
        if q.is_dir():
            out.append({"name": name, "path": str(q)})
    if sys.platform == "darwin":
        vol = Path("/Volumes")
        if vol.is_dir():
            for p in sorted(vol.iterdir()):
                if p.is_dir() and not p.name.startswith("."):
                    out.append({"name": p.name, "path": str(p)})
        gd = Path.home() / "Library" / "CloudStorage"
        if gd.is_dir():
            for p in sorted(gd.iterdir()):
                if p.is_dir() and p.name.startswith("GoogleDrive"):
                    out.append({"name": "Google Drive", "path": str(p)})
    elif os.name == "nt":
        for letter in string.ascii_uppercase:
            d = f"{letter}:\\"
            if os.path.exists(d):
                out.append({"name": f"Disco {letter}:", "path": d})
    else:
        out.append({"name": "/", "path": "/"})
    return out


def listdir(path: str, video_exts=(".mp4", ".mov", ".m4v")) -> dict:
    p = Path(path).expanduser().resolve()
    if not p.is_dir():
        raise FileNotFoundError(path)
    dirs, videos, files = [], [], []
    try:
        entries = sorted(p.iterdir(), key=lambda q: q.name.lower())
    except PermissionError:
        entries = []
    for q in entries:
        if q.name.startswith("."):
            continue
        try:
            if q.is_dir():
                dirs.append({"name": q.name, "path": str(q)})
            elif q.suffix.lower() in video_exts:
                videos.append({"name": q.name, "path": str(q)})
            else:
                files.append(q.name)
        except OSError:
            continue
    parent = str(p.parent) if p.parent != p else None
    return {"path": str(p), "parent": parent, "dirs": dirs, "videos": videos, "others": len(files)}
