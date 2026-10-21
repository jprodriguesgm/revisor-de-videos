from revisor import nametag

FPS = 30000 / 1001


def _reads(*items):
    """items: (frame, texto) — leituras da varredura (3 por segundo)"""
    return [{"frame": f, "source": "tag_scan", "event_frame": None,
             "lines": [{"text": t, "conf": 90, "box": [.1, .8, .3, .05], "words": []}]} for f, t in items]


def _scan(first, n, text):
    """n leituras seguidas (a cada 10 frames) com o mesmo texto"""
    return _reads(*[(first + 10 * k, text) for k in range(n)])


def test_ok_sem_acento_e_maiusculas():
    r = nametag.check(_reads((300, "PROFA. MARIA CLARA SOUZA")), [], FPS, 180, "Maria Clara Souza")
    assert r["status"] == "ok"
    r = nametag.check(_reads((300, "João Paulo Rodrigues")), [], FPS, 180, "João Paulo Rodrigues")
    assert r["status"] == "ok" and not r.get("accent_diff")


def test_acento_diferente_conferir():
    r = nametag.check(_reads((300, "Carlos Taviao")), [], FPS, 180, "Carlos Tavião")
    assert r["status"] == "ok" and r["accent_diff"]
    assert "'Carlos Taviao' × 'Carlos Tavião'" in r["note"]


def test_nome_diferente():
    r = nametag.check(_reads((300, "Bruno Zantu")), [], FPS, 180, "Bruno Zantiu")
    assert r["status"] == "diferente"
    assert "'Bruno Zantu' × 'Bruno Zantiu'" in r["note"]


def test_generico():
    r = nametag.check(_reads((300, "Nome do Professor")), [], FPS, 180, "Bruno Zantiu")
    assert r["status"] == "generico"
    r = nametag.check(_reads((300, "Nome do(a) professor(a)")), [], FPS, 180, None)
    assert r["status"] == "generico"
    # "professor" dentro de uma frase normal não é genérico
    r = nametag.check(_reads((300, "O professor explica o conceito")), [], FPS, 180, None)
    assert r["status"] == "nao_achada"


def test_fora_da_janela_e_nao_achada():
    late = 180 + int(60 * FPS)
    r = nametag.check(_reads((late, "Bruno Zantiu")), [], FPS, 180, "Bruno Zantiu")
    assert r["status"] == "nao_achada"


def test_sem_nome_cadastrado_mostra_o_que_leu():
    r = nametag.check(_reads((250, "Sociograma"), (300, "Prof. Dr. Antônio Bispo dos Santos")), [], FPS, 180, None)
    assert r["status"] == "lido"
    assert "Antônio Bispo dos Santos" in r["note"]


def test_tarja_curta_conferir():
    r = nametag.check(_scan(300, 4, "Bruno Zantiu"), [], FPS, 180, "Bruno Zantiu")
    assert r["status"] == "ok" and r["short"] and "1,3 s" in r["note"]
    # leituras falhando no meio da animação: conta do primeiro ao último frame lido
    reads = _scan(300, 12, "Bruno Zantiu")
    del reads[3:9]
    r = nametag.check(reads, [], FPS, 180, "Bruno Zantiu")
    assert r["status"] == "ok" and not r.get("short") and r["on_screen_s"] == 4.0


def test_animacao_vale_a_melhor_leitura():
    reads = _reads((300, "amila Duarte Vasconti gel"), (310, "Renata Duarte Vasconti"),
                   (320, "Renata Duarte Vasconti"), (330, "Renata Duarte Vasconti"))
    r = nametag.check(reads, [], FPS, 180, "Renata Duarte Vasconti")
    assert r["status"] == "ok"
    assert r["frame"] == 310


def test_sem_nome_escolhe_o_que_mais_aparece():
    reads = _scan(250, 8, "Estratégias De Pricing") + _scan(400, 4, "Léo Rinaldi")
    for r in reads[:8]:
        r["lines"][0]["box"] = [.3, .25, .4, .06]          # título no alto da tela
    r = nametag.check(reads, [], FPS, 180, None)
    assert r["status"] == "lido" and "Léo Rinaldi" in r["note"]


def test_logo_nao_e_tarja():
    reads = _scan(250, 10, "PUC Minas") + _scan(400, 3, "PUC Mir nas")
    for r in reads:
        r["lines"][0]["box"] = [.85, .9, .1, .04]
    r = nametag.check(reads, [], FPS, 180, None)
    assert r["status"] == "nao_achada"


def test_cara_de_nome():
    assert nametag.looks_like_name("Felipe Arantes")
    assert nametag.looks_like_name("Prof. Dr. Antônio Bispo dos Santos")
    assert nametag.looks_like_name("J. L. Moreno")
    assert not nametag.looks_like_name("Fonte: Ze")
    assert not nametag.looks_like_name("Ex: Spotify, Netflix")
    assert not nametag.looks_like_name("O professor explica")


def test_cadastrado_errado_mostra_o_nome_da_tarja():
    # teste do JP (19/10): professor "Varios" → antes só "tarja não encontrada"
    r = nametag.check(_reads((300, "Léo Rinaldi")), [], FPS, 180, "Rodrigo Paveli")
    assert r["status"] == "diferente" and "'Léo Rinaldi' × 'Rodrigo Paveli'" in r["note"]


def test_varios_vale_como_sem_nome():
    r = nametag.check(_reads((300, "Bruno Zantiu")), [], FPS, 180, "Vários")
    assert r["status"] == "lido" and "Bruno Zantiu" in r["note"]
    r = nametag.check([], [], FPS, 180, "Varios")
    assert r["status"] == "nao_achada" and "procurado" not in r["note"]
