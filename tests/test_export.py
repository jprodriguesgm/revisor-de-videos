"""Etapa 5: texto copiado, SRT, horas por editor, rodadas, pacote entre computadores,
junção de revisões, relatório do mês e configurações."""
import json
import shutil
import subprocess
import time

import pytest

from conftest import PROJ, ffmpeg, video_codec
from revisor import export, review, spell
from revisor.timecode import NTSC_2997, Rate

from test_review import _req, app_srv, needs_ffmpeg  # noqa: F401  (fixture e utilidades)

R = Rate(NTSC_2997)


def _rev(**kw):
    r = review.new_review("/x/Carlos 21:09")
    r.update({"professor": "Carlos", "curso": "Direito", "entrega": "2026-10-07", "entrega_locked": True,
              "report": {"file": "Relatorio_tempo_2026-10-07_1032.txt", "date": "2026-10-07 10:32",
                         "total_raw_s": 4126, "total_edited_s": 3304, "usage_pct": 80.1,
                         "raw": [{"seconds": 2036, "file": "2026-09-21 10-38-10-001.mp4"},
                                 {"seconds": 2090, "file": "2026-09-30 11-17-22.mp4"}]}})
    r["videos"] = [
        {"id": "a1", "file": "01 Parte 1.mp4", "duration": 798.2, "editor": "Lúcia", "fps": "30000/1001",
         "report_entry": {"seconds": 798, "file": "01 Parte 1-.mp4"},
         "comments": [{"cid": "c1", "frame": 1319, "text": "Trocar o slide", "selected": True, "with_frame": True,
                       "updated": "2026-10-15 10:00:00"},
                      {"cid": "c2", "frame": 1349, "text": "Pico de áudio\n\nconferir", "selected": True,
                       "with_frame": False, "updated": "2026-10-15 10:00:00"}]},
        {"id": "b2", "file": "02 Parte 2.mp4", "duration": 958.0, "editor": "Mônica", "fps": "30000/1001",
         "comments": [{"cid": "c3", "frame": 300, "text": "Não vai", "selected": False, "with_frame": True}]},
        {"id": "c3", "file": "03 Apresentação.mp4", "duration": 50.0, "editor": None, "comments": []},
    ]
    r.update(kw)
    return r


def test_linhas_e_texto_copiado():
    rows = export.comment_rows(_rev())
    assert [r["tc"] for r in rows] == ["00:00:44", "00:00:45", "00:00:10"]
    assert export.line_of(rows[0]) == "Vídeo 01 · 00:00:44 · Trocar o slide"
    nd = export.comment_rows(_rev(), "ndf")
    assert nd[0]["tc"] == "00:00:43:29"
    assert rows[2]["selected"] is False


def test_srt_blocos_sem_sobrepor():
    v = _rev()["videos"][0]
    t = export.srt_text(v["comments"], R, 3, "CORRIGIR:")
    blocks = t.strip().split("\n\n")
    assert blocks[0] == "1\n00:00:44,011 --> 00:00:45,011\nCORRIGIR: Trocar o slide"     # termina antes do próximo
    assert blocks[1] == "2\n00:00:45,012 --> 00:00:48,012\nCORRIGIR: Pico de áudio\nconferir"  # sem linha em branco
    b = export.srt_bytes(t)
    assert b.startswith(b"\xef\xbb\xbf1\r\n") and b"\r\n\r\n2\r\n" in b
    assert export.srt_text(v["comments"][:1], R, 2, "").splitlines()[2] == "Trocar o slide"


def test_srt_so_dos_marcados(tmp_path):
    rev = _rev()
    out = export.write_srts(rev, tmp_path, 3, "CORRIGIR:", "beside")
    assert [f["file"] for f in out["files"]] == ["01 Parte 1.srt"]          # vídeo 2: comentário desmarcado
    assert (tmp_path / "01 Parte 1.srt").read_bytes().count(b"CORRIGIR:") == 2
    out = export.write_srts(rev, tmp_path, 3, "CORRIGIR:", "subfolder")
    assert (tmp_path / "Correções" / "01 Parte 1.srt").is_file()
    import io, zipfile
    z = zipfile.ZipFile(io.BytesIO(export.srt_zip(rev)))
    assert z.namelist() == ["01 Parte 1.srt"]


def test_horas_por_editor():
    h = export.editor_hours(_rev())
    assert [(g["name"], g["videos"], g["seconds"]) for g in h["editors"]] == [
        ("Mônica", [2], 958.0), ("Lúcia", [1], 798.0), (export.NO_EDITOR, [3], 50.0)]
    assert h["total_s"] == 3304 and h["without_editor"] == 1 and h["usage_pct"] == 80.1
    txt = export.hours_txt(_rev())
    assert "Lúcia" in txt and "0:13:18" in txt and "TOTAL EDITADO:     0:55:04" in txt and "sem editor" in txt
    assert export.fmt_hm(42 * 60 + 18) == "0:42h"


