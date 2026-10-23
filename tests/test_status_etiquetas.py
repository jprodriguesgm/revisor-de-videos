"""Situação do vídeo (aprovado / volta) e etiqueta de cada comentário (pedido do JP, 22/10)."""
import json

from test_fila import _pasta, _req, _start, _wait_all_done, needs_ffmpeg, srv  # noqa: F401 (fixture)

from revisor import export, review


@needs_ffmpeg
def test_situacao_e_etiquetas(srv):  # noqa: F811
    port, tmp, server = srv
    pasta = _pasta(tmp, "Ana 22-10", n=2)
    assert _start(port, pasta, "Ana")[0] == 200
    _wait_all_done(port)
    st, v = _req(port, "GET", "/api/video?n=1")
    vid = v["video"]["id"]
    assert v["tags"]["audio"] == "Áudio" and v["video"]["status"] is None
    assert _req(port, "POST", "/api/review/editor", {"id": "all", "editor": "Bia"})[0] == 200
    # comentário com etiqueta; trocar a etiqueta sem mudar o texto; etiqueta inválida recusada
    st, r = _req(port, "POST", "/api/comment", {"id": vid, "frame": 30, "text": "subir o áudio", "tag": "audio"})
    assert st == 200 and r["comments"][0]["tag"] == "audio" and r["comments"][0]["round"] == 1
    st, r = _req(port, "POST", "/api/comment", {"id": vid, "frame": 30, "text": "subir o áudio", "tag": "corte"})
    assert r["comments"][0]["tag"] == "corte"
    assert _req(port, "POST", "/api/comment", {"id": vid, "frame": 40, "text": "x", "tag": "xpto"})[0] == 400
    st, r = _req(port, "POST", "/api/comment", {"id": vid, "frame": 60, "text": "palavra errada", "tag": "texto"})
    # situação
    assert _req(port, "POST", "/api/review/status", {"id": vid, "status": "volta"})[0] == 200
    st, v2 = _req(port, "GET", "/api/video?n=2")
    assert _req(port, "POST", "/api/review/status", {"id": v2["video"]["id"], "status": "aprovado"})[0] == 200
    assert _req(port, "POST", "/api/review/status", {"id": vid, "status": "talvez"})[0] == 400
    st, v = _req(port, "GET", "/api/video?n=1")
    assert v["video"]["status"] == "volta"
    assert [t["status"] for t in v["tabs"]] == ["volta", "aprovado"]
    st, f = _req(port, "GET", "/api/final")
    assert {x["status"] for x in f["videos"]} == {"volta", "aprovado"}
    assert sorted(r["tag"] for r in f["rows"] if r["frame"] is not None) == ["corte", "texto"]
    # relatório do mês: 1 aprovado de primeira, 1 voltou, correções por tipo
    st, m = _req(port, "GET", "/api/month?m=2026-10")
    bia = next(e for e in m["editors"] if e["name"] == "Bia")
    assert bia["approved_first"] == 1 and bia["returned"] == 1 and bia["comments"] == 2
    assert bia["tags"] == {"corte": 1, "texto": 1}
    rev = server.APP.review
    txt = export.month_txt(export.month_report([rev], "2026-10"))
    assert "1 aprovados de primeira · 1 voltaram" in txt and "Corte 1" in txt
    # tirar a situação
    assert _req(port, "POST", "/api/review/status", {"id": vid, "status": None})[0] == 200
    st, v = _req(port, "GET", "/api/video?n=1")
    assert v["video"]["status"] is None
    # pacote: situação e etiqueta vão junto; lixo é limpo
    clean = export._clean_video({"id": "abc123", "file": "a.mp4", "status": "hack", "round": "x",
                                 "comments": [{"frame": 3, "text": "t", "tag": "<script>"}]})
    assert "status" not in clean and clean["round"] == 1 and clean["comments"][0]["tag"] is None
    assert set(review.TAGS) == {"audio", "cor", "texto", "corte", "tarja", "slide", "vinheta", "outro"}
    json.dumps(f)
