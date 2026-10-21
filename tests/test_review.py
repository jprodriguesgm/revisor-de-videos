"""Etapa 4: tela de revisão — itens, listas, avisos ignorados, comentários, frames, gráficos,
conta-gotas, trecho de 8 s e vídeo com "Range" (o player do navegador pula no tempo assim)."""
import http.client
import json
import os
import shutil
import subprocess
import threading
import time
from http.server import ThreadingHTTPServer

import pytest

from conftest import PROJ, ffmpeg, video_codec
from revisor import analyze, media, summary


def _a():
    """Análise mínima com frames de verdade (lista de 2, texto solto, corte, avisos)."""
    return {
        "id": "x", "file": "01 Aula.mp4", "duration": 100.0, "fps": "30000/1001", "frames": 2997,
        "width": 1920, "height": 1080, "settings_used": {"group_gap_s": 8.0},
        "events": [
            {"kind": "cut", "score": 900.0, "group": None, "frame": 150, "show_frame": 150, "time": 5.0, "tc": "00:00:05",
             "region": [0, 0, 1, 1]},
            {"kind": "text_in", "score": 900.0, "group": 1, "frame": 180, "show_frame": 189, "time": 6.0,
             "region": [0.1, 0.1, 0.3, 0.1], "extra": {"until_frame": 400, "on_screen_s": 7.3}},
            {"kind": "text_in", "score": 900.0, "group": 1, "frame": 240, "show_frame": 249, "time": 8.0,
             "region": [0.1, 0.25, 0.3, 0.1], "extra": {"until_frame": 400, "on_screen_s": 5.3}},
            {"kind": "text_out", "score": 900.0, "group": None, "frame": 400, "show_frame": 409, "time": 13.3,
             "region": [0.1, 0.1, 0.3, 0.25], "extra": {"pair_of_frame": 180}},
            {"kind": "text_in", "score": 900.0, "group": None, "frame": 600, "show_frame": 609, "time": 20.0,
             "region": [0.1, 0.8, 0.4, 0.05]},
            {"kind": "spelling", "score": 10000.0, "group": None, "frame": 630, "show_frame": 630, "time": 21.0,
             "tc": "00:00:21", "note": "ortografia: 'Previdênsia' → Previdência", "region": [0.1, 0.8, 0.2, 0.05],
             "extra": {"word": "Previdênsia", "suggestions": ["Previdência"], "line": "Previdênsia Social"}},
            {"kind": "freeze", "score": 10000.0, "group": None, "frame": 900, "show_frame": 900, "time": 30.0,
             "tc": "00:00:30", "note": "imagem congelada 9,9 s"},
        ],
        "audio": {"min_db": -60.0, "min_time": 1.0, "peak_dbfs": -2.0, "peak_time": 3.0, "avg_db": -20.0,
                  "envelope_step": 0.1, "envelope_db": [-30] * 1000,
                  "events": [{"kind": "clip", "start": 40.0, "end": 40.1, "value": 0, "note": "áudio estourando"},
                             {"kind": "speech_cut", "start": 50.0, "end": 50.05, "value": 14, "note": "corte"}]},
        "vinheta": {"warnings": [{"kind": "vinheta_final_cortada", "frame": 5000, "note": "vinheta final cortada"}]},
    }


def test_itens_da_revisao():
    r = summary.review_items(_a(), 55)
    kinds = [(it["kind"], it["frame"], it["warn"]) for it in r["items"]]
    # lista de 2 = um item (mostra o último passo); saída de texto com par some; corte fica à parte
    assert kinds == [("list", 249, False), ("text_in", 609, False), ("spelling", 630, True),
                     ("freeze", 900, True), ("clip", 1198, True), ("vinheta_final_cortada", 2996, True)]
    lst = r["items"][0]
    assert [s["frame"] for s in lst["steps"]] == [189, 249] and lst["label"] == "lista · 2 itens"
    assert lst["region"] == [0.1, 0.1, 0.3, 0.25]                       # caixa das duas linhas
    assert lst["note"] == "na tela por 7,3 s"
    assert r["cuts"] == [{"frame": 150, "tc": "00:00:05"}]
    assert r["audio_marks"][0]["kind"] == "speech_cut"                  # marca, não aviso
    sp = r["items"][2]
    assert sp["key"] == "spelling:previdensia" and sp["extra"]["suggestions"] == ["Previdência"]
    assert [it["i"] for it in r["items"]] == list(range(6))


def test_ignorar_aviso_tira_da_contagem():
    a = _a()
    assert summary.counts_of(a, 55)["warnings"] == 4
    keys = [w["key"] for w in summary.warnings_of(a)]
    assert keys == ["spelling:previdensia", "freeze:900", "audio_clip:1198", "vinheta_final_cortada:2996"]
    r = summary.review_items(a, 55, dismissed=["freeze:900"])
    assert r["counts"]["warnings"] == 3
    fr = [it for it in r["items"] if it["kind"] == "freeze"][0]
    assert fr["dismissed"] is True                                      # continua na lista, apagado
    assert summary.video_row(a, 55, dismissed=["freeze:900"])["counts"]["warnings"] == 3


