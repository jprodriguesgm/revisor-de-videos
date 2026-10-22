"""Analisar de novo (pedido do JP, 22/10): o vídeo que volta corrigido com o MESMO nome e a MESMA duração
tinha o mesmo id e abria a análise antiga do cache. Agora:
- o app percebe sozinho que o arquivo é outro (tamanho) e analisa de novo;
- o botão "Analisar de novo" refaz um vídeo (ou a pasta) do zero;
- nada disso mexe no editor, nos comentários, na entrega nem nas horas do mês."""
import json
import os
import subprocess
import time

from conftest import ffmpeg, video_codec
from test_fila import _req, _start, _wait_all_done, needs_ffmpeg, srv  # noqa: F401 (fixture)

from revisor import analyze


def _video(path, freq=440, dur=6, color="testsrc2"):
    subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    f"{color}=size=320x180:rate=30000/1001:duration={dur}", "-f", "lavfi", "-i",
                    f"sine=frequency={freq}:sample_rate=48000:duration={dur}", *video_codec(),
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path)], check=True)


def _horas(m):
    """(nº de vídeos, segundos editados, por editor) do relatório do mês, sem as datas de leitura."""
    keep = {k: v for k, v in m.items() if k not in ("reviews_read", "duplicates", "dirs", "report_dir", "reviews_dir")}
    txt = json.dumps(keep, sort_keys=True)
    return (len(txt), txt)


def _analysis(home, vid):
    return json.loads((home / "home" / "cache" / vid / "analysis.json").read_text(encoding="utf-8"))


