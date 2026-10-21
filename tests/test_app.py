"""Etapa 3: revisão salva, resumo e servidor local (sem vídeo de verdade)."""
import http.client
import json
import threading
from http.server import ThreadingHTTPServer

import pytest

from revisor import review, summary


def test_slug_e_chave():
    assert review.slug("Carlos 21:09") == "Carlos 21-09"
    assert review.slug("a/b\\c") == "a-b-c"
    # Mac guarda acento decomposto; a chave é a mesma
    assert review.project_key("João 18:10") == review.project_key("João 18:10") == "joao 18:10"


@pytest.mark.parametrize("pasta,prof", [
    ("Carlos 21:09", "Carlos"), ("Ana Lima 9h30", "Ana Lima"), ("Bruno Zantiu 07-10", "Bruno Zantiu"),
    ("Marina 02/10", "Marina"), ("Felipe", "Felipe"),
])
def test_sugere_professor(pasta, prof):
    assert review.suggest_professor(pasta) == prof


def test_datas():
    assert review.parse_date("07/10/2026") == "2026-10-07"
    assert review.parse_date("2026-10-07") == "2026-10-07"
    assert review.parse_date("31/02/2026") is None
    assert review.fmt_date("2026-10-07") == "07/10/2026"


def test_merge_mantem_editor_e_comentarios(tmp_path):
    rev = review.new_review(tmp_path / "Carlos 21:09")
    review.merge_videos(rev, [{"id": "a", "file": "01.mp4", "duration": 10.0},
                              {"id": "b", "file": "02.mp4", "duration": 20.0}])
    rev["videos"][0]["editor"] = "Lúcia"
    rev["videos"][1]["comments"].append({"frame": 1, "text": "x"})
    # vídeo 02 corrigido (outra duração = outro id) e 03 novo
    review.merge_videos(rev, [{"id": "a", "file": "01.mp4", "duration": 10.0},
                              {"id": "c", "file": "03.mp4", "duration": 5.0}])
    ids = [v["id"] for v in rev["videos"]]
    assert ids == ["a", "c", "b"]
    assert rev["videos"][0]["editor"] == "Lúcia"
    assert rev["videos"][2]["missing"] is True and rev["videos"][2]["comments"]
    p = review.save(tmp_path, rev)
    assert p.exists()
    again = review.find(tmp_path, "Carlos 21:09")
    assert again["videos"][0]["editor"] == "Lúcia"
    assert review.list_saved(tmp_path)[0]["comments"] == 1


def test_nota_do_slide_vira_12f_do_premiere():
    assert summary.fix_note("slide saiu descendo (esperado: sobe em 9f)") == \
        "slide saiu descendo (esperado: sobe em 12f no Premiere)"
    assert "12f no Premiere ≈ 9 visíveis" in summary.fix_note("slide saiu em 4 frames de movimento (padrão: 9; mais rápido)")


def _analysis():
    return {
        "id": "x", "file": "01 Aula.mp4", "duration": 100.0, "fps": "30000/1001",
        "events": [
            {"kind": "cut", "score": 900.0, "group": None, "time": 5.0, "tc": "00:00:05"},
            {"kind": "text_in", "score": 900.0, "group": 1, "time": 6.0, "tc": "00:00:06"},
            {"kind": "text_in", "score": 900.0, "group": 1, "time": 8.0, "tc": "00:00:08"},
            {"kind": "text_in", "score": 900.0, "group": None, "time": 20.0, "tc": "00:00:20"},
            {"kind": "spelling", "score": 10000.0, "group": None, "time": 21.0, "tc": "00:00:21", "note": "ortografia"},
            {"kind": "freeze", "score": 10000.0, "group": None, "time": 30.0, "tc": "00:00:30", "note": "congelada"},
        ],
        "audio": {"min_db": -60.0, "min_time": 1.0, "peak_dbfs": -2.0, "peak_time": 3.0, "avg_db": -20.0,
                  "events": [{"kind": "clip", "start": 40.0, "end": 40.1, "value": 0, "note": "áudio estourando"},
                             {"kind": "speech_cut", "start": 50.0, "end": 50.05, "value": 14,
                              "note": "corte no meio da fala · conferir"}]},
        "vinheta": {"warnings": [{"kind": "vinheta_final_cortada", "frame": 2970, "note": "vinheta final cortada"}]},
    }