def test_rodada_2_herda_editor_e_nao_conta_duas_vezes():
    rev = _rev()
    review.merge_videos(rev, [{"id": "a9", "file": "01 Parte 1.mp4", "duration": 790.0},
                              {"id": "b2", "file": "02 Parte 2.mp4", "duration": 958.0},
                              {"id": "c3", "file": "03 Apresentação.mp4", "duration": 50.0}])
    new = rev["videos"][0]
    assert new["id"] == "a9" and new["round"] == 2 and new["editor"] == "Lúcia" and new["comments"] == []
    old = [v for v in rev["videos"] if v["id"] == "a1"][0]
    assert old["missing"] and len(old["comments"]) == 2                    # comentários antigos guardados
    assert [n for n, v in export.counted_videos(rev)] == [1, 2, 3]          # a versão antiga não conta


def test_pacote_ida_e_volta(tmp_path):
    rev = _rev()
    img = tmp_path / "f.jpg"
    img.write_bytes(b"\xff\xd8fake")
    out = export.export_package(rev, tmp_path, lambda v, f: img if f != 300 else None)
    folder = tmp_path / out["name"]
    assert out["name"] == "Revisão 2026-10-07 Carlos 21-09"
    assert sorted(p.name for p in folder.iterdir()) == ["frames", "horas.txt", "revisao.json"]
    assert out["frames"] == 2 and out["frames_missing"] == 1
    data = json.loads((folder / "revisao.json").read_text(encoding="utf-8"))
    assert "folder" not in data                                             # nenhum caminho
    pkg, base = export.read_package(folder)
    assert pkg["project"] == "Carlos 21:09" and len(pkg["videos"]) == 3
    fr = export.package_frames(pkg, base)
    assert set(fr) == {"a1:1319", "a1:1349"}
    # pacote adulterado: caminho no nome do arquivo e frame fora de frames/
    data["videos"][0]["file"] = "../../etc/01 Parte 1.mp4"
    data["videos"][1]["id"] = "../x"
    data["package"]["frames"]["a1:1"] = "../../segredo.jpg"
    (folder / "revisao.json").write_text(json.dumps(data), encoding="utf-8")
    pkg, base = export.read_package(folder / "revisao.json")
    assert pkg["videos"][0]["file"] == "01 Parte 1.mp4" and len(pkg["videos"]) == 2
    assert "a1:1" not in export.package_frames(pkg, base)
    with pytest.raises(export.PackageError):
        export.read_package(tmp_path / "nada")


def test_juntar_revisoes():
    local = _rev(updated="2026-10-15 11:20:00")
    pkg = _rev(updated="2026-10-16 09:00:00")
    pkg["videos"][0]["comments"][0].update({"text": "Trocar o slide 3", "updated": "2026-10-16 08:00:00"})
    pkg["videos"][0]["comments"].append({"cid": "n1", "frame": 9000, "text": "Novo", "selected": True,
                                         "with_frame": True})
    pkg["videos"][2]["editor"] = "Mônica"
    pkg["videos"].append({"id": "d4", "file": "04 Extra.mp4", "duration": 10.0, "comments": []})
    m = export.merge_reviews(local, pkg)
    cs = m["videos"][0]["comments"]
    assert [c["text"] for c in cs] == ["Trocar o slide 3", "Pico de áudio\n\nconferir", "Novo"]
    assert m["videos"][2]["editor"] == "Mônica" and [v["id"] for v in m["videos"]][-1] == "d4"


