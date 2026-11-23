"""Google Drive opcional (pedido do JP, 23/11/2026): baixar a pasta Saída de um dia direto para a pasta de
revisão, com o nome no padrão ("{data} {professor}") e com as transcrições prontas.

- Vem DESLIGADO. Desligado, o app não usa internet (como sempre foi).
- Usa o rclone que já está no computador (o mesmo do app "Subir no Drive", com a conta da instituição).
  Nada de senha ou chave dentro do Revisor: quem fala com o Google é o rclone.
- Organização no Drive: <pasta das gravações>/<código + professor>/<AAAA MM DD>/Saída (vídeos editados)
  e <...>/<AAAA MM DD>/Transcrições (transcrições do "Subir no Drive").
- O link colado é de uma pasta (Saída ou a pasta do dia). O app acha onde ela fica (o nome do dia e do
  curso) listando as pastas da pasta das gravações uma vez (o resultado fica guardado alguns minutos).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import unicodedata
from pathlib import Path

from . import analyze, transcricao

SUBIR_SUPPORT = Path.home() / "Library" / "Application Support" / "SubirNoDrive"
NAME_DEFAULT = "{data} {professor}"
TOKENS = ("data", "professor", "codigo")
VIDEO_EXT = tuple(sorted(analyze.VIDEO_EXT))
TREE_TTL_S = 600
_NO_WINDOW = 0x08000000 if os.name == "nt" else 0      # CREATE_NO_WINDOW: sem janela preta no Windows


class DriveError(Exception):
    pass


# ------------------------------------------------------------------ achar o rclone

def _subir_files() -> dict:
    """O que o "Subir no Drive" deixou no Mac: rclone (PATH do env.sh), RCLONE_CONFIG, conexão e pasta inicial."""
    out: dict = {}
    env = SUBIR_SUPPORT / "env.sh"
    try:
        for line in env.read_text(encoding="utf-8").splitlines():
            m = re.match(r'\s*export\s+RCLONE_CONFIG="([^"]+)"', line)
            if m:
                out["config"] = m.group(1)
            m = re.match(r'\s*export\s+PATH="([^"]+)"', line)
            if m:
                for d in m.group(1).split(":"):
                    if d and "$" not in d and (Path(d) / "rclone").is_file():
                        out["rclone"] = str(Path(d) / "rclone")
                        break
    except OSError:
        pass
    try:
        lines = (SUBIR_SUPPORT / "config.txt").read_text(encoding="utf-8").splitlines()
        if lines and lines[0].strip():
            out["remote"] = lines[0].strip()
        if len(lines) > 1:
            out["root"] = lines[1].strip()
    except OSError:
        pass
    return out


def find_rclone(saved: str | None = None) -> dict:
    """{"path", "from", "config"?}. Ordem: o escolhido nas configurações, o do Subir no Drive, o PATH,
    lugares comuns."""
    if saved and Path(saved).expanduser().is_file():
        return {"path": str(Path(saved).expanduser()), "from": "configuracoes"}
    sub = _subir_files()
    if sub.get("rclone"):
        return {"path": sub["rclone"], "from": "subir_no_drive", "config": sub.get("config")}
    w = shutil.which("rclone")
    if w:
        return {"path": w, "from": "sistema"}
    home = Path.home()
    cands = [home / "Applications" / "rclone" / "rclone", Path("/Applications/rclone/rclone"),
             Path("/opt/homebrew/bin/rclone"), Path("/usr/local/bin/rclone"), home / "bin" / "rclone"]
    if os.name == "nt":
        la = Path(os.environ.get("LOCALAPPDATA") or home)
        cands = [la / "rclone" / "rclone.exe", home / "rclone" / "rclone.exe", Path("C:/rclone/rclone.exe"),
                 Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "rclone" / "rclone.exe"]
    for c in cands:
        if c.is_file():
            return {"path": str(c), "from": "sistema"}
    return {"path": None, "from": None}


def defaults_from_subir() -> dict:
    """Valores sugeridos para as configurações (quando o Subir no Drive está instalado)."""
    sub = _subir_files()
    return {k: sub[k] for k in ("remote", "root", "config") if sub.get(k)}


# ------------------------------------------------------------------ rodar o rclone

class Rclone:
    def __init__(self, path: str, config: str | None = None, remote: str = "drive"):
        if not path or not Path(path).is_file():
            raise DriveError("O rclone não foi encontrado neste computador. Aponte o programa nas Configurações → Google Drive.")
        if not re.fullmatch(r"[\w.\- ]{1,60}", remote or ""):
            raise DriveError("Nome de conexão inválido.")
        self.path, self.config, self.remote = path, config, remote

    def env(self) -> dict:
        e = dict(os.environ)
        if self.config:
            e["RCLONE_CONFIG"] = self.config
        return e

    def run(self, args: list[str], timeout: float = 120) -> str:
        try:
            r = subprocess.run([self.path, *args], capture_output=True, text=True, encoding="utf-8", errors="replace",
                               timeout=timeout, env=self.env(), creationflags=_NO_WINDOW)
        except subprocess.TimeoutExpired:
            raise DriveError("O Drive demorou demais para responder. Confira a internet e tente de novo.")
        except OSError as e:
            raise DriveError(f"Não deu para rodar o rclone ({e}).")
        if r.returncode != 0:
            raise DriveError(friendly(r.stderr))
        return r.stdout

    def at(self, folder_id: str | None = None, sub: str = "") -> str:
        """Endereço para o rclone: a pasta pelo id (link colado) ou um caminho na conexão."""
        if folder_id:
            return f"{self.remote},root_folder_id={folder_id}:{sub}"
        return f"{self.remote}:{sub}"

    def remotes(self) -> list[str]:
        out = self.run(["listremotes", "--long"], timeout=30)
        names = []
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "drive" and parts[0].endswith(":"):
                names.append(parts[0][:-1])
        return names

    def email(self) -> str | None:
        try:
            out = self.run(["config", "userinfo", f"{self.remote}:"], timeout=30)
        except DriveError:
            return None
        m = re.search(r"email:\s*(\S+)", out, re.I)
        return m.group(1) if m else None

    def lsjson(self, where: str, *flags: str, timeout: float = 180) -> list[dict]:
        out = self.run(["lsjson", where, *flags], timeout=timeout)
        try:
            data = json.loads(out or "[]")
        except json.JSONDecodeError:
            raise DriveError("Resposta estranha do Drive (lista de arquivos).")
        return data if isinstance(data, list) else []


def friendly(stderr: str) -> str:
    s = stderr or ""
    low = s.lower()
    if "didn't find section in config file" in low or "not found in config" in low:
        return "A conexão escolhida não existe no rclone deste computador. Confira em Configurações → Google Drive."
    if "invalid_grant" in low or ("token" in low and "expired" in low) or ("oauth2" in low and "refresh" in low):
        return "A conexão do rclone com o Google expirou. Abra o Terminal e rode \"rclone config reconnect drive:\" (como no Subir no Drive)."
    if "notfound" in low or "file not found" in low or "directory not found" in low or "404" in low:
        return "Pasta não encontrada no Drive (o link está certo? a conta da conexão tem acesso a ela?)."
    if "insufficient" in low and "scope" in low:
        return "A conexão do rclone não tem permissão para ler essa pasta."
    if "no such host" in low or "dial tcp" in low or "network is unreachable" in low or "timeout" in low:
        return "Sem internet ou o Google não respondeu. Tente de novo."
    last = [ln for ln in s.strip().splitlines() if ln.strip()]
    return "Erro do rclone: " + (last[-1][-240:] if last else "sem detalhe")


# ------------------------------------------------------------------ link, nomes e árvore

def folder_id(link: str) -> str | None:
    """Id da pasta num link do Drive (".../folders/<id>", "?id=<id>") ou o próprio id colado."""
    t = (link or "").strip()
    m = re.search(r"/folders/([\w-]{10,})", t) or re.search(r"[?&]id=([\w-]{10,})", t)
    if m:
        return m.group(1)
    if re.fullmatch(r"[\w-]{15,}", t):
        return t
    return None


def _plain(s: str) -> str:
    n = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in n if not unicodedata.combining(c)).lower().strip()


def is_saida(name: str) -> bool:
    return _plain(name) in ("saida", "saidas")


def is_transcricoes(name: str) -> bool:
    return _plain(name) in ("transcricoes", "transcricao")


def day_of(name: str) -> str | None:
    m = re.fullmatch(r"\s*(\d{4})[ ._\-](\d{1,2})[ ._\-](\d{1,2})\s*", name or "")
    return f"{m.group(1)} {int(m.group(2)):02d} {int(m.group(3)):02d}" if m else None


def course_parts(name: str) -> tuple[str, str]:
    """"26_701 Maria Clara Souza" → ("26_701", "Maria Clara Souza")."""
    m = re.match(r"\s*(\d+[_\-.]\d+)\s+(.*\S)\s*$", name or "")
    if m:
        return m.group(1), m.group(2)
    return "", (name or "").strip()


def make_name(template: str, data: str, professor: str, codigo: str = "") -> str:
    t = (template or NAME_DEFAULT)
    out = t.replace("{data}", data or "").replace("{professor}", professor or "").replace("{codigo}", codigo or "")
    out = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "-", out)
    out = re.sub(r"\s+", " ", out).strip(" .-")
    return out[:120]


def valid_template(t: str) -> bool:
    if not isinstance(t, str) or not t.strip() or len(t) > 80:
        return False
    toks = re.findall(r"\{(\w+)\}", t)
    return bool(toks) and all(x in TOKENS for x in toks) and t.count("{") == len(toks)


_tree_lock = threading.Lock()
_tree: dict = {"key": None, "at": 0.0, "dirs": []}


def tree(rc: Rclone, root: str, refresh: bool = False) -> list[dict]:
    """Pastas (até 3 níveis) da pasta das gravações: [{"Path", "Name", "ID"}]. Guardado uns minutos."""
    key = (rc.path, rc.config, rc.remote, root)
    with _tree_lock:
        if not refresh and _tree["key"] == key and time.time() - _tree["at"] < TREE_TTL_S:
            return _tree["dirs"]
    dirs = rc.lsjson(rc.at(None, root), "--dirs-only", "-R", "--max-depth", "3", "--fast-list", timeout=300)
    with _tree_lock:
        _tree.update(key=key, at=time.time(), dirs=dirs)
    return dirs


def locate(rc: Rclone, root: str, fid: str) -> dict:
    """Onde fica a pasta do link: {"found", "saida_id", "day", "course", "codigo", "professor",
    "transcricoes_id", "path"}."""
    hit = None
    for refresh in (False, True):
        dirs = tree(rc, root, refresh)
        hit = next((d for d in dirs if d.get("ID") == fid), None)
        if hit:
            break
    out = {"found": False, "saida_id": fid, "day": None, "course": None, "codigo": "", "professor": "",
           "transcricoes_id": None, "path": None}
    if not hit:
        return out
    parts = hit["Path"].split("/")
    by_path = {d["Path"]: d for d in dirs}
    if is_saida(parts[-1]) and len(parts) >= 2:
        day_path = "/".join(parts[:-1])
    elif day_of(parts[-1]):
        day_path = hit["Path"]
        sai = next((d for p, d in by_path.items() if p.rsplit("/", 1)[0] == day_path and is_saida(d["Name"])), None)
        if sai is None:
            raise DriveError("Essa pasta do dia não tem a pasta Saída.")
        out["saida_id"] = sai["ID"]
    else:
        raise DriveError("Cole o link da pasta Saída (ou da pasta do dia).")
    dparts = day_path.split("/")
    out["found"] = True
    out["day"] = day_of(dparts[-1]) or dparts[-1]
    out["course"] = dparts[-2] if len(dparts) >= 2 else ""
    out["codigo"], out["professor"] = course_parts(out["course"])
    tr = next((d for p, d in by_path.items() if p.rsplit("/", 1)[0] == day_path and is_transcricoes(d["Name"])), None)
    out["transcricoes_id"] = tr["ID"] if tr else None
    out["path"] = [root.rstrip("/").split("/")[-1]] + dparts + ["Saída"] if root else dparts + ["Saída"]
    return out


def plan(rc: Rclone, root: str, link: str, dest_root: str, template: str, want_transcripts: bool) -> dict:
    fid = folder_id(link)
    if not fid:
        raise DriveError("Isso não parece um link de pasta do Drive.")
    loc = locate(rc, root, fid)
    files = [f for f in rc.lsjson(rc.at(loc["saida_id"]), "--files-only", timeout=120)
             if Path(f.get("Name", "")).suffix.lower() in VIDEO_EXT and not f.get("Name", "").startswith(".")]
    files.sort(key=lambda f: f["Name"].lower())
    if not files:
        raise DriveError("Nenhum vídeo (MP4, MOV) nessa pasta do Drive.")
    trs = {}
    if want_transcripts and loc["transcricoes_id"]:
        for f in rc.lsjson(rc.at(loc["transcricoes_id"]), "--files-only", timeout=120):
            n = f.get("Name", "")
            if n.endswith(transcricao.SUFFIX):
                trs[n] = f.get("Size", 0)
    name = make_name(template, loc["day"], loc["professor"], loc["codigo"]) if loc["found"] else ""
    return {"loc": loc, "folder_id": fid, "name": name, "dest_root": dest_root,
            "videos": [{"name": f["Name"], "size": int(f.get("Size") or 0),
                        "transcript": transcricao.file_name(f["Name"]) in trs} for f in files],
            "total": sum(int(f.get("Size") or 0) for f in files)}


# ------------------------------------------------------------------ baixar (em segundo plano)

class Download:
    """Uma pasta por vez. Estado para a tela: state, bytes, total, eta, arquivos."""

    def __init__(self, rc: Rclone, pl: dict, name: str, transcripts: bool):
        safe = make_name("{data}", name, "")
        if not safe:
            raise DriveError("Escreva o nome da pasta.")
        self.rc, self.pl, self.name = rc, pl, safe
        self.dest = Path(pl["dest_root"]).expanduser() / safe
        self.transcripts = transcripts
        self.state, self.error = "idle", None
        self.bytes, self.total, self.eta = 0, int(pl["total"]), None
        self.current: dict[str, float] = {}
        self.tr_done = 0
        self.started = self.finished = None
        self._proc = None
        self._cancel = False

    def start(self):
        self.state, self.started = "running", time.time()
        threading.Thread(target=self._run, name="drive", daemon=True).start()

    def cancel(self):
        self._cancel = True
        p = self._proc
        if p and p.poll() is None:
            try:
                p.terminate()
            except OSError:
                pass

    def _copy(self, src: str, dest: Path, names: list[str], progress: bool) -> None:
        dest.mkdir(parents=True, exist_ok=True)
        lst = dest / ".revisor-baixar.txt"
        lst.write_text("\n".join(names) + "\n", encoding="utf-8")
        args = [self.rc.path, "copy", src, str(dest), "--files-from", str(lst), "--transfers", "2",
                "--retries", "3", "--use-json-log", "--stats", "1s", "--stats-log-level", "NOTICE", "-v"]
        try:
            self._proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
                                          encoding="utf-8", errors="replace", env=self.rc.env(), creationflags=_NO_WINDOW)
            tail = []
            for line in self._proc.stderr:
                if progress:
                    self._stats(line)
                tail = (tail + [line])[-20:]
            code = self._proc.wait()
        finally:
            try:
                lst.unlink()
            except OSError:
                pass
        if self._cancel:
            raise DriveError("Download cancelado.")
        if code != 0:
            msgs = []
            for ln in tail:
                try:
                    j = json.loads(ln)
                    if j.get("level") in ("error", "critical"):
                        msgs.append(j.get("msg", ""))
                except ValueError:
                    msgs.append(ln)
            raise DriveError(friendly("\n".join(msgs)))

    def _stats(self, line: str) -> None:
        try:
            j = json.loads(line)
        except ValueError:
            return
        st = j.get("stats")
        if not isinstance(st, dict):
            return
        self.bytes = int(st.get("bytes") or 0)
        if st.get("totalBytes"):
            self.total = max(self.total, int(st["totalBytes"]))
        self.eta = st.get("eta")
        self.current = {t.get("name", ""): float(t.get("percentage") or 0) for t in st.get("transferring") or []}

    def _run(self):
        try:
            names = [v["name"] for v in self.pl["videos"]]
            self._copy(self.rc.at(self.pl["loc"]["saida_id"]), self.dest, names, True)
            self.bytes, self.current = self.total, {}
            want = [transcricao.file_name(v["name"]) for v in self.pl["videos"] if v["transcript"]]
            if self.transcripts and want and self.pl["loc"].get("transcricoes_id"):
                self.state = "transcricoes"
                self._copy(self.rc.at(self.pl["loc"]["transcricoes_id"]), self.dest / transcricao.FOLDER_NAMES[0], want, False)
                self.tr_done = len(want)
            self.state = "done"
        except DriveError as e:
            self.state, self.error = ("cancelled" if self._cancel else "error"), str(e)
        except OSError as e:
            self.state, self.error = "error", f"Não deu para gravar no disco ({e.strerror or e})."
        finally:
            self.finished = time.time()

    def view(self) -> dict:
        files = []
        for v in self.pl["videos"]:
            p = self.dest / v["name"]
            if v["name"] in self.current:
                pct = self.current[v["name"]]
            elif p.is_file() and v["size"] and p.stat().st_size >= v["size"]:
                pct = 100.0
            else:
                pct = 0.0
            files.append({"name": v["name"], "size": v["size"], "pct": round(pct, 1)})
        return {"state": self.state, "error": self.error, "name": self.name, "dest": str(self.dest),
                "bytes": self.bytes, "total": self.total, "eta": self.eta, "files": files,
                "transcripts": sum(1 for v in self.pl["videos"] if v["transcript"]) if self.transcripts else 0,
                "transcripts_done": self.tr_done, "loc": self.pl["loc"]}
