"""Exportar e importar a equipe (pedido do JP, 27/10): uma pessoa cadastra a equipe (30+ nomes) e
manda o arquivo para as outras importarem. Importar junta: ninguém é apagado; desativado volta a ativo."""
import pytest

from revisor import appdata


def test_ler_lista():
    texto = ("﻿# Equipe do Revisor de Vídeos\r\n"
             "Ana Souza\r\n\r\n  ana   souza \n"            # repetido (maiúscula e espaços)
             "Bruno Lima;Carla Dias\tDiego Rocha\n"         # colado de planilha
             "- Elisa Prado\n• Fábio Nunes\n"               # lista com marcadores
             "# comentário\n" + "x" * 41 + "\n")            # nome comprido demais
    assert appdata.parse_team(texto) == ["Ana Souza", "Bruno Lima", "Carla Dias", "Diego Rocha",
                                         "Elisa Prado", "Fábio Nunes"]
    assert appdata.parse_team("") == [] and appdata.parse_team(None) == []


def test_exportar_e_importar_em_outro_computador(tmp_path, monkeypatch):
    from revisor import server
    # computador 1: cadastra 32 pessoas, desativa uma e exporta
    monkeypatch.setenv("REVISOR_HOME", str(tmp_path / "pc1"))
    app = server.App()
    nomes = [f"Pessoa {k:02d} Ávila" for k in range(1, 33)]
    r = app.settings_editors({"op": "import", "text": "\n".join(nomes)})
    assert len(r["added"]) == 32 and not r["already"]
    app.settings_editors({"op": "toggle", "name": "Pessoa 05 Ávila"})
    txt = appdata.team_txt()
    assert txt.startswith(appdata.TEAM_FILE_HEAD + "\n") and txt.endswith("Pessoa 32 Ávila\n")
    assert "Pessoa 05" not in txt and txt.count("\n") == 32       # cabeçalho + 31 ativos
    (tmp_path / "Equipe.txt").write_bytes(txt.encode("utf-8"))

    # computador 2: já tinha 2 pessoas (uma desativada) e importa o arquivo
    monkeypatch.setenv("REVISOR_HOME", str(tmp_path / "pc2"))
    app2 = server.App()
    app2.settings_editors({"op": "add", "name": "Mônica Lima"})
    app2.settings_editors({"op": "add", "name": "pessoa 07 ávila"})
    app2.settings_editors({"op": "toggle", "name": "pessoa 07 ávila"})
    r = app2.settings_editors({"op": "import", "text": (tmp_path / "Equipe.txt").read_text(encoding="utf-8")})
    assert len(r["added"]) == 30 and r["reactivated"] == ["pessoa 07 ávila"] and not r["already"]
    eds = appdata.load_settings()["editors"]
    assert len(eds) == 32 and eds[0]["name"] == "Mônica Lima"                 # ninguém foi apagado
    assert all(e["active"] for e in eds)
    assert len(appdata.active_editors()) == 32
    # importar de novo não duplica
    r = app2.settings_editors({"op": "import", "names": ["Mônica Lima", "Pessoa 01 Ávila"]})
    assert not r["added"] and len(r["already"]) == 2 and len(appdata.load_settings()["editors"]) == 32


def test_importar_vazio_ou_grande_demais(tmp_path, monkeypatch):
    from revisor import server
    monkeypatch.setenv("REVISOR_HOME", str(tmp_path / "home"))
    app = server.App()
    with pytest.raises(server.ApiError, match="Nenhum nome"):
        app.settings_editors({"op": "import", "text": "# só cabeçalho\n\n"})
    with pytest.raises(server.ApiError, match="grande demais"):
        app.settings_editors({"op": "import", "text": "\n".join(f"P{k}" for k in range(appdata.TEAM_MAX + 1))})
    assert appdata.load_settings()["editors"] == []


def test_rota_do_arquivo(tmp_path, monkeypatch):
    """GET /api/settings/equipe.txt baixa o arquivo (UTF-8, com acento)."""
    import http.client
    import threading
    from http.server import ThreadingHTTPServer

    from revisor import server
    monkeypatch.setenv("REVISOR_HOME", str(tmp_path / "home"))
    appdata.save_settings({"editors": [{"name": "Lúcia", "active": True}, {"name": "Ivo", "active": False}]})
    srv = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        c = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=10)
        c.request("GET", "/api/settings/equipe.txt", headers={"Host": "127.0.0.1"})
        resp = c.getresponse()
        body = resp.read().decode("utf-8")
        assert resp.status == 200 and "attachment" in resp.getheader("Content-Disposition")
        assert body.splitlines()[1:] == ["Lúcia"]
    finally:
        srv.shutdown()
