"""Pedidos do JP de 23/11/2026: colar o cartão do Planner, reconhecer a revisão pelos vídeos (pasta
baixada de novo com outro nome) e usar a transcrição pronta (da pasta "Transcrições" ou adicionada à mão).
Nomes fictícios."""
import json
import time

from test_fila import _req, _start, _wait_all_done, needs_ffmpeg, srv  # noqa: F401 (fixture)
from test_reanalisar import _analysis, _video

from revisor import cartao, review, transcricao

CARD = """> ###Preenchimento do professor

Data da gravação: 01/10/2026

Nome completo do professor:  Maria Clara Souza Andrade

Nome que será utilizado na aula:  Maria Clara Souza

Matrícula: não sei

Telefone: (31) 90000-0000

E-mail: [maria.exemplo@email.com](mailto:E-mail "")

Curso:  MBA em Finanças Corporativas

Tipo do curso:  Pós Graduação

Disciplina: Valuation de Empresas

Microfundamento: Não

Início da(s) disciplina(s):  não sei
"""


# ------------------------------------------------------------------ cartão

def test_cartao_le_os_campos():
    c = cartao.parse(CARD)
    assert c["ok"]
    assert c["professor"] == "Maria Clara Souza" and c["professor_from"] == "nome_aula"
    assert c["nome_tarja"] == "Maria Clara Souza"
    assert c["curso"] == "MBA em Finanças Corporativas"
    assert c["disciplina"] == "Valuation de Empresas"
    assert c["data_gravacao"] == "2026-10-01"
    # nada de telefone, e-mail ou matrícula no resultado
    assert "90000" not in json.dumps(c) and "email" not in json.dumps(c).lower()


def test_cartao_sem_nome_da_aula_usa_o_completo_e_vazios():
    c = cartao.parse("Nome completo do professor: **João Pedro Lima**\nCurso: não sei\nDisciplina: -\n")
    assert c["professor"] == "João Pedro Lima" and c["professor_from"] == "nome_completo"
    assert c["curso"] is None and c["disciplina"] is None
    assert not cartao.parse("texto qualquer sem campos")["ok"]


def test_cartao_confere_a_data_da_pasta():
    c = cartao.parse(CARD)
    ck = cartao.check(c, "2026 11 10 Maria Clara Souza")
    assert ck == {"folder_date": "2026-11-10", "card_date": "2026-10-01", "date_mismatch": True}
    assert not cartao.check(c, "2026 10 01 Maria Clara Souza")["date_mismatch"]
    assert not cartao.check(c, "Maria Clara 21:09")["date_mismatch"]      # pasta sem data: não avisa
    assert cartao.parse_date("1/10/26") == "2026-10-01"
    assert review.suggest_professor("2026 11 10 Maria Clara Souza") == "Maria Clara Souza"


# ------------------------------------------------------------------ revisão reconhecida pelos vídeos

def test_revisao_parecida_e_apelido(tmp_path):
    root = tmp_path / "rev"
    old = review.new_review(tmp_path / "2026 11 10 Maria Clara Souza")
    old["videos"] = [{"id": f"x{i}", "file": f"0{i} Aula {i}.mp4", "duration": 60.0, "comments": []} for i in (1, 2, 3)]
    review.save(root, old)
    other = review.new_review(tmp_path / "Outra pasta")
    other["videos"] = [{"id": "y1", "file": "01 Aula 1.mp4", "duration": 60.0, "comments": []}]
    review.save(root, other)
    files = ["01 Aula 1.mp4", "02 Aula 2.mp4", "03 Aula 3.mp4"]
    sim = review.find_similar(root, "2026 11 10 Maria Clara", files)
    assert sim[0]["project"] == "2026 11 10 Maria Clara Souza" and sim[0]["match_n"] == 3
    assert all(s["project"] != "Outra pasta" for s in sim)      # 1 de 3 não chega à metade
    assert review.find(root, "2026 11 10 Maria Clara") is None
    review.link_folder(old, tmp_path / "2026 11 10 Maria Clara")
    review.save(root, old)
    got = review.find(root, "2026 11 10 Maria Clara")
    assert got and got["project"] == "2026 11 10 Maria Clara Souza"
    assert review.find_similar(root, "2026 11 10 Maria Clara", files) == []   # já ligada: não pergunta de novo