def test_contagens_e_avisos():
    a = _analysis()
    c = summary.counts_of(a, 55)
    assert c == {"frames": 2, "cuts": 1, "warnings": 4}       # lista conta 1; ortografia, congelada, áudio, vinheta
    assert summary.counts_of(a, 55, spell=False)["warnings"] == 3
    w = summary.warnings_of(a)
    assert [x["source"] for x in w] == ["texto", "imagem", "áudio", "vinheta"]
    row = summary.video_row(a, 55)
    # corte no meio da fala: só marca na forma de onda, não é aviso
    assert row["audio_marks"] == [{"time": 50.0, "tc": "00:00:50", "kind": "speech_cut", "label": "corte no meio da fala"}]
    tot = summary.audio_totals([row, {**row, "id": "y", "duration": 300.0,
                                      "audio": {**row["audio"], "min_db": -70.0, "avg_db": -10.0}}])
    assert tot["min"]["db"] == -70.0 and tot["min"]["video"] == "y"
    assert tot["avg"]["db"] == -12.5                            # ponderada pela duração


# ---------------------------------------------------------------- servidor

@pytest.fixture()
def srv(tmp_path, monkeypatch):
    monkeypatch.setenv("REVISOR_HOME", str(tmp_path / "home"))
    from revisor import server
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield httpd.server_address[1], tmp_path
    httpd.shutdown()


def _req(port, method, path, body=None, headers=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    h = {"Host": f"127.0.0.1:{port}"}
    if body is not None:
        h["Content-Type"] = "application/json"
    h.update(headers or {})
    c.request(method, path, body=json.dumps(body) if body is not None else None, headers=h)
    r = c.getresponse()
    data = r.read()
    return r.status, data


def test_servidor_basico(srv):
    port, tmp = srv
    st, data = _req(port, "GET", "/api/state")
    assert st == 200
    s = json.loads(data)
    assert s["editors"] == [] and s["review_open"] is False      # sem equipe até cadastrar
    st, data = _req(port, "GET", "/")
    assert st == 200 and b"Revisor de V" in data
    st, _ = _req(port, "GET", "/ui/fonts/ibm-plex-sans-latin-400-normal.woff2")
    assert st == 200
    # pasta que não existe
    st, data = _req(port, "GET", "/api/folder?path=" + str(tmp / "nao-existe"))
    assert st == 200 and json.loads(data)["scan"]["error"] == "Pasta não encontrada."
    # pasta vazia
    (tmp / "vazia").mkdir()
    st, data = _req(port, "GET", "/api/folder?path=" + str(tmp / "vazia"))
    assert "Nenhum vídeo" in json.loads(data)["scan"]["error"]
    st, data = _req(port, "POST", "/api/start", {"folder": str(tmp / "vazia"), "professor": "X", "entrega": "01/10/2026"})
    assert st == 400


def test_servidor_protecoes(srv):
    port, tmp = srv
    st, _ = _req(port, "GET", "/api/state", headers={"Host": "exemplo.com"})
    assert st == 403                                    # outro site não conversa com o app
    st, _ = _req(port, "GET", "/ui/../server.py")
    assert st == 404
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    c.request("POST", "/api/settings", body="sensitivity=1",
              headers={"Host": f"127.0.0.1:{port}", "Content-Type": "application/x-www-form-urlencoded"})
    assert c.getresponse().status == 415                # formulário de outro site é recusado
    st, data = _req(port, "POST", "/api/settings", {"sensitivity": 70, "editors": "não pode"})
    assert st == 200
    st, data = _req(port, "GET", "/api/state")
    assert json.loads(data)["settings"]["sensitivity"] == 70
