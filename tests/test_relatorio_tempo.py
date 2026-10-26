"""Relatório de tempo feito pelo app (revisor/timereport.py): o txt tem que sair IGUAL ao do
script "Calculo de tempo.command", porque sobe para a planilha do Google.

Os 6 relatórios reais de tests/relatorios/ são refeitos: para cada um, o teste procura durações
com casas decimais (o script soma os valores com decimais e só arredonda no fim) que deem as
mesmas linhas e os mesmos totais, monta pastas com arquivos desses nomes e compara o texto
gerado, linha por linha, com o original (menos a linha "Data:").
"""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime
from pathlib import Path

import pytest

from revisor import media, report, timereport

HERE = Path(__file__).parent
SAMPLES = sorted((HERE / "relatorios").glob("Relatorio_tempo_*.txt"))


def _exact_names(text: str, rep):
    """Nomes como estão no txt (o report.parse tira espaços do começo: " 01 Estudo…" existe de verdade)."""
    names, sec = {"raw": [], "edited": []}, None
    for line in text.splitlines():
        if line.startswith("BRUTOS"):
            sec = "raw"
        elif line.startswith("EDITADOS"):
            sec = "edited"
        elif line.startswith("---"):
            sec = None
        elif sec and len(line) > 12 and line[:2] == "  " and line[4] == ":" and line[10:12] == "  ":
            names[sec].append(line[12:])
    rep.raw = [(s, n) for (s, _o), n in zip(rep.raw, names["raw"])]
    rep.edited = [(s, n) for (s, _o), n in zip(rep.edited, names["edited"])]


def _safe(name: str) -> str:
    """No Windows ":" não pode em nome de pasta ("Carlos 21:09" vira "Carlos 21-09")."""
    return name.replace(":", "-") if os.name == "nt" else name


def _fake_dirs(tmp_path, rep, ignored_raw, ignored_ed):
    raw, ed = tmp_path / "brutos", tmp_path / _safe(rep.project)
    raw.mkdir()
    ed.mkdir()
    for _s, name in rep.raw:
        (raw / name).write_bytes(b"")
    for _s, name in rep.edited:
        (ed / name).write_bytes(b"")
    for k in range(ignored_raw):                    # divisões do Estúdio Encoder (ficam de fora)
        (raw / f"zz {k:03d}-{'D' if k % 2 else 'E'}.mp4").write_bytes(b"")
    for k in range(ignored_ed):
        (ed / f"zz {k:03d}-D.mp4").write_bytes(b"")
    (raw / ".escondido.mp4").write_bytes(b"")       # arquivo oculto: o script não lê
    (ed / "sub").mkdir()
    (ed / "sub" / "antigo.mp4").write_bytes(b"")    # subpasta dos editados: o script não lê
    return raw, ed


@pytest.mark.parametrize("sample", SAMPLES, ids=[p.stem for p in SAMPLES])
def test_txt_igual_ao_do_script(sample, tmp_path, monkeypatch):
    rep = report.parse(sample)
    original = sample.read_text(encoding="utf-8")
    _exact_names(original, rep)
    original = original.replace(f"Projeto (pasta editados): {rep.project}\n",
                                f"Projeto (pasta editados): {_safe(rep.project)}\n")
    raw, ed = _fake_dirs(tmp_path, rep, rep.ignored_raw or 0, rep.ignored_edited or 0)
    # a ordem das linhas tem que ser a mesma do script (find | sort)
    assert [p.name for p in timereport.list_videos(raw, True)] == [n for _s, n in rep.raw] + \
        sorted(p.name for p in raw.iterdir() if p.name.startswith("zz"))
    assert [p.name for p in timereport.list_videos(ed, False)] == [n for _s, n in rep.edited] + \
        sorted(p.name for p in ed.iterdir() if p.name.startswith("zz"))

    secs = {n: s for s, n in rep.raw + rep.edited}
    now = datetime.strptime(original.split("Data: ", 1)[1][:16], "%d/%m/%Y %H:%M")
    steps = [x / 100 for x in range(-49, 50, 3)]
    for fr in steps:
        for fe in steps:
            frac = {**{n: fr for _s, n in rep.raw}, **{n: fe for _s, n in rep.edited}}
            monkeypatch.setattr(timereport, "duration_of", lambda p: secs[Path(p).name] + frac[Path(p).name])
            res = timereport.build(raw, ed, now=now)
            if res.text == original:
                assert res.filename == sample.name
                return
    # nenhuma combinação: mostra a diferença da melhor tentativa
    monkeypatch.setattr(timereport, "duration_of", lambda p: float(secs[Path(p).name]))
    got = timereport.build(raw, ed, now=now).text
    assert got.splitlines()[:-6] == original.splitlines()[:-6]
    pytest.fail("os totais não bateram com nenhuma combinação de decimais:\n" + got)