@needs_ffmpeg
def test_pasta_com_outro_nome_continua_a_revisao(srv):  # noqa: F811
    port, tmp, server = srv
    a = tmp / "2026 11 10 Maria Clara Souza"
    a.mkdir()
    _video(a / "01 Aula.mp4")
    st, r = _start(port, a, "Maria Clara Souza")
    assert st == 200, r
    _wait_all_done(port)
    st, v = _req(port, "GET", "/api/video?n=1")
    vid = v["video"]["id"]
    assert _req(port, "POST", "/api/comment", {"id": vid, "frame": 30, "text": "tarja errada"})[0] == 200
    # baixou de novo, versão corrigida (outra duração), com outro nome de pasta
    b = tmp / "2026 11 10 Maria Clara"
    b.mkdir()
    _video(b / "01 Aula.mp4", dur=7)
    st, inf = _req(port, "GET", "/api/folder?path=" + str(b).replace(" ", "%20"))
    assert st == 200 and inf["prev"] is None
    assert inf["similar"][0]["project"] == a.name and inf["folder_date"] == "2026-11-10"
    assert inf["suggest"]["professor"] == "Maria Clara"
    assert _req(port, "POST", "/api/review/link", {"project": a.name, "folder": str(b)})[0] == 200
    st, inf = _req(port, "GET", "/api/folder?path=" + str(b).replace(" ", "%20"))
    assert inf["prev"] and inf["linked"] and inf["project"] == a.name
    assert inf["suggest"]["professor"] == "Maria Clara Souza"
    st, r = _start(port, b, "Maria Clara Souza")
    assert st == 200 and r["project"] == a.name, r
    _wait_all_done(port)
    from revisor import appdata
    saved = review.find(appdata.reviews_dir(), a.name)
    assert saved["folder"] == str(b.resolve())
    assert any(int(x.get("round") or 1) == 2 for x in saved["videos"])     # o corrigido é a rodada 2
    assert any(c.get("text") == "tarja errada" for x in saved["videos"] for c in x.get("comments", []))


# ------------------------------------------------------------------ transcrição pronta

def test_importar_srt_vtt_e_json(tmp_path):
    srt = tmp_path / "a.srt"
    srt.write_text("1\n00:00:01,000 --> 00:00:03,000\nOlá pessoal, errei\n\n2\n00:00:04,000 --> 00:00:05,500\nvamos lá\n",
                   encoding="utf-8")
    d = transcricao.import_file(srt, "01 Aula.mp4", 6.0)
    assert d["aproximada"] and d["formato"] == "revisor-transcricao"
    assert [w[2] for w in d["words"]] == ["Olá", "pessoal,", "errei", "vamos", "lá"]
    assert d["words"][0][0] == 1.0 and d["words"][2][1] == 3.0
    vtt = tmp_path / "a.vtt"
    vtt.write_text("WEBVTT\n\n00:01.000 --> 00:02.000\n<v Prof>bom dia</v>\n", encoding="utf-8")
    assert [w[2] for w in transcricao.import_file(vtt, "x.mp4", 6.0)["words"]] == ["bom", "dia"]
    wj = tmp_path / "w.json"
    wj.write_text(json.dumps({"segments": [{"start": 0.5, "end": 2.0, "text": " oi gente",
                                            "words": [{"word": " oi", "start": 0.5, "end": 0.8, "probability": 0.9},
                                                      {"word": " gente", "start": 0.9, "end": 2.0, "probability": 0.8}]}]}),
                  encoding="utf-8")
    d = transcricao.import_file(wj, "x.mp4", 6.0)
    assert not d["aproximada"] and d["words"][1][:3] == [0.9, 2.0, "gente"]
    longo = tmp_path / "b.srt"
    longo.write_text("1\n00:10:00,000 --> 00:10:02,000\nfim\n", encoding="utf-8")
    try:
        transcricao.import_file(longo, "x.mp4", 6.0)
        raise AssertionError("devia recusar transcrição mais longa que o vídeo")
    except transcricao.TranscriptError as e:
        assert "outro vídeo" in str(e)


