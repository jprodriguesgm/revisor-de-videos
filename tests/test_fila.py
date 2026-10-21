"""Fila de pastas (pedido do JP, 21/10): várias pastas analisadas uma depois da outra, sem parar
a análise ao trocar a revisão aberta. Também: trecho com duração escolhida e "próxima pasta"."""
import http.client
import json
import os
import subprocess
import threading
import time
from http.server import ThreadingHTTPServer

import pytest

from conftest import ffmpeg, video_codec
from revisor import media


def _has_ffmpeg() -> bool:
    try:
        ffmpeg()
        return True
    except Exception:
        return False


needs_ffmpeg = pytest.mark.skipif(not _has_ffmpeg(), reason="sem FFmpeg")
SEP = ":" if os.name != "nt" else "-"


@pytest.fixture()
def srv(tmp_path, monkeypatch):
    monkeypatch.setenv("REVISOR_HOME", str(tmp_path / "home"))
    from revisor import server
    server.APP.__init__()
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield httpd.server_address[1], tmp_path, server
    server.APP.stop_all()
    for _ in range(100):                       # espera as análises pararem (não atrapalhar outros testes)
        if not server.APP._any_alive():
            break
        time.sleep(0.1)
    httpd.shutdown()


def _req(port, method, path, body=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
    h = {"Host": f"127.0.0.1:{port}"}
    if body is not None:
        h["Content-Type"] = "application/json"
    c.request(method, path, body=json.dumps(body) if body is not None else None, headers=h)
    r = c.getresponse()
    data = r.read()
    try:
        return r.status, json.loads(data)
    except ValueError:
        return r.status, data


def _pasta(tmp, nome, n=1, dur=6):
    p = tmp / nome
    p.mkdir()
    for k in range(n):
        subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                        f"testsrc2=size=320x180:rate=30000/1001:duration={dur}", "-f", "lavfi", "-i",
                        f"sine=frequency={440 + 50 * k}:sample_rate=48000:duration={dur}", *video_codec(),
                        "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(p / f"0{k + 1} Aula.mp4")], check=True)
    return p


def _start(port, pasta, prof):
    return _req(port, "POST", "/api/start", {"folder": str(pasta), "professor": prof, "entrega": "21/10/2026",
                                             "transcribe": False})


def _wait_all_done(port, timeout=240):
    for _ in range(timeout * 2):
        st, q = _req(port, "GET", "/api/queue")
        if q["entries"] and all(e["status"] in ("done", "error") for e in q["entries"]):
            return q
        time.sleep(0.5)
    raise AssertionError(f"a fila não terminou: {q}")


@needs_ffmpeg
def test_fila_analisa_uma_pasta_depois_da_outra(srv):
    port, tmp, server = srv
    a = _pasta(tmp, f"Ana 21{SEP}10", n=2)
    b = _pasta(tmp, f"Bruno 21{SEP}10", n=1)

    st, r = _start(port, a, "Ana")
    assert st == 200 and r["queued"] is False
    st, r = _start(port, b, "Bruno")                     # Ana ainda analisando: Bruno vai para a fila
    assert st == 200 and r["queued"] is True and r["position"] == 1 and r["running"] == a.name
    st, view = _req(port, "GET", "/api/review")
    assert view["review"]["project"] == a.name           # a revisão aberta continua a da Ana

    st, q = _req(port, "GET", "/api/queue")
    assert [e["project"] for e in q["entries"]] == [a.name, b.name]
    assert q["entries"][0]["open"] and not q["entries"][1]["open"]
    assert q["entries"][1]["status"] in ("wait", "running", "done")
    st, s = _req(port, "GET", "/api/state")
    assert s["queue"]["total"] == 2

    q = _wait_all_done(port)
    assert [e["status"] for e in q["entries"]] == ["done", "done"]
    # nunca duas ao mesmo tempo: a do Bruno começou depois que a da Ana acabou
    ja, jb = (server.APP._entry(x.name)["job"] for x in (a, b))
    assert jb.started >= ja.finished - 0.05

    # última aula da Ana → "Próxima pasta" aponta para o Bruno
    st, v = _req(port, "GET", "/api/video?n=2")
    assert v["n"] == 2 and v["next_folder"]["project"] == b.name and "pronta" in v["next_folder"]["status_text"]
    st, v = _req(port, "GET", "/api/video?n=1")
    assert v["next_folder"] is None                      # não é a última aula

    # abrir a pasta do Bruno pela fila: não reanalisa, abre no 1º vídeo pronto
    st, r = _req(port, "POST", "/api/reviews/open", {"project": b.name})
    assert st == 200 and r["folder_found"] and r["ready_n"] == 1 and r["queued"] is False
    st, view = _req(port, "GET", "/api/review")
    assert view["review"]["project"] == b.name and view["job"]["state"] == "done"
    st, q = _req(port, "GET", "/api/queue")
    assert [e["open"] for e in q["entries"]] == [False, True]
    st, v = _req(port, "GET", "/api/video?n=1")
    assert v["ready"] and v["next_folder"] is None       # Bruno é a última da fila

    # tirar da lista
    st, r = _req(port, "POST", "/api/queue/remove", {"project": a.name})
    st, q = _req(port, "GET", "/api/queue")
    assert [e["project"] for e in q["entries"]] == [b.name]


@needs_ffmpeg
def test_analisar_agora_passa_na_frente(srv):
    port, tmp, server = srv
    a = _pasta(tmp, f"Ana 22{SEP}10", n=2, dur=12)
    b = _pasta(tmp, f"Bruno 22{SEP}10")
    c = _pasta(tmp, f"Carla 22{SEP}10")
    _start(port, a, "Ana")
    _req(port, "POST", "/api/job/pause", {})               # segura a Ana (e a fila junto)
    _start(port, b, "Bruno")
    _start(port, c, "Carla")
    time.sleep(0.3)
    st, q = _req(port, "GET", "/api/queue")
    assert [(e["project"], e["status"]) for e in q["entries"]][1:] == [(b.name, "wait"), (c.name, "wait")]
    assert q["entries"][0]["status"] in ("paused", "running")

    st, r = _req(port, "POST", "/api/queue/now", {"project": c.name})
    assert st == 200
    st, q = _req(port, "GET", "/api/queue")
    order = [e["project"] for e in q["entries"]]
    assert order.index(c.name) < order.index(a.name) < order.index(b.name)   # Carla, depois Ana, depois Bruno
    q = _wait_all_done(port)
    jobs = {e: server.APP._entry(e)["job"] for e in (a.name, b.name, c.name)}
    assert jobs[c.name].started <= jobs[a.name].started <= jobs[b.name].started


@needs_ffmpeg
def test_fila_que_ficou_volta_ao_abrir(srv):
    port, tmp, server = srv
    a = _pasta(tmp, f"Ana 23{SEP}10")
    _start(port, a, "Ana")
    _wait_all_done(port)
    # o app fechou com a pasta da Ana ainda na fila (escrito como o app escreve)
    (tmp / "home" / "fila.json").write_text(json.dumps({"pending": [{"project": a.name, "folder": str(a)}]}),
                                            encoding="utf-8")
    server.APP.__init__()                                 # app aberto de novo
    st, q = _req(port, "GET", "/api/queue")
    assert q["entries"] == [] and [x["project"] for x in q["restore"]] == [a.name]
    st, s = _req(port, "GET", "/api/state")
    assert s["queue"]["restore"] == 1
    st, r = _req(port, "POST", "/api/queue/restore", {"keep": True})
    assert r["added"] == 1 and r["missing"] == []
    q = _wait_all_done(port)
    assert q["restore"] == [] and q["entries"][0]["project"] == a.name
    saved = json.loads((tmp / "home" / "fila.json").read_text(encoding="utf-8"))
    assert saved["pending"] == []                         # terminou: nada pendente
    # descartar
    (tmp / "home" / "fila.json").write_text(json.dumps({"pending": [{"project": "Outra", "folder": "/nao/existe"}]}),
                                            encoding="utf-8")
    server.APP.__init__()
    st, r = _req(port, "POST", "/api/queue/restore", {"keep": False})
    st, q = _req(port, "GET", "/api/queue")
    assert q["restore"] == []


@needs_ffmpeg
def test_trecho_com_duracao_escolhida(srv):
    port, tmp, server = srv
    a = _pasta(tmp, f"Ana 24{SEP}10", dur=20)
    _start(port, a, "Ana")
    _wait_all_done(port)
    st, v = _req(port, "GET", "/api/video?n=1")
    assert v["clip_half_s"] == 4 and 2 in v["clip_choices"]
    vid = v["video"]["id"]
    # opção fora da lista vira o padrão; opção certa fica guardada
    _req(port, "POST", "/api/settings", {"clip_half_s": 7})
    st, v = _req(port, "GET", "/api/video?n=1")
    assert v["clip_half_s"] == 4
    _req(port, "POST", "/api/settings", {"clip_half_s": 2})
    st, v = _req(port, "GET", "/api/video?n=1")
    assert v["clip_half_s"] == 2
    # trecho em MP4 (quando o navegador não toca o original): 2 s antes e 2 s depois
    st, data = _req(port, "GET", f"/api/clip?id={vid}&f=300&fmt=mp4&h=2")
    assert st == 200
    clips = list((tmp / "home" / "cache" / vid / "clips").glob("*.mp4"))
    assert len(clips) == 1 and clips[0].name.endswith("_020.mp4")
    assert media.probe(str(clips[0])).duration == pytest.approx(4.0, abs=0.3)


@needs_ffmpeg
def test_reabrir_pasta_com_video_novo_analisa_de_novo(srv):
    port, tmp, server = srv
    a = _pasta(tmp, f"Ana 25{SEP}10")
    _start(port, a, "Ana")
    _wait_all_done(port)
    # o editor mandou mais um vídeo para a mesma pasta
    subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                    "testsrc2=size=320x180:rate=30000/1001:duration=4", "-f", "lavfi", "-i",
                    "sine=frequency=700:sample_rate=48000:duration=4", *video_codec(),
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(a / "02 Nova.mp4")], check=True)
    st, r = _req(port, "POST", "/api/reviews/open", {"project": a.name})
    assert st == 200 and r["folder_found"]
    q = _wait_all_done(port)
    st, view = _req(port, "GET", "/api/review")
    assert [v["file"] for v in view["videos"]] == ["01 Aula.mp4", "02 Nova.mp4"]
    assert all(v["row"] for v in view["videos"])
    # sem mudança na pasta: só troca a revisão aberta (não analisa de novo)
    job = server.APP._entry(a.name)["job"]
    _req(port, "POST", "/api/reviews/open", {"project": a.name})
    assert server.APP._entry(a.name)["job"] is job
