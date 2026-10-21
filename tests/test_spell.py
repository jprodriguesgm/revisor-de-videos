from revisor import spell

CK = spell.Checker()


def test_portugues_ingles_latim():
    for w in ["Previdência", "previdenciários", "Salário-maternidade", "sociodrama", "germinantes",
              "learning", "Transformers", "pricing", "habeas", "corpus", "litteris", "PREVIDÊNCIA"]:
        assert CK.known(w), w


def test_erros():
    for w in ["Previdênsia", "previdenciaria", "excessão", "concientização"]:
        assert not CK.known(w), w


def test_sugestoes():
    assert CK.suggest("Previdênsia")[0] == "Previdência"
    assert "previdenciária" in CK.suggest("previdenciaria")
    assert CK.suggest("excessão")[0] == "exceção"


def test_o_que_nao_checar():
    assert not spell.should_check("BPC")        # sigla
    assert not spell.should_check("AIOps")      # maiúscula no meio
    assert not spell.should_check("de")         # curta
    assert spell.should_check("PREVIDÊNSIA")    # título em maiúsculas é checado


def test_releitura_salva_engano_do_ocr():
    w = {"text": "Previdencia", "conf": 80, "box": [0, 0, .1, .1]}
    assert spell.word_problems(w, CK) == ["Previdencia"]
    w["reread"] = "Previdência"
    assert spell.word_problems(w, CK) == []
    w["reread"] = "Previdencia"
    assert spell.word_problems(w, CK) == ["Previdencia"]


def test_sem_acento_vale_o_portugues():
    # inglês/latim aceitam "familia", mas em português falta o acento
    assert not CK.known("Familia")
    assert CK.suggest("Familia") == ["Família"]


def test_lista_propria(tmp_path):
    lista = tmp_path / "lista.txt"
    ck = spell.Checker(custom=spell.load_custom(lista))
    assert not ck.known("Zantiu")
    spell.add_to_custom(lista, "Zantiu")
    spell.add_to_custom(lista, "Zantiu")
    assert lista.read_text(encoding="utf-8").count("Zantiu") == 1
    ck = spell.Checker(custom=spell.load_custom(lista))
    assert ck.known("Zantiu") and ck.known("ZANTIU")


def _read(frame, *lines):
    return {"frame": frame, "source": "text_in", "lines": [
        {"text": t, "conf": 90, "box": [0, i * .1, .5, .05],
         "words": [{"text": w, "conf": 90, "box": [0, i * .1, .1, .05]} for w in t.split()]}
        for i, t in enumerate(lines)]}


def test_check_reads_uma_vez_por_video_e_hifen():
    reads = [_read(100, "Previdênsia Social"), _read(200, "Previdênsia Social"),
             _read(300, "aposentadoria previden-", "ciária por idade")]
    f = spell.check_reads(reads, CK)
    assert [x["word"] for x in f] == ["Previdênsia"]
    assert f[0]["frames"] == [100, 200]
    assert f[0]["suggestions"][0] == "Previdência"
    assert "aparece 2 vezes" in spell.note_for(f[0])


def test_palavra_cortada_e_lixo():
    reads = [_read(100, "finan"), _read(200, "Planejamento financeiro"), _read(300, "1000 chs FV"),
             _read(400, "Word2Vec e GloVe"), _read(500, "ntexto"), _read(600, "Contexto delimitado")]
    assert spell.check_reads(reads, CK) == []
