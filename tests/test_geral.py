"""Comentário geral do vídeo (pedido do JP, 21/10): sem tempo ("aumentar o áudio geral",
"ajustar a cor da pele"). Entra no Resumo final, na cópia, no SRT e no pacote."""
import copy
import json

import pytest

from revisor import export, review


def _rev():
    return {
        "project": "Ana 21-10", "key": "ana 21-10", "updated": "2026-10-21 10:00:00",
        "videos": [
            {"id": "a1b2c3", "file": "01 Aula.mp4", "duration": 60.0, "fps": "30000/1001",
             "general": {"text": "Aumentar o áudio geral do vídeo.", "selected": True,
                         "created": "2026-10-21 10:00:00", "updated": "2026-10-21 10:00:00"},
             "comments": [{"cid": "c1", "frame": 60, "text": "Texto entra antes da fala.", "selected": True,
                           "with_frame": True, "updated": "2026-10-21 10:00:00"}]},
            {"id": "d4e5f6", "file": "02 Aula.mp4", "duration": 60.0, "fps": "30000/1001",
             "general": {"text": "Ajustar a cor da pele.", "selected": True}, "comments": []},
            {"id": "g7h8i9", "file": "03 Aula.mp4", "duration": 60.0, "fps": "30000/1001",
             "general": {"text": "   ", "selected": True}, "comments": []},          # vazio: não conta
        ],
    }


def test_linhas_do_resumo_final_e_copia():
    rows = export.comment_rows(_rev())
    assert [(r["n"], r["tc"], r.get("general", False)) for r in rows] == [
        (1, "Geral", True), (1, "00:00:02", False), (2, "Geral", True)]
    g = rows[0]
    assert g["frame"] is None and g["with_frame"] is False and g["cid"] == "ga1b2c3"
    assert export.copy_text(rows).splitlines() == [
        "Vídeo 01 · Geral · Aumentar o áudio geral do vídeo.",
        "Vídeo 01 · 00:00:02 · Texto entra antes da fala.",
        "Vídeo 02 · Geral · Ajustar a cor da pele."]
    assert export.comment_count(_rev()) == 3
    assert [review.comment_total(v) for v in _rev()["videos"]] == [2, 1, 0]


def test_srt_com_comentario_geral_no_comeco():
    jobs = export.srt_jobs(_rev())
    assert [j["name"] for j in jobs] == ["01 Aula.srt", "02 Aula.srt"]     # vídeo 02 só tem o geral
    t1 = export.srt_text(jobs[0]["comments"], export.rate_of(jobs[0]["video"]), 3, "CORRIGIR:")
    blocks = t1.strip().split("\n\n")
    assert blocks[0].splitlines() == ["1", "00:00:00,000 --> 00:00:02,001", "CORRIGIR: (geral) Aumentar o áudio geral do vídeo."]
    assert blocks[1].splitlines()[2] == "CORRIGIR: Texto entra antes da fala."
    t2 = export.srt_text(jobs[1]["comments"], export.rate_of(jobs[1]["video"]), 3, "")
    assert t2.splitlines()[1:3] == ["00:00:00,000 --> 00:00:03,000", "(geral) Ajustar a cor da pele."]
    # desmarcado no Resumo final: fica fora do SRT
    r = _rev()
    r["videos"][1]["general"]["selected"] = False
    assert [j["name"] for j in export.srt_jobs(r)] == ["01 Aula.srt"]


def test_pacote_leva_e_junta_o_comentario_geral(tmp_path):
    out = export.export_package(_rev() | {"entrega": "2026-10-21"}, tmp_path, lambda v, f: None)
    assert out["comments"] == 3
    data, _ = export.read_package(out["folder"])
    assert data["videos"][0]["general"]["text"] == "Aumentar o áudio geral do vídeo."
    assert data["videos"][2]["general"] is None                          # vazio não vai
    # adulterado: o geral vira texto limpo e curto
    raw = json.loads((tmp_path / out["name"] / "revisao.json").read_text(encoding="utf-8"))
    raw["videos"][0]["general"] = {"text": "x" * 9000, "selected": "sim"}
    (tmp_path / out["name"] / "revisao.json").write_text(json.dumps(raw), encoding="utf-8")
    data2, _ = export.read_package(out["folder"])
    assert len(data2["videos"][0]["general"]["text"]) == 4000 and data2["videos"][0]["general"]["selected"] is True
    # juntar: o geral mais recente vale; geral que só existe no pacote entra
    local = _rev()
    pkg = copy.deepcopy(local)
    pkg["videos"][0]["general"] = {"text": "Aumentar o áudio e tirar o chiado.", "selected": True,
                                   "updated": "2026-10-21 11:00:00"}
    local["videos"][1].pop("general")
    m = export.merge_reviews(local, pkg)
    assert m["videos"][0]["general"]["text"] == "Aumentar o áudio e tirar o chiado."
    assert m["videos"][1]["general"]["text"] == "Ajustar a cor da pele."
    assert not export.same_content(local, pkg)


def test_servidor_salva_marca_e_apaga(tmp_path, monkeypatch):
    monkeypatch.setenv("REVISOR_HOME", str(tmp_path / "home"))
    from revisor import server
    app = server.App()
    rev = _rev()
    rev["videos"][0].pop("general")
    app.review = rev
    r = app.set_general({"id": "a1b2c3", "text": "  Preciso que aumente o áudio geral do vídeo  "})
    assert r["general"] == "Preciso que aumente o áudio geral do vídeo"
    g = rev["videos"][0]["general"]
    assert g["selected"] is True and g["created"] and g["updated"]
    saved = review.find(app.reviews_root(), rev["project"])
    assert saved["videos"][0]["general"]["text"] == "Preciso que aumente o áudio geral do vídeo"
    # Resumo final: marcar/desmarcar o geral pelo cid; "all" também pega o geral
    app.final_mark({"cid": "ga1b2c3", "selected": False})
    assert rev["videos"][0]["general"]["selected"] is False
    app.final_mark({"cid": "all", "selected": True})
    assert rev["videos"][0]["general"]["selected"] is True and rev["videos"][1]["general"]["selected"] is True
    # texto vazio apaga
    assert app.set_general({"id": "a1b2c3", "text": ""})["general"] == ""
    assert "general" not in rev["videos"][0]
    with pytest.raises(server.ApiError):
        app.set_general({"id": "a1b2c3", "text": "x" * 4001})