def test_relatorio_do_mes(tmp_path):
    a = _rev()
    b = _rev(project="Ana 02:10", key="ana 02:10", entrega="2026-10-20", curso="")
    b["report"] = None
    b["videos"] = [dict(a["videos"][0]),                                     # o mesmo vídeo (id): não conta de novo
                   {"id": "z9", "file": "01 Outra.mp4", "duration": 600.0, "editor": "Lúcia", "comments": []}]
    c = _rev(project="Velha", key="velha", entrega="2026-09-28")
    c["report"] = None
    c["videos"] = [{"id": "s1", "file": "01 Set.mp4", "duration": 120.0, "editor": "Mônica", "comments": []}]
    rep = export.month_report([a, b, c], "2026-10")
    assert rep["videos"] == 4 and rep["repeated"] == 1
    assert [(e["name"], e["videos"], e["seconds"]) for e in rep["editors"]] == [
        ("Lúcia", 2, 1398.0), ("Mônica", 1, 958.0), (export.NO_EDITOR, 1, 50.0)]
    assert rep["edited_s"] == 2406.0
    assert rep["recorded_s"] == 0.0                                          # brutos gravados em setembro
    assert rep["weeks"][0]["seconds"] == 1806.0 and rep["weeks"][2]["seconds"] == 600.0 and len(rep["weeks"]) == 5
    assert {c_["name"] for c_ in rep["courses"]} == {"Direito", export.NO_COURSE}
    sep = export.month_report([a, b, c], "2026-09")
    assert sep["recorded_s"] == 4126.0 and sep["edited_s"] == 120.0
    assert [m["key"] for m in rep["months"]] == ["2026-10", "2026-09"]
    csv = export.month_csv(rep).decode("utf-8-sig")
    assert csv.splitlines()[0].startswith("Mês;Entrega da edição;Editor") and "0,2217" in csv
    assert "Lúcia" in export.month_txt(rep, 3)
    # revisões em duas pastas (este computador + pacote): conta uma vez, a mais recente
    for d, r in ((tmp_path / "a" / "x", a), (tmp_path / "b" / "Pacote", dict(a, updated="2099-01-01 00:00:00"))):
        d.mkdir(parents=True)
        (d / "revisao.json").write_text(json.dumps(r), encoding="utf-8")
    revs, read, dup = export.find_reviews([tmp_path / "a", tmp_path / "b"])
    assert read == 2 and dup == 1 and revs[0]["updated"].startswith("2099")


def test_expressao_na_lista_propria(tmp_path):
    ck = spell.Checker(("pt_BR",), ["habeas corpus"])
    assert "habeas" in ck.custom and "corpus" in ck.custom
    f = tmp_path / "l.txt"
    spell.add_to_custom(f, "data venia")
    spell.add_to_custom(f, "briefing")
    assert spell.remove_from_custom(f, "Data Venia") and spell.load_custom(f) == ["briefing"]


# ---------------------------------------------------------------- servidor (vídeo pequeno)

