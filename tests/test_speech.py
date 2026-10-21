from revisor import speech
from revisor.speech import Word


def W(text, t0=0.0, step=0.35):
    out = []
    t = t0
    for w in text.split():
        out.append(Word(t, t + step * 0.8, w))
        t += step
    return out


def test_norm():
    assert speech.norm("Começo,") == "comeco"
    assert speech.norm_phrase("Vou começar de novo!") == ["vou", "comecar", "de", "novo"]


def test_error_phrase_found():
    ws = W("então o próximo passo é calcular, ah, errei, vou voltar. O próximo passo é calcular o fluxo")
    res = speech.find_error_phrases(ws, speech.ERROR_PHRASES_DEFAULT)
    kinds = [r["match"] for r in res]
    assert "errei" in kinds and "vou voltar" in kinds


def test_error_phrase_whole_words_only():
    # "corta" não pode bater em "cortar"/"recorta"; "desculpa" sim, com pontuação
    ws = W("vamos recortar a imagem e cortar o excesso. Desculpa. Olhando de novo para a imagem")
    res = speech.find_error_phrases(ws, speech.ERROR_PHRASES_DEFAULT)
    assert [r["match"] for r in res] == ["desculpa"]


def test_longest_phrase_wins():
    ws = W("deixa eu repetir isso")
    res = speech.find_error_phrases(ws, ["repetir", "deixa eu repetir"])
    assert len(res) == 1 and res[0]["match"] == "deixa eu repetir"


def test_repeat_take_found():
    ws = W("nessa aula a gente vai estudar o valor presente líquido que é... Retomando. "
           "nessa aula a gente vai estudar o valor presente líquido de um projeto")
    res = speech.find_repeats(ws)
    assert len(res) == 1
    r = res[0]
    assert r["first"].startswith("nessa aula a gente vai estudar")
    assert any("retomando" in x for x in r["reasons"]) and "reticências" in r["reasons"]


def test_repeat_with_one_letter_misheard():
    ws = W("o modelo de fundação é treinado com muitos dados, opa, "
           "o modelo de fundação é treinada com muitos dados diferentes")
    assert len(speech.find_repeats(ws)) == 1


def test_rhetorical_repetition_is_normal():
    # do jeito que os professores falam nas aulas aprovadas
    for t in ["a estratégia de preço por pacote. A estratégia de preço por pacote é a venda de",
              "o registro do que foi feito. Precisa ter o registro do que foi feito. E o que é",
              "O encoder fica do lado esquerdo. Enquanto o decoder fica do lado direito.",
              "pode ser uma palavra, pode ser parte de uma palavra, pode ser uma pontuação"]:
        assert speech.find_repeats(W(t)) == [], t


def test_whole_sentence_said_twice():
    ws = W("quase todo o trabalho do escritório é manipulação de texto. "
           "o trabalho do escritório é manipulação de texto. O que muda é")
    res = speech.find_repeats(ws)
    assert len(res) == 1 and "frase inteira dita 2 vezes" in res[0]["reasons"]


def test_long_pause_before_restart():
    ws = W("então o modelo de linguagem aprende padrões")
    ws += W("então o modelo de linguagem aprende padrões estatísticos do texto", t0=ws[-1].end + 2.0)
    res = speech.find_repeats(ws)
    assert len(res) == 1 and res[0]["reasons"][0].startswith("pausa")


def test_topic_phrase_far_apart_is_not_repeat():
    filler = ("e aqui a gente olha o gráfico com calma para entender cada linha da tabela "
              "porque cada fluxo de caixa chega num ano diferente e precisa ser trazido para hoje")
    ws = W(f"o valor presente líquido do projeto {filler} o valor presente líquido do projeto")
    assert speech.find_repeats(ws) == []


def test_short_repetition_is_normal():
    ws = W("é muito importante, muito importante mesmo, a gente vai, a gente vai ver isso")
    assert speech.find_repeats(ws) == []


def test_hallucination_loop_dropped():
    ws = W("obrigado por assistir o vídeo " * 4)
    assert speech.find_repeats(ws) == []


def test_repeat_in_silence_dropped():
    ws = W("nessa aula a gente vai estudar o valor presente... nessa aula a gente vai estudar o valor presente")
    assert speech.find_repeats(ws, speech_active=lambda a, b: 0.0) == []
    assert len(speech.find_repeats(ws, speech_active=lambda a, b: 1.0)) == 1


def test_words_from_whisper_json():
    data = {"transcription": [{"offsets": {"from": 0, "to": 2000}, "text": " Olá, pessoal.",
                               "tokens": [
                                   {"text": "[_BEG_]", "offsets": {"from": 0, "to": 0}, "p": 1},
                                   {"text": " Ol", "offsets": {"from": 100, "to": 300}, "p": 0.9},
                                   {"text": "á", "offsets": {"from": 300, "to": 400}, "p": 0.8},
                                   {"text": ",", "offsets": {"from": 400, "to": 400}, "p": 0.9},
                                   {"text": " pessoal", "offsets": {"from": 500, "to": 900}, "p": 0.9, "t_dtw": 52},
                                   {"text": ".", "offsets": {"from": 900, "to": 950}, "p": 0.9},
                               ]}]}
    ws = speech.words_from_whisper_json(data, offset=10.0)
    assert [w.text for w in ws] == ["Olá,", "pessoal."]
    assert abs(ws[0].start - 10.1) < 1e-6 and abs(ws[1].start - 10.52) < 1e-6


def test_plan_chunks_cuts_in_pause():
    step = 0.1
    env = [-20] * 3000                       # 300 s de fala
    for i in range(1050, 1060):              # pausa em 105–106 s
        env[i] = -90
    ch = speech.plan_chunks((0.0, 300.0), env, step)
    assert abs(ch[0][1] - 105.5) < 0.2
    assert ch[-1][1] == 300.0
    assert all(b > a for a, b in ch)


def test_checks_merge_phrase_into_repeat():
    sp = {"words": [w.to_list() for w in W(
        "ele é o alicerce sobre qualquer... Retomando. ele é o alicerce sobre o qual muitas aplicações. "
        "Vou voltar. Vou voltar onde estava")]}
    res = speech.checks(sp)
    assert [r["kind"] for r in res] == ["speech_repeat", "speech_phrase"]
    assert res[1].get("count") == 2