def test_stale_helpers(tmp_path):
    f = tmp_path / "a.mp4"
    f.write_bytes(b"x" * 100)
    a = {"source": analyze.source_of(f)}
    assert a["source"]["size"] == 100
    assert not analyze.is_stale(a, f)
    f.write_bytes(b"y" * 120)                    # mesmo nome, outro arquivo
    assert analyze.is_stale(a, f)
    assert not analyze.is_stale({}, f)          # análise antiga sem "source": não dá para saber
    assert not analyze.is_stale(a, None)        # vídeo não está neste computador
    assert not analyze.mark_reanalyze(tmp_path / "cache", "abc")   # sem cache: nada a marcar
    # análise antiga, sem o tamanho (caso real do JP, 22/10): vale a data do arquivo × hora da análise
    old = {"analyzed_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() - 3600))}
    os.utime(f, (time.time() - 7200, time.time() - 7200))
    assert not analyze.is_stale(old, f)          # arquivo de antes da análise: vale
    os.utime(f, None)                            # arquivo salvo agora, depois da análise: é outro
    assert analyze.is_stale(old, f)
    os.utime(f, (time.time() + 86400, time.time() + 86400))
    assert not analyze.is_stale(old, f)          # data no futuro (relógio errado): não usa
    assert not analyze.is_stale({"analyzed_at": "?"}, tmp_path / "nao_existe.mp4")
    (tmp_path / "cache" / "abc").mkdir(parents=True)
    assert analyze.mark_reanalyze(tmp_path / "cache", "abc")
    assert analyze.marked(tmp_path / "cache", "abc")


@needs_ffmpeg
def test_reanalisar_botao_e_arquivo_trocado(srv):  # noqa: F811
    port, tmp, server = srv
    pasta = tmp / "Ana 22-10"
    pasta.mkdir()
    _video(pasta / "01 Aula.mp4")
    _video(pasta / "02 Aula.mp4", freq=660)
    st, r = _start(port, pasta, "Ana")
    assert st == 200, r
    _wait_all_done(port)
    st, v = _req(port, "GET", "/api/video?n=1")
    vid = v["video"]["id"]
    ver1 = v["ver"]
    assert v["ready"] and ver1
    a1 = _analysis(tmp, vid)
    assert a1["source"]["size"] == (pasta / "01 Aula.mp4").stat().st_size
    # editor e comentário antes
    assert _req(port, "POST", "/api/review/editor", {"id": vid, "editor": "Bia"})[0] == 200
    assert _req(port, "POST", "/api/comment", {"id": vid, "frame": 30, "text": "trocar o slide"})[0] == 200
    st, m1 = _req(port, "GET", "/api/month?m=2026-10")
    assert st == 200

    # 1) botão: analisar de novo só o vídeo 01
    time.sleep(1.1)                              # analyzed_at muda de segundo
    st, res = _req(port, "POST", "/api/reanalyze", {"id": vid})
    assert st == 200 and res["videos"] == 1 and not res["queued"], res
    _wait_all_done(port)
    st, v2 = _req(port, "GET", "/api/video?n=1")
    assert v2["ready"] and v2["ver"] != ver1          # análise nova (endereço das imagens muda)
    assert v2["video"]["editor"] == "Bia"
    assert [c["text"] for c in v2["comments"]] == ["trocar o slide"]
    assert not analyze.marked(server.APP.cache_root(), vid)
    st, m2 = _req(port, "GET", "/api/month?m=2026-10")
    assert _horas(m2) == _horas(m1) and _horas(m1)[0] > 0       # horas do mês iguais
    st, v_b = _req(port, "GET", "/api/video?n=2")
    a2b = _analysis(tmp, v_b["video"]["id"])

    # 2) o vídeo 01 volta "corrigido": outro conteúdo, mesmo nome e mesma duração (mesmo id)
    _video(pasta / "01 Aula.mp4", color="smptebars")
    st, sc = _req(port, "GET", "/api/folder?path=" + str(pasta).replace(" ", "%20"))
    assert st == 200
    st, r = _start(port, pasta, "Ana")
    assert st == 200, r
    _wait_all_done(port)
    st, v3 = _req(port, "GET", "/api/video?n=1")
    assert v3["video"]["id"] == vid                    # mesmo id: conta uma vez só no mês
    a3 = _analysis(tmp, vid)
    assert a3["source"]["size"] == (pasta / "01 Aula.mp4").stat().st_size
    assert a3["analyzed_at"] != a1["analyzed_at"] or a3["source"] != a1["source"]
    assert v3["video"]["editor"] == "Bia" and len(v3["comments"]) == 1
    # o vídeo 02 não mudou: continua a análise do cache
    assert _analysis(tmp, v_b["video"]["id"])["analyzed_at"] == a2b["analyzed_at"]
    st, m3 = _req(port, "GET", "/api/month?m=2026-10")
    assert _horas(m3) == _horas(m1)                               # trocado com o mesmo id: conta uma vez

    # 2b) análise antiga (sem o tamanho, de antes de 22/10) e o vídeo salvo depois dela: refaz sozinho
    jp = tmp / "home" / "cache" / vid / "analysis.json"
    old = json.loads(jp.read_text(encoding="utf-8"))
    old.pop("source", None)
    old["analyzed_at"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() - 3600))
    jp.write_text(json.dumps(old), encoding="utf-8")
    os.utime(pasta / "01 Aula.mp4", None)
    margem = analyze.STALE_MARGIN_S
    analyze.STALE_MARGIN_S = 0          # no teste tudo acontece em segundos (na vida real são minutos/dias)
    try:
        st, v_old = _req(port, "GET", "/api/video?n=1")
        assert not v_old["ready"] and v_old["stale"]      # a tela oferece "Analisar este vídeo de novo"
        st, r = _start(port, pasta, "Ana")
        assert st == 200, r
        _wait_all_done(port)
    finally:
        analyze.STALE_MARGIN_S = margem
    a4 = _analysis(tmp, vid)
    assert a4["source"]["size"] == (pasta / "01 Aula.mp4").stat().st_size and a4["analyzed_at"] != old["analyzed_at"]
    st, v_new = _req(port, "GET", "/api/video?n=1")
    assert v_new["ready"]

    # 3) pasta toda
    st, res = _req(port, "POST", "/api/reanalyze", {"id": "all"})
    assert st == 200 and res["videos"] == 2
    _wait_all_done(port)
    st, v4 = _req(port, "GET", "/api/video?n=2")
    assert v4["ready"]

    # proteções
    assert _req(port, "POST", "/api/reanalyze", {"id": "../x"})[0] == 400
    assert _req(port, "POST", "/api/reanalyze", {"id": "abc123"})[0] == 404
