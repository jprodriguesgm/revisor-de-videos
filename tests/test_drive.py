"""Google Drive opcional (pedido do JP, 23/11/2026), com um rclone de mentira: uma pasta local faz o papel do
Drive e um arquivo ids.json liga cada pasta a um id (como nos links do Drive). Nomes fictícios."""
import json
import os
import sys
import time
from pathlib import Path

import pytest

from test_fila import _req, srv  # noqa: F401 (fixture)

from revisor import drive, transcricao

pytestmark = pytest.mark.skipif(os.name == "nt", reason="rclone de mentira é um script (Mac/Linux)")

FAKE = r'''#!PYTHON
import json, os, sys, time
from pathlib import Path
ROOT = Path(os.environ["FAKE_DRIVE"])
IDS = json.loads((ROOT.parent / "ids.json").read_text())
def where(spec):
    remote, _, sub = spec.partition(":")
    base = ROOT
    if ",root_folder_id=" in remote:
        fid = remote.split("=", 1)[1]
        base = ROOT / (IDS[fid] if fid in IDS else bytes.fromhex(fid[1:]).decode())
    return base / sub if sub else base
a = sys.argv[1:]
if a[:2] == ["listremotes", "--long"]:
    print("drive:  drive"); print("outro: s3"); sys.exit(0)
if a[:2] == ["config", "userinfo"]:
    print("email: conta@exemplo.edu"); sys.exit(0)
if a[0] == "lsjson":
    p = where(a[1])
    if not p.is_dir():
        sys.stderr.write("directory not found"); sys.exit(3)
    rec = "-R" in a
    rev = {v: k for k, v in IDS.items()}
    out = []
    for q in sorted(p.rglob("*") if rec else p.iterdir()):
        rel = q.relative_to(p).as_posix()
        if "--dirs-only" in a and not q.is_dir(): continue
        if "--files-only" in a and not q.is_file(): continue
        if rec and rel.count("/") >= 3: continue
        out.append({"Path": rel, "Name": q.name, "IsDir": q.is_dir(), "Size": q.stat().st_size if q.is_file() else -1,
                    "ID": rev.get(q.relative_to(ROOT).as_posix(), "H" + q.relative_to(ROOT).as_posix().encode().hex())})
    print(json.dumps(out)); sys.exit(0)
if a[0] == "copy":
    src, dst = where(a[1]), Path(a[2])
    names = [n for n in Path(a[a.index("--files-from") + 1]).read_text().splitlines() if n]
    dst.mkdir(parents=True, exist_ok=True)
    tot = sum((src / n).stat().st_size for n in names)
    done = 0
    for n in names:
        data = (src / n).read_bytes()
        (dst / n).write_bytes(data)
        done += len(data)
        sys.stderr.write(json.dumps({"level": "notice", "msg": "stats", "stats": {"bytes": done, "totalBytes": tot, "eta": 0,
                         "transferring": []}}) + "\n")
        time.sleep(0.05)
    sys.exit(0)
sys.stderr.write("comando desconhecido " + " ".join(a)); sys.exit(1)
'''


def _setup(tmp):
    root = tmp / "drive"
    day = root / "Gravações IEC" / "26_701 Maria Clara Souza" / "2026 11 10"
    (day / "Saída").mkdir(parents=True)
    (day / "Transcrições").mkdir()
    (day / "Saída" / "01 Aula.mp4").write_bytes(b"a" * 3000)
    (day / "Saída" / "02 Aula.mp4").write_bytes(b"b" * 2000)
    (day / "Saída" / "notas.txt").write_text("x")
    tr = transcricao.build("01 Aula.mp4", 60.0, [[1, 2, "oi", 1.0]], [[1, 2, "oi"]])
    transcricao.write(day / "Transcrições", "01 Aula.mp4", tr)
    ids = {"SAIDA1234567890": "Gravações IEC/26_701 Maria Clara Souza/2026 11 10/Saída",
           "DIA123456789012345": "Gravações IEC/26_701 Maria Clara Souza/2026 11 10",
           "FORA12345678901234": "Outra/Pasta"}
    (root / "Outra" / "Pasta").mkdir(parents=True)
    (root / "Outra" / "Pasta" / "x.mp4").write_bytes(b"c" * 10)
    (tmp / "ids.json").write_text(json.dumps(ids))
    fake = tmp / "rclone"
    fake.write_text(FAKE.replace("PYTHON", sys.executable))
    fake.chmod(0o755)
    os.environ["FAKE_DRIVE"] = str(root)
    return fake