def test_juntar_listas_sem_reanalisar():
    a = _a()
    assert analyze.regroup_lists(a, 8.0) is False                       # já está com 8 s
    assert analyze.regroup_lists(a, 0.0) is True                        # "não juntar"
    texts = [e for e in a["events"] if e["kind"] == "text_in"]
    assert all(e["group"] is None for e in texts)
    kinds = [it["kind"] for it in summary.review_items(a, 55)["items"] if not it["warn"]]
    assert kinds == ["text_in", "text_in", "text_in"]
    assert analyze.regroup_lists(a, 8.0) is True
    assert [e["group"] for e in a["events"] if e["kind"] == "text_in"][:2] == [1, 1]
    out = [e for e in a["events"] if e["kind"] == "text_out"][0]
    assert out["extra"]["pair_of_frame"] in (180, 240)                  # saída volta a virar duração
    assert [(e.get("extra") or {}).get("until_frame") for e in a["events"] if e["kind"] == "text_in"] == [400, 400, None]
    assert a["settings_used"]["group_gap_s"] == 8.0


# ---------------------------------------------------------------- de ponta a ponta (vídeo pequeno)

def _has_ffmpeg() -> bool:
    try:
        ffmpeg()
        return True
    except Exception:
        return False


needs_ffmpeg = pytest.mark.skipif(not _has_ffmpeg(), reason="sem FFmpeg")


@pytest.fixture()
def app_srv(tmp_path, monkeypatch):
    monkeypatch.setenv("REVISOR_HOME", str(tmp_path / "home"))
    from revisor import server
    server.APP.__init__()                      # estado limpo (o APP é do módulo)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield httpd.server_address[1], tmp_path, server
    if server.APP.job:
        server.APP.job.cancel()
    httpd.shutdown()