def test_procura_na_pasta_transcricoes(tmp_path):
    dia = tmp_path / "2026 11 10"
    saida = dia / "Saída"
    saida.mkdir(parents=True)
    v = saida / "01 Aula.mp4"
    v.write_bytes(b"x")
    assert transcricao.lookup(v, 10.0)["status"] == "nenhuma"
    data = transcricao.build("01 Aula.mp4", 10.0, [[1, 2, "oi", 1.0]], [[1, 2, "oi"]], model="m")
    transcricao.write(dia / "Transcrições", "01 Aula.mp4", data)      # ao lado da Saída (como no Drive)
    assert transcricao.lookup(v, 10.2)["status"] == "ok"
    assert transcricao.lookup(v, 12.0)["status"] == "nao_bate"          # outra versão do vídeo
    assert transcricao.target_dir(v) == saida / "Transcrições"


@needs_ffmpeg
def test_analise_usa_a_transcricao_pronta_e_a_manual(srv):  # noqa: F811
    port, tmp, server = srv
    pasta = tmp / "Ana 23-11"
    pasta.mkdir()
    _video(pasta / "01 Aula.mp4")
    _video(pasta / "02 Aula.mp4", freq=660)
    from revisor import media
    dur1 = media.probe(pasta / "01 Aula.mp4").duration
    words = [[1.0, 1.3, "ops", 1.0], [1.4, 1.8, "errei", 1.0], [2.0, 2.4, "vamos", 1.0]]
    transcricao.write(pasta / "Transcrições", "01 Aula.mp4",
                      transcricao.build("01 Aula.mp4", dur1, words, [[1.0, 2.4, "ops errei vamos"]], model="ggml-small-q5_1.bin"))
    st, r = _start(port, pasta, "Ana")          # "Ouvir as falas" desligado: a pronta vale mesmo assim
    assert st == 200, r
    _wait_all_done(port)
    st, j = _req(port, "GET", "/api/job")
    trs = {v["file"]: v["tr"] for v in j["videos"]}
    assert trs["01 Aula.mp4"]["status"] == "pronta" and trs["02 Aula.mp4"] is None
    st, v1 = _req(port, "GET", "/api/video?n=1")
    a1 = _analysis(tmp, v1["video"]["id"])
    assert a1["speech"]["source"] == "pronta"
    assert any(e["kind"] == "speech_phrase" for e in a1["events"])      # "errei" virou aviso
    # adicionar à mão no vídeo 02 (SRT do Premiere)
    srt = tmp / "02.srt"
    srt.write_text("1\n00:00:01,000 --> 00:00:02,000\nretomando aqui\n", encoding="utf-8")
    st, v2 = _req(port, "GET", "/api/video?n=2")
    vid2 = v2["video"]["id"]
    st, r = _req(port, "POST", "/api/transcript/import", {"id": vid2, "path": str(srt)})
    assert st == 200 and r["approx"], r
    assert (pasta / "Transcrições" / "02 Aula.transcricao.json").is_file()
    time.sleep(0.5)
    _wait_all_done(port)
    a2 = _analysis(tmp, vid2)
    assert a2["speech"]["source"] == "pronta" and a2["speech"]["approx"]
    assert any(e["kind"] == "speech_phrase" for e in a2["events"])      # "retomando"
    # arquivo errado: recusa sem mexer
    bad = tmp / "x.txt"
    bad.write_text("oi", encoding="utf-8")
    st, r = _req(port, "POST", "/api/transcript/import", {"id": vid2, "path": str(bad)})
    assert st == 400 and ".srt" in r["error"]


def test_cartao_rota(srv):  # noqa: F811
    port, tmp, server = srv
    st, r = _req(port, "POST", "/api/card", {"text": CARD, "folder": str(tmp / "2026 11 10 Maria Clara Souza")})
    assert st == 200 and r["card"]["professor"] == "Maria Clara Souza" and r["check"]["date_mismatch"]


def test_cartao_txt_exportado_com_tab_ou_igual():
    txt = "Nome que será utilizado na aula\tAna Lima\nCurso = MBA em Gestão\nDisciplina: Finanças\nData da gravação: 05/11/2026\n"
    c = cartao.parse(txt)
    assert (c["professor"], c["curso"], c["disciplina"], c["data_gravacao"]) == ("Ana Lima", "MBA em Gestão", "Finanças", "2026-11-05")