def test_regras_basicas(tmp_path, monkeypatch):
    raw, ed = tmp_path / "Brutos", tmp_path / _safe("Ana 21:09")
    (raw / "cam2").mkdir(parents=True)
    ed.mkdir()
    durs = {"2026-09-21 10-00-00.mp4": 600.4, "2026-09-21 10-00-00-D.mp4": 300, "2026-09-21 10-00-00-e.mov": 300,
            "2026-09-21 11-00-00.mkv": 59.6, "01 Aula.mp4": 500.25, "02 Aula.mp4": 100.25, "quebrado.mp4": None}
    for n in ("2026-09-21 10-00-00.mp4", "2026-09-21 10-00-00-D.mp4", "2026-09-21 10-00-00-e.mov"):
        (raw / n).write_bytes(b"x")
    (raw / "cam2" / "2026-09-21 11-00-00.mkv").write_bytes(b"x")       # subpasta dos brutos entra
    (raw / "notas.txt").write_text("não é vídeo")
    for n in ("01 Aula.mp4", "02 Aula.mp4", "quebrado.mp4"):
        (ed / n).write_bytes(b"x")
    monkeypatch.setattr(timereport, "duration_of", lambda p: durs[Path(p).name])
    res = timereport.build(raw, ed, now=datetime(2026, 10, 26, 9, 5))
    t = res.text
    assert res.filename == "Relatorio_tempo_2026-10-26_0905.txt"
    assert f"Projeto (pasta editados): {_safe('Ana 21:09')}\nData: 26/10/2026 09:05\n\nBRUTOS (2 arquivos)\n" in t
    assert "  00:10:00  2026-09-21 10-00-00.mp4\n  00:01:00  2026-09-21 11-00-00.mkv\n\nEDITADOS (2 arquivos)\n" in t
    assert "TEMPO DE GRAVAÇÃO (bruto): 00:11:00\n" in t           # 600,4 + 59,6 = 660
    assert "TEMPO LÍQUIDO (editado):   00:10:01\n" in t           # 500,25 + 100,25 = 600,5 → arredonda para cima
    assert "APROVEITAMENTO:            91,0%\n" in t
    assert "TEMPO DESCARTADO:          00:00:60" not in t and "TEMPO DESCARTADO:          00:01:00\n" in t
    assert "Ignorados por terminarem em -D ou -E: brutos 2, editados 0\n" in t
    assert t.endswith("ATENÇÃO - arquivos não lidos (NÃO entraram na soma):\n  - quebrado.mp4\n\n")
    # o app lê de volta o que escreveu
    p = timereport.save(res, ed)
    back = report.parse(p)
    assert (back.total_raw_s, back.total_edited_s, back.usage_pct, back.discarded_s) == (660, 601, 91.0, 60)
    assert report.find_in_folder(ed) == p
    assert p.read_bytes().count(b"\r") == 0


def test_pastas_erradas(tmp_path, monkeypatch):
    a = tmp_path / "a"
    a.mkdir()
    with pytest.raises(timereport.TimeReportError, match="mesma"):
        timereport.build(a, a)
    with pytest.raises(timereport.TimeReportError, match="brutos não encontrada"):
        timereport.build(tmp_path / "nada", a)
    b = tmp_path / "b"
    b.mkdir()
    (b / "x.mp4").write_bytes(b"")
    monkeypatch.setattr(timereport, "duration_of", lambda p: None)
    with pytest.raises(timereport.TimeReportError, match="Não consegui ler vídeos"):
        timereport.build(a, b)


def test_divididos():
    assert timereport.is_split("2026-09-21 10-38-10-D.mp4")
    assert timereport.is_split("x-e.MOV")
    assert not timereport.is_split("2026-09-21 10-38-10-001.mp4")
    assert not timereport.is_split("01 Parte 1-.mp4")
    assert not timereport.is_split("Aula-DE.mp4")


def _make(path: Path, seconds: float, extra: list[str]):
    from conftest import video_codec          # libx264 quando houver; senão MPEG-4 (FFmpeg do app no Mac)
    cmd = [media.ffmpeg(), "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=160x90:rate=30000/1001",
           "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000", "-t", str(seconds),
           *video_codec(), "-pix_fmt", "yuv420p", "-c:a", "aac", *extra, str(path)]
    subprocess.run(cmd, check=True, capture_output=True)