def _req(port, method, path, body=None, headers=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
    h = {"Host": f"127.0.0.1:{port}"}
    if body is not None:
        h["Content-Type"] = "application/json"
    h.update(headers or {})
    c.request(method, path, body=json.dumps(body) if body is not None else None, headers=h)
    r = c.getresponse()
    return r.status, r.read(), dict(r.getheaders())


@needs_ffmpeg
def test_revisao_de_ponta_a_ponta(app_srv):
    port, tmp, server = app_srv
    pasta = tmp / PROJ
    pasta.mkdir()
    subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                    "testsrc2=size=640x360:rate=30000/1001:duration=6", "-f", "lavfi", "-i",
                    "sine=frequency=440:sample_rate=48000:duration=6", *video_codec(), "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-shortest", str(pasta / "01 Teste.mp4")], check=True)
    st, data, _ = _req(port, "POST", "/api/start", {"folder": str(pasta), "professor": "Ana", "entrega": "19/10/2026",
                                                    "transcribe": False})
    assert st == 200, data
    for _ in range(240):
        st, data, _ = _req(port, "GET", "/api/job")
        if json.loads(data)["state"] in ("done", "error"):
            break
        time.sleep(0.5)
    assert json.loads(data)["state"] == "done"

    st, data, _ = _req(port, "GET", "/api/video?n=1")
    v = json.loads(data)
    assert st == 200 and v["ready"] and v["meta"]["width"] == 640 and v["meta"]["has_video"]
    vid = v["video"]["id"]
    assert v["scope"]["targets"]["R"]["angle"] == pytest.approx(103.0, abs=1.5)    # Rec.709

    # frames: miniatura e cheio (feitos na hora e guardados no cache, com cache do navegador)
    st, jpg, hd = _req(port, "GET", f"/api/frame.jpg?id={vid}&f=60&s=full")
    assert st == 200 and jpg[:2] == b"\xff\xd8" and "max-age" in hd["Cache-Control"]
    st, jpg, _ = _req(port, "GET", f"/api/frame.jpg?id={vid}&f=60&s=thumb")
    assert st == 200 and jpg[:2] == b"\xff\xd8"
    st, _, _ = _req(port, "GET", "/api/frame.jpg?id=../../x&f=1")
    assert st == 400                                                    # nada de caminho no id
    # gráficos do frame e conta-gotas (vídeo original)
    for k in ("luma", "parade", "vector"):
        st, png, _ = _req(port, "GET", f"/api/fscope.png?id={vid}&f=60&k={k}")
        assert st == 200 and png[:4] == b"\x89PNG"
    st, data, _ = _req(port, "POST", "/api/pick", {"id": vid, "f": 60, "x": 5000, "y": -3})
    p = json.loads(data)
    assert st == 200 and p["x"] == 639 and p["y"] == 0 and 16 <= p["Y"] <= 235   # ponto fora vira a borda

    # vídeo original com Range (o <video> pede pedaços)
    st, part, hd = _req(port, "GET", f"/api/media?id={vid}", headers={"Range": "bytes=0-99"})
    assert st == 206 and len(part) == 100 and hd["Content-Range"].startswith("bytes 0-99/")
    size = int(hd["Content-Range"].split("/")[1])
    st, part, hd = _req(port, "GET", f"/api/media?id={vid}", headers={"Range": "bytes=-10"})
    assert st == 206 and len(part) == 10 and hd["Content-Range"] == f"bytes {size - 10}-{size - 1}/{size}"
    st, _, _ = _req(port, "GET", f"/api/media?id={vid}", headers={"Range": f"bytes={size + 5}-"})
    assert st == 416
    st, _, _ = _req(port, "GET", "/api/media?id=0123456789abcdef")
    assert st == 404                                                    # só vídeos da revisão aberta
    # trecho de 8 s (quando o navegador não toca o original)
    st, mp4, hd = _req(port, "GET", f"/api/clip?id={vid}&f=90&fmt=mp4")
    enc = media.h264_encoder()
    if enc is None:
        assert st >= 400                                                # sem H.264: erro claro, não trava
    elif st != 200 and enc == "h264_videotoolbox" and os.environ.get("CI"):
        print("AVISO: VideoToolbox não codifica nesta máquina virtual do GitHub (no Mac de verdade, sim)")
    else:
        assert st == 200 and hd["Content-Type"] == "video/mp4" and mp4[4:8] == b"ftyp"

    # comentário: um por frame; texto vazio apaga; fica salvo na revisão
    st, data, _ = _req(port, "POST", "/api/comment", {"id": vid, "frame": 60, "text": "Trocar o slide", "source": "livre"})
    cs = json.loads(data)["comments"]
    assert st == 200 and len(cs) == 1 and cs[0]["selected"] and cs[0]["with_frame"]
    _req(port, "POST", "/api/comment", {"id": vid, "frame": 60, "text": "Trocar o slide 3"})
    st, data, _ = _req(port, "POST", "/api/comment", {"id": vid, "frame": 12, "text": "Outro"})
    assert [c["frame"] for c in json.loads(data)["comments"]] == [12, 60]
    st, data, _ = _req(port, "GET", "/api/video?n=1")
    assert [c["text"] for c in json.loads(data)["comments"]] == ["Outro", "Trocar o slide 3"]
    _req(port, "POST", "/api/comment", {"id": vid, "frame": 12, "text": "  "})
    saved = json.loads(next((tmp / "home" / "revisoes").glob("*/revisao.json")).read_text(encoding="utf-8"))
    assert [c["text"] for c in saved["videos"][0]["comments"]] == ["Trocar o slide 3"]
    st, _, _ = _req(port, "POST", "/api/comment", {"id": "outro", "frame": 1, "text": "x"})
    assert st == 404

    # ignorar / desfazer
    st, data, _ = _req(port, "POST", "/api/dismiss", {"id": vid, "key": "freeze:10"})
    assert json.loads(data)["dismissed"] == ["freeze:10"]
    st, data, _ = _req(port, "POST", "/api/dismiss", {"id": vid, "key": "freeze:10", "undo": True})
    assert json.loads(data)["dismissed"] == []
    # ajustes sem reanalisar
    st, _, _ = _req(port, "POST", "/api/review/adjust", {"group_gap_s": 5})
    assert st == 400
    st, _, _ = _req(port, "POST", "/api/review/adjust", {"group_gap_s": 0, "sensitivity": 70})
    assert st == 200
    st, data, _ = _req(port, "GET", "/api/video?n=1")
    assert json.loads(data)["review"]["group_gap_s"] == 0.0
    # aceitar palavra: vai para a lista própria
    st, data, _ = _req(port, "POST", "/api/accept", {"word": "Autoatenção"})
    assert st == 200
    assert "Autoatenção" in (tmp / "home" / "lista_propria.txt").read_text(encoding="utf-8")
    st, _, _ = _req(port, "POST", "/api/accept", {"word": "duas palavras"})
    assert st == 400


def test_trechos_de_slide_na_linha_do_tempo():
    from revisor import summary
    def cut(f, kind):
        return {"kind": "cut", "frame": f, "extra": {"transition": {"kind": kind}}}
    a = {"frames": 5000, "content": {"end_frame": 4800}, "events": [
        cut(100, "outro"), cut(300, "entra"), cut(600, "sai"),
        cut(900, "corte_seco"), {"kind": "slide_transition", "frame": 900, "note": "slide entrou com corte seco"},
        cut(1200, "sai"), cut(2000, "entra")]}
    assert summary.slide_spans(a) == [[300, 600], [900, 1200], [2000, 4800]]


def test_slides_navegaveis():
    from revisor import summary
    def cut(f, kind):
        return {"kind": "cut", "frame": f, "extra": {"transition": {"kind": kind}}}
    a = {"frames": 5000, "content": {"end_frame": 4800}, "events": [
        cut(300, "entra"), cut(450, "outro"), cut(600, "sai"), cut(2000, "entra")]}
    pages = summary.slide_pages(a)
    assert [p["frame"] for p in pages] == [315, 452, 2015]          # depois da transição / do corte seco
    assert [p["label"] for p in pages] == ["slide 1 de 3", "slide 2 de 3", "slide 3 de 3"]
    assert all(p["kind"] == "slide" and not p["warn"] for p in pages)
