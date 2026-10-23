"""Conferir correções da rodada anterior (pedido do JP, 22/10): o frame antigo ao lado do novo, no ponto
equivalente achado pelo áudio, e "corrigido / não corrigido"."""
import os
import subprocess
import time

import numpy as np

from conftest import ffmpeg, video_codec
from revisor import rounds
from test_fila import _req, _start, _wait_all_done, needs_ffmpeg, srv  # noqa: F401 (fixture)

# fala "de mentira": volume que sobe e desce sem se repetir (para o áudio ter uma assinatura)
VOZ = "aevalsrc='sin(2*PI*220*t)*(0.15+0.85*abs(sin(2*PI*0.37*t))*abs(sin(2*PI*0.113*t+1)))':s=48000"


def test_map_time_acha_o_ponto_mesmo_com_trecho_a_mais():
    rng = np.random.default_rng(3)
    env = list((rng.normal(-30, 8, 1200)).astype(int))           # 120 s em janelas de 0,1 s
    old = {"audio": {"envelope_db": env, "envelope_step": 0.1}}
    fp = rounds.fingerprint(old, 50.0)
    assert fp and abs(fp["t"] - 50.0) < 1e-6
    new = {"audio": {"envelope_db": [-60] * 30 + env, "envelope_step": 0.1}}   # 3 s a mais no começo
    t, c = rounds.map_time(fp, new)
    assert abs(t - 53.0) < 0.15 and c > 0.95
    assert rounds.map_time(fp, {"audio": {"envelope_db": list(rng.normal(-30, 8, 1200).astype(int)),
                                          "envelope_step": 0.1}}) is None      # outro áudio: não acha
    silent = {"audio": {"envelope_db": [-90] * 400, "envelope_step": 0.1}}
    assert rounds.map_time(rounds.fingerprint(silent, 10.0), silent) is None


def _video(path, dur, extra_s=0.0, color="testsrc2"):
    """Vídeo com a 'fala'; extra_s = segundos de outra imagem/silêncio inseridos no começo (editor mexeu)."""
    vf = f"{color}=size=320x180:rate=30000/1001:duration={dur}"
    af = f"{VOZ}:d={dur}"
    if extra_s:
        vf = (f"color=c=blue:size=320x180:rate=30000/1001:duration={extra_s}[va];{vf}[vb];[va][vb]concat=n=2:v=1:a=0")
        af = f"anullsrc=r=48000:cl=mono:d={extra_s}[x];{VOZ}:d={dur}[y];[x][y]concat=n=2:v=0:a=1"
    subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-filter_complex", f"{vf}[v];{af}[a]",
                    "-map", "[v]", "-map", "[a]", *video_codec(), "-pix_fmt", "yuv420p", "-c:a", "aac", str(path)],
                   check=True)


@needs_ffmpeg
def test_conferir_correcoes(srv):  # noqa: F811
    port, tmp, server = srv
    pasta = tmp / "Ana 22-10"
    pasta.mkdir()
    _video(pasta / "01 Aula.mp4", 30)
    assert _start(port, pasta, "Ana")[0] == 200
    _wait_all_done(port)
    st, v = _req(port, "GET", "/api/video?n=1")
    vid = v["video"]["id"]
    assert not (v.get("checks") or {}).get("total")
    st, r = _req(port, "POST", "/api/comment", {"id": vid, "frame": 450, "text": "trocar o slide", "tag": "slide"})
    c = r["comments"][0]
    assert c["afp"]["step"] == 0.1 and len(c["afp"]["env"]) > 100
    for _ in range(50):                                  # a cópia do frame é feita em segundo plano
        if _req(port, "GET", f"/api/snap.jpg?id={vid}&f=450")[0] == 200:
            break
        time.sleep(0.2)
    assert _req(port, "GET", f"/api/snap.jpg?id={vid}&f=450")[0] == 200

    # o editor mexeu no começo: 2 s a mais → outra duração = rodada 2 (o antigo fica guardado)
    os.remove(pasta / "01 Aula.mp4")
    _video(pasta / "01 Aula.mp4", 30, extra_s=2.0, color="smptebars")
    assert _start(port, pasta, "Ana")[0] == 200
    _wait_all_done(port)
    st, v2 = _req(port, "GET", "/api/video?n=1")
    assert v2["video"]["round"] == 2 and v2["checks"]["total"] == 1 and v2["checks"]["done"] == 0
    st, ck = _req(port, "GET", "/api/checks?n=1")
    it = ck["items"][0]
    assert it["text"] == "trocar o slide" and it["tag"] == "slide" and it["snap"] and not it["approx"]
    assert abs(it["frame"] - (450 + 60)) <= 4, it          # 2 s × 29,97 = 60 frames depois
    # não corrigido → vira comentário no vídeo novo, no ponto achado
    st, r = _req(port, "POST", "/api/check", {"src": it["src"], "cid": it["cid"], "check": "no",
                                              "id": v2["video"]["id"], "frame": it["frame"]})
    assert st == 200 and r["comments"][0]["text"] == "Não corrigido: trocar o slide" and r["comments"][0]["tag"] == "slide"
    st, v3 = _req(port, "GET", "/api/video?n=1")
    assert v3["checks"]["done"] == 1 and v3["checks"]["no"] == 1
    # o "não corrigido" (feito agora) não vira comentário da rodada anterior
    st, ck2 = _req(port, "GET", "/api/checks?n=1")
    assert len(ck2["items"]) == 1 and ck2["items"][0]["check"] == "no"
    # desfazer e marcar corrigido
    assert _req(port, "POST", "/api/check", {"src": it["src"], "cid": it["cid"], "check": "ok"})[0] == 200
    st, ck3 = _req(port, "GET", "/api/checks?n=1")
    assert ck3["items"][0]["check"] == "ok"
    assert _req(port, "POST", "/api/check", {"src": it["src"], "cid": "nao-existe", "check": "ok"})[0] == 404
    assert _req(port, "GET", "/api/snap.jpg?id=../x&f=1")[0] == 400


def test_rodada_anterior_no_mesmo_arquivo_trocado():
    # mesmo nome e duração (mesmo id): comentário feito ANTES de o arquivo atual ser salvo é da rodada anterior
    antes = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() - 3600))
    agora = time.strftime("%Y-%m-%d %H:%M:%S")
    v = {"id": "x1", "file": "01 Aula.mp4", "round": 1,
         "comments": [{"cid": "a", "frame": 10, "text": "velho", "created": antes},
                      {"cid": "b", "frame": 20, "text": "novo", "created": agora}]}
    rev = {"videos": [v]}
    a = {"source": {"size": 1, "mtime": time.time() - 600}}
    assert [c["cid"] for _, c in rounds.previous_comments(rev, v, a)] == ["a"]
    assert rounds.previous_comments(rev, v, {"source": {"size": 1}}) == []      # análise antiga sem a data