def test_nomes_e_link():
    assert drive.folder_id("https://drive.google.com/drive/folders/1AbCdEfGhIjK?usp=sharing") == "1AbCdEfGhIjK"
    assert drive.folder_id("https://drive.google.com/open?id=1AbCdEfGhIjKlm") == "1AbCdEfGhIjKlm"
    assert drive.folder_id("oi") is None
    assert drive.course_parts("26_701 Maria Clara Souza") == ("26_701", "Maria Clara Souza")
    assert drive.make_name("{data} {professor}", "2026 11 10", "Maria Clara Souza") == "2026 11 10 Maria Clara Souza"
    assert drive.make_name("{codigo} - {professor}", "", "Ana/B", "26_1") == "26_1 - Ana-B"
    assert drive.valid_template("{data} {professor}") and not drive.valid_template("{senha}") and not drive.valid_template("sem")
    assert drive.is_saida("Saída") and drive.is_saida("saida") and drive.day_of("2026 11 10") == "2026 11 10"


def test_baixar_do_drive(srv):  # noqa: F811
    port, tmp, server = srv
    fake = _setup(tmp)
    dest = tmp / "Vídeos para conferir"
    dest.mkdir()
    # desligado: não deixa
    st, r = _req(port, "POST", "/api/drive/plan", {"link": "https://drive.google.com/drive/folders/SAIDA1234567890"})
    assert st == 400 and "desligado" in r["error"]
    assert _req(port, "POST", "/api/settings/save", {"drive_on": True, "drive_rclone": str(fake), "drive_root": "Gravações IEC",
                                                       "drive_dest": str(dest)})[0] == 200
    st, r = _req(port, "POST", "/api/settings/save", {"drive_name": "{senha}"})
    assert st == 400
    st, t = _req(port, "POST", "/api/drive/test", {})
    assert st == 200 and t["ok"] and t["email"] == "conta@exemplo.edu" and t["folders"] == 1, t
    st, t = _req(port, "POST", "/api/drive/test", {"remote": "nada"})
    assert not t["ok"] and "nada" in t["error"]
    for link in ("https://drive.google.com/drive/folders/SAIDA1234567890", "DIA123456789012345"):
        st, p = _req(port, "POST", "/api/drive/plan", {"link": link})
        assert st == 200, p
        assert p["name"] == "2026 11 10 Maria Clara Souza" and p["loc"]["found"]
        assert [v["name"] for v in p["videos"]] == ["01 Aula.mp4", "02 Aula.mp4"]
        assert [v["transcript"] for v in p["videos"]] == [True, False]
        assert p["total"] == 5000 and not p["exists"] and p["prev"] is None
    st, r = _req(port, "POST", "/api/drive/start", {"name": p["name"]})
    assert st == 200, r
    for _ in range(100):
        st, j = _req(port, "GET", "/api/drive/job")
        if j["job"]["state"] in ("done", "error"):
            break
        time.sleep(0.1)
    assert j["job"]["state"] == "done", j
    out = dest / "2026 11 10 Maria Clara Souza"
    assert (out / "01 Aula.mp4").stat().st_size == 3000 and (out / "02 Aula.mp4").is_file()
    assert not (out / "notas.txt").exists()
    assert (out / "Transcrições" / "01 Aula.transcricao.json").is_file()
    assert not any(n.name.startswith(".revisor") for n in out.iterdir())
    assert all(f["pct"] == 100 for f in j["job"]["files"])
    # pasta fora da pasta das gravações: baixa, mas o nome fica por conta do JP
    st, p = _req(port, "POST", "/api/drive/plan", {"link": "FORA12345678901234"})
    assert st == 200 and not p["loc"]["found"] and p["name"] == ""
    st, n = _req(port, "POST", "/api/drive/name", {"name": "2026 11 10 Maria Clara Souza"})
    assert n["exists"]
    st, r = _req(port, "POST", "/api/drive/start", {"name": ""})
    assert st == 400
    st, r = _req(port, "POST", "/api/drive/plan", {"link": "isso não é link"})
    assert st == 400 and "link" in r["error"]