def test_duracao_do_cabecalho(tmp_path):
    """mvhd (MP4 normal) e MP4 fragmentado: a duração lida bate com a do FFprobe (±0,1 s)."""
    normal, frag, mov = tmp_path / "normal.mp4", tmp_path / "frag.mp4", tmp_path / "x.mov"
    _make(normal, 3.5, [])
    _make(frag, 4.2, ["-movflags", "frag_keyframe+empty_moov"])
    _make(mov, 2.0, [])
    mv, _me = timereport._mvhd_mehd(normal)
    assert mv is not None and abs(mv - media.probe(normal).duration) < 0.1
    assert timereport._mvhd_mehd(frag)[0] is None           # fragmentado: o cabeçalho diz zero
    for p in (normal, frag, mov):
        d = timereport.duration_of(p)
        assert d is not None and abs(d - media.probe(p).duration) < 0.15, (p.name, d)
    junk = tmp_path / "lixo.mp4"
    junk.write_bytes(b"isto nao e um video" * 10)
    assert timereport.duration_of(junk) is None


def test_servidor_relatorio_e_modo_editor(tmp_path, monkeypatch):
    """Rota do relatório de tempo + começar no modo editor (sem entrega: vale o dia; editor = o nome
    das configurações; pasta dos brutos guardada na revisão, mas nunca no pacote)."""
    from datetime import date

    from conftest import PROJ
    from revisor import appdata, export, review, server
    monkeypatch.setenv("REVISOR_HOME", str(tmp_path / "home"))
    ed, raw = tmp_path / PROJ, tmp_path / "Brutos"
    ed.mkdir()
    (raw / "cam").mkdir(parents=True)
    _make(ed / "01 Aula.mp4", 2.0, [])
    _make(ed / "02 Aula.mp4", 3.0, [])
    _make(raw / "2026-10-19 10-00-00.mp4", 4.0, [])
    _make(raw / "2026-10-19 10-00-00-D.mp4", 2.0, [])
    _make(raw / "cam" / "2026-10-19 11-00-00.mp4", 2.5, ["-movflags", "frag_keyframe+empty_moov"])
    app = server.App()
    monkeypatch.setattr(app, "_pump", lambda: None)            # sem análise de verdade aqui
    with pytest.raises(server.ApiError, match="brutos"):
        app.time_report({"raw": "", "edited": str(ed)})
    r = app.time_report({"raw": str(raw), "edited": str(ed)})
    assert r["in_folder"] and (ed / r["file"]).is_file()
    assert r["summary"]["raw_files"] == 2 and r["summary"]["ignored_raw"] == 1
    assert r["report"]["total_edited_s"] == 5 and r["report"]["total_raw_s"] in (6, 7)
    assert appdata.load_settings()["last_raw_folder"] == str(raw.resolve())
    info = app.folder_info(str(ed))
    assert info["scan"]["report"]["file"] == r["file"]

    # modo editor: começa sem a entrega
    appdata.save_settings({"mode": "editor", "my_name": "Mônica"})
    out = app.start({"folder": str(ed), "professor": "Ana", "nome_tarja": "Ana Souza", "raw_folder": str(raw),
                     "spell": True, "transcribe": False})
    assert out["ok"]
    rev = app.review
    assert rev["entrega"] == date.today().isoformat() and rev["entrega_locked"]
    assert [v["editor"] for v in rev["videos"]] == ["Mônica", "Mônica"]
    assert rev["raw_folder"] == str(raw.resolve()) and rev["report"]["file"] == r["file"]
    assert app.review_view()["review"]["raw_folder"] == str(raw.resolve())
    assert app.folder_info(str(ed))["prev"]["raw_folder"] == str(raw.resolve())
    # gerar de novo com a revisão aberta: ela passa a usar o txt novo
    (ed / r["file"]).rename(ed / "Relatorio_tempo_2020-01-01_0000.txt")
    r2 = app.time_report({"raw": str(raw), "edited": str(ed)})
    assert rev["report"]["file"] == r2["file"]
    # o pacote não leva o caminho dos brutos
    (tmp_path / "out").mkdir()
    pk = export.export_package(rev, tmp_path / "out", lambda v, f: None)
    data = json.loads((Path(pk["folder"]) / "revisao.json").read_text(encoding="utf-8"))
    assert "raw_folder" not in data and "folder" not in data
    # configurações: modo e nome
    with pytest.raises(server.ApiError):
        app.settings_save({"mode": "chefe"})
    app.settings_save({"mode": "revisor", "my_name": "  Mônica   Lima "})
    s = appdata.load_settings()
    assert s["mode"] == "revisor" and s["my_name"] == "Mônica Lima"
    # modo revisor exige a entrega numa pasta nova
    other = tmp_path / "Bia 20-10"
    other.mkdir()
    _make(other / "01.mp4", 1.0, [])
    with pytest.raises(server.ApiError, match="entrega"):
        app.start({"folder": str(other), "professor": "Bia"})
    assert review.find(app.reviews_root(), PROJ)["raw_folder"] == str(raw.resolve())