@needs_ffmpeg
def test_etapa5_de_ponta_a_ponta(app_srv):
    port, tmp, server = app_srv
    for nome in ("Lúcia", "Mônica"):           # o app começa sem equipe: cada unidade cadastra a sua
        st, _, _ = _req(port, "POST", "/api/settings/editors", {"op": "add", "name": nome})
        assert st == 200
    pasta = tmp / PROJ
    pasta.mkdir()
    for nome in ("01 Teste.mp4", "02 Outro.mp4"):
        subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                        "testsrc2=size=640x360:rate=30000/1001:duration=4", "-f", "lavfi", "-i",
                        "sine=frequency=440:sample_rate=48000:duration=4", *video_codec(), "-pix_fmt", "yuv420p",
                        "-c:a", "aac", "-shortest", str(pasta / nome)], check=True)
    st, data, _ = _req(port, "POST", "/api/start", {"folder": str(pasta), "professor": "Ana", "entrega": "19/10/2026",
                                                    "transcribe": False})
    assert st == 200, data
    for _ in range(240):
        st, data, _ = _req(port, "GET", "/api/job")
        if json.loads(data)["state"] in ("done", "error"):
            break
        time.sleep(0.5)
    st, data, _ = _req(port, "GET", "/api/review")
    vids = json.loads(data)["videos"]
    v1, v2 = vids[0]["id"], vids[1]["id"]
    _req(port, "POST", "/api/comment", {"id": v1, "frame": 60, "text": "Trocar o slide"})
    _req(port, "POST", "/api/comment", {"id": v2, "frame": 30, "text": "Áudio baixo"})
    _req(port, "POST", "/api/review/editor", {"id": "all", "editor": "Lúcia"})

    # resumo final
    st, data, _ = _req(port, "GET", "/api/final")
    f = json.loads(data)
    assert st == 200 and [r["tc"] for r in f["rows"]] == ["00:00:02", "00:00:01"]
    assert f["hours"]["editors"][0]["name"] == "Lúcia" and f["srt"]["videos"] == 2
    cid2 = f["rows"][1]["cid"]
    st, _, _ = _req(port, "POST", "/api/final/mark", {"cid": cid2, "selected": False, "with_frame": False})
    assert st == 200
    st, data, _ = _req(port, "GET", "/api/final")
    r2 = json.loads(data)["rows"][1]
    assert r2["selected"] is False and r2["with_frame"] is False
    st, jpg, _ = _req(port, "GET", f"/api/cframe.jpg?id={v1}&f=60&s=full")
    assert st == 200 and jpg[:2] == b"\xff\xd8"
    # SRT ao lado dos vídeos, só do vídeo com comentário marcado
    st, data, _ = _req(port, "POST", "/api/final/srt", {})
    out = json.loads(data)
    assert st == 200 and [x["file"] for x in out["files"]] == ["01 Teste.srt"]
    assert (pasta / "01 Teste.srt").read_bytes().startswith(b"\xef\xbb\xbf1\r\n00:00:02,002 --> 00:00:05,002")
    st, body, hd = _req(port, "GET", "/api/final/horas.txt")
    assert st == 200 and "attachment" in hd["Content-Disposition"] and "Lúcia".encode() in body

    # pacote: exportar e abrir em "outro computador" (outra pasta do app)
    dest = tmp / "pendrive"
    dest.mkdir()
    st, data, _ = _req(port, "POST", "/api/package/export", {"dest": str(dest)})
    pk = json.loads(data)
    assert st == 200 and pk["frames"] == 2, pk
    pfolder = dest / pk["name"]
    assert (pfolder / "frames").is_dir() and (pfolder / "horas.txt").is_file()
    st, data, _ = _req(port, "POST", "/api/package/inspect", {"path": str(pfolder)})
    ins = json.loads(data)
    assert ins["local"] is not None and all(v["found"] for v in ins["videos"])
    st, _, _ = _req(port, "POST", "/api/package/open", {"path": str(pfolder)})
    assert st == 400                                                       # já existe: precisa escolher
    st, data, _ = _req(port, "POST", "/api/package/open", {"path": str(pfolder), "choice": "merge"})
    assert st == 200 and json.loads(data)["folder_found"]

    # relatório do mês
    st, data, _ = _req(port, "GET", "/api/month?m=2026-10")
    m = json.loads(data)
    assert st == 200 and m["videos"] == 2 and m["editors"][0]["name"] == "Lúcia"
    st, body, hd = _req(port, "GET", "/api/month.csv?m=2026-10")
    assert st == 200 and body.startswith(b"\xef\xbb\xbf") and "csv" in hd["Content-Type"]
    st, _, _ = _req(port, "GET", "/api/month?m=../x")
    assert st == 400

    # configurações
    st, data, _ = _req(port, "GET", "/api/settings/all")
    s = json.loads(data)
    assert st == 200 and s["settings"]["srt_block_s"] == 3
    st, _, _ = _req(port, "POST", "/api/settings/save", {"srt_block_s": 4})
    assert st == 400
    st, _, _ = _req(port, "POST", "/api/settings/save", {"time_format": "ndf", "srt_prefix": " AJUSTAR: ",
                                                         "spell_la": False, "error_phrases": ["errei", "Errei", " "]})
    assert st == 200
    st, data, _ = _req(port, "GET", "/api/settings/all")
    s = json.loads(data)["settings"]
    assert s["time_format"] == "ndf" and s["srt_prefix"] == "AJUSTAR:" and s["error_phrases"] == ["errei"]
    st, data, _ = _req(port, "GET", "/api/final")
    assert json.loads(data)["rows"][0]["tc"] == "00:00:02:00"
    st, data, _ = _req(port, "POST", "/api/settings/editors", {"op": "rename", "name": "Lúcia", "new": "Lúcia Renata"})
    assert st == 200
    st, data, _ = _req(port, "GET", "/api/final")
    assert json.loads(data)["hours"]["editors"][0]["name"] == "Lúcia Renata"   # revisões seguem o nome novo
    st, _, _ = _req(port, "POST", "/api/settings/editors", {"op": "add", "name": "mônica"})
    assert st == 400                                                       # já existe (sem diferença de maiúscula)
    st, data, _ = _req(port, "POST", "/api/settings/words", {"op": "add", "word": "in dubio pro reo"})
    assert st == 200 and "in dubio pro reo" in json.loads(data)["words"]
    st, data, _ = _req(port, "GET", "/api/cache")
    c = json.loads(data)
    assert c["groups"][0]["videos"] == 2 and c["groups"][0]["open"]
    for _ in range(120):                      # abrir o pacote reabriu a revisão (análise do cache)
        if json.loads(_req(port, "GET", "/api/job")[1])["state"] not in ("running", "paused"):
            break
        time.sleep(0.25)
    st, data, _ = _req(port, "POST", "/api/cache/clear", {"project": PROJ})
    assert st == 200 and json.loads(data)["videos"] == 2
    st, data, _ = _req(port, "GET", "/api/cframe.jpg?id=" + v1 + "&f=60&s=full")
    assert st == 200                                   # sem cache: a imagem que veio no pacote ("juntar")
