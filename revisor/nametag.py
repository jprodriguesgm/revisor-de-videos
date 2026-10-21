"""Tarja de nome (lower third) no começo de cada aula.

Regra do núcleo: em TODA aula a tarja com o nome escolhido pelo professor
tem que aparecer no começo. Erro comum: tarja com texto genérico ("Nome do
professor").

A tarja muda de cor e de forma, então não procuramos um desenho: procuramos
TEXTO lido pelo OCR no começo do conteúdo (janela padrão de 45 s depois da
vinheta) e comparamos com o nome esperado (sem diferença de acento e de
maiúsculas). Resultado, um por vídeo:
  ok          nome encontrado
  diferente   texto parecido, mas não igual ("Bruno Zantu" × "Bruno Zantiu")
  generico    texto genérico da lista proibida
  lido        sem nome cadastrado: mostra o nome que parece estar na tarja
  nao_achada  nenhum nome no começo do vídeo
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

from .spell import norm

WINDOW_S = 45.0
SIMILAR = 0.75          # a partir disso é "o mesmo nome escrito diferente"
SHORT_S = 2.0           # tarja que fica menos que isso na tela: conferir
PERSISTENT = 0.4        # texto em 40% ou mais da varredura é logo/título fixo, não tarja

GENERIC_DEFAULT = [
    "nome do professor", "nome do(a) professor(a)", "nome da professora", "nome do docente",
    "nome sobrenome", "nome e sobrenome", "nome completo", "seu nome", "nome aqui",
    "professor", "professora", "professor(a)", "nome", "título", "titulo", "texto",
    "lorem ipsum", "fulano", "fulano de tal", "cargo", "cargo do professor",
]
CONNECTORS = {"de", "da", "do", "das", "dos", "e", "di", "van", "von", "del", "la"}
TITLES = {"prof", "profa", "professor", "professora", "dr", "dra", "me", "ma", "msc", "phd", "esp"}


def _clean(s: str) -> str:
    """Sem acento, minúsculas, só letras e números separados por espaço."""
    return " ".join(re.findall(r"[a-z0-9]+", norm(s)))


def _letters(s: str) -> str:
    """Minúsculas COM acento, só letras (para ver diferença de acento)."""
    import unicodedata
    return "".join(ch for ch in unicodedata.normalize("NFC", s.lower()) if ch.isalpha())


def _best_window(line: str, target: str) -> tuple[float, str]:
    """Trecho da linha mais parecido com o nome esperado."""
    lt, tt = line.split(), target.split()
    if not lt or not tt:
        return 0.0, ""
    best, best_txt = 0.0, ""
    n = len(tt)
    for size in {max(1, n - 1), n, n + 1}:
        for i in range(0, max(1, len(lt) - size + 1)):
            cand = " ".join(lt[i:i + size])
            r = SequenceMatcher(None, cand, target).ratio()
            if r > best:
                best, best_txt = r, cand
    return best, best_txt


def _orig_slice(line_text: str, cleaned_slice: str) -> str:
    """Devolve o trecho da linha original (com acentos) que corresponde ao trecho limpo."""
    words = line_text.split()
    target = cleaned_slice.split()
    for i in range(len(words)):
        for j in range(i + 1, len(words) + 1):
            if _clean(" ".join(words[i:j])).split() == target:
                return " ".join(words[i:j])
    return cleaned_slice


def generic_hit(line: str, generic: list[str]) -> str | None:
    c = _clean(line)
    for g in generic:
        gc = _clean(g)
        if not gc:
            continue
        if c == gc:
            return g
        if len(gc.split()) >= 2 and re.search(rf"(^| ){re.escape(gc)}( |$)", c):
            return g
    return None


LOGO_TEXTS = ["puc minas", "pucminas", "puc minas virtual", "iec puc minas"]


def _is_logo(cleaned: str) -> bool:
    """Logo da PUC Minas (às vezes lido pela metade: "PUC Mir nas")."""
    return any(SequenceMatcher(None, cleaned, lg).ratio() >= 0.75 for lg in LOGO_TEXTS)


def looks_like_name(text: str) -> bool:
    """2 a 6 palavras com inicial maiúscula (fora "de", "da", "dos"...), só letras.

    Pontuação dentro da linha ("Fonte: Ze", "Ex: Spotify") não é tarja; título
    ("Prof.", "Dra.") e inicial com ponto ("J. L. Moreno") são aceitos.
    """
    words = text.split()
    core = []
    for w in words:
        c = _clean(w)
        if c in TITLES:
            continue
        stripped = w.rstrip(".") if len(w.rstrip(".")) == 1 else w
        if not all(ch.isalpha() or ch in "-'’" for ch in stripped):
            return False
        core.append(stripped)
    if not 2 <= len(core) <= 6:
        return False
    caps = 0
    for w in core:
        if _clean(w) in CONNECTORS:
            continue
        if not w[:1].isupper():
            return False
        caps += 1
    return caps >= 2 and any(len(w) >= 3 for w in core)


# professor "Vários" etc.: a pasta tem mais de um professor, não há um nome para procurar
NOT_A_NAME = {"varios", "varias", "diversos", "diversas", "todos", "professores", "variados"}


def check(reads: list[dict], events: list[dict], fps: float, content_first: int,
          expected: str | None, generic: list[str] | None = None, window_s: float = WINDOW_S,
          scan_fps: float = 3.0) -> dict:
    """Procura a tarja nas leituras do começo do conteúdo (varredura + frames marcados).

    O tempo na tela vem da varredura (3 leituras por segundo): do primeiro ao
    último frame em que o nome foi lido. A tarja animada às vezes só fica
    legível em parte das leituras; para o nome vale a MELHOR leitura.
    """
    generic = generic if generic is not None else GENERIC_DEFAULT
    last = content_first + int(round(window_s * fps))
    cands = []      # (frame, linha, read)
    for rd in reads:
        if not content_first <= rd["frame"] <= last:
            continue
        for ln in rd["lines"]:
            cands.append((rd["frame"], ln, rd))
    cands.sort(key=lambda c: c[0])

    def seconds_seen(match) -> float | None:
        """Do primeiro ao último frame da varredura em que o nome foi lido (a leitura
        da tarja animada falha em alguns frames no meio: conta o intervalo todo)."""
        frames = sorted({f for f, ln, rd in cands if rd["source"] == "tag_scan" and match(ln["text"])})
        if not frames:
            return None
        return (frames[-1] - frames[0]) / fps + 1.0 / scan_fps

    def result(status, note, frame=None, read_text=None, box=None, match=None):
        r = {"status": status, "note": note, "frame": frame, "read": read_text, "expected": expected,
             "box": box, "window_s": window_s}
        secs = seconds_seen(match) if match else None
        if secs is not None:
            r["on_screen_s"] = round(secs, 1)
            if secs < SHORT_S:
                r["short"] = True
                r["note"] += f" · legível só ~{secs:.1f} s (conferir)".replace(".", ",")
        return r

    # 1) texto genérico (mostra a leitura mais completa)
    hits = [(f, ln, generic_hit(ln["text"], generic)) for f, ln, rd in cands]
    hits = [h for h in hits if h[2]]
    if hits:
        f, ln, g = max(hits, key=lambda h: (len(_clean(h[1]["text"])), h[1]["conf"]))
        return result("generico", f"tarja com nome genérico: '{ln['text']}'", f, ln["text"], ln["box"],
                      lambda t: generic_hit(t, generic) is not None)

    # "Vários" (pasta com mais de um professor) não é nome de tarja: vale como sem nome
    if expected and _clean(expected) in NOT_A_NAME:
        expected = None

    # 2) nome esperado
    if expected and _clean(expected):
        target = _clean(expected)
        best = (0.0, "", None, None)
        for f, ln, rd in cands:
            r, txt = _best_window(_clean(ln["text"]), target)
            if r > best[0] + 1e-9:
                best = (r, txt, f, ln)
        r, txt, f, ln = best
        if r >= 0.999:
            shown = _orig_slice(ln["text"], txt)
            res = result("ok", f"tarja ok: '{shown}'", f, ln["text"], ln["box"],
                         lambda t: _best_window(_clean(t), target)[0] >= SIMILAR)
            # mesmo nome, acento diferente ("Taviao" × "Tavião"): conferir
            if _letters(shown) != _letters(expected):
                res["accent_diff"] = True
                res["note"] = f"tarja com acento diferente do cadastrado: '{shown}' × '{expected}' (conferir)"
            return res
        if r >= SIMILAR:
            # o nome certo nunca apareceu; a leitura mais parecida aparece em várias leituras?
            shown = _orig_slice(ln["text"], txt)
            return result("diferente", f"nome na tarja diferente do cadastrado: '{shown}' × '{expected}'",
                          f, ln["text"], ln["box"], lambda t: _best_window(_clean(t), target)[0] >= SIMILAR)
        # o nome cadastrado não aparece: mostra o nome que está na tarja, se houver
        g = _guess(cands, window_s, scan_fps)
        if g:
            key, f, ln = g
            return result("diferente", f"nome na tarja diferente do cadastrado: '{ln['text']}' × '{expected}'",
                          f, ln["text"], ln["box"], lambda t: _best_window(_clean(t), key)[0] >= SIMILAR)
        return result("nao_achada", f"tarja não encontrada no começo deste vídeo (procurado: '{expected}')")

    # 3) sem nome cadastrado: o texto com cara de nome que mais aparece na varredura
    g = _guess(cands, window_s, scan_fps)
    if g:
        key, f, ln = g
        return result("lido", f"tarja: '{ln['text']}' (confira o nome)", f, ln["text"], ln["box"],
                      lambda t: _best_window(_clean(t), key)[0] >= SIMILAR)
    return result("nao_achada", "tarja não encontrada no começo deste vídeo")


def _guess(cands, window_s: float, scan_fps: float):
    """Texto com cara de nome que mais aparece na varredura, tirando o que fica na tela
    quase o tempo todo (logo "PUC Minas", título fixo). (chave, frame, linha) ou None."""
    # (a varredura só guarda os frames em que leu algo: conta pelo tamanho da janela)
    n_scan = max(1, int(window_s * scan_fps))
    count: dict[str, list] = {}
    for f, ln, rd in cands:
        if looks_like_name(ln["text"]):
            count.setdefault(_clean(ln["text"]), []).append((f, ln))
    count = {k: v for k, v in count.items() if len(v) < PERSISTENT * n_scan and not _is_logo(k)}
    if not count:
        return None
    # tarja fica na metade de baixo da tela quase sempre; depois, a que mais aparece
    key = max(count, key=lambda k: (count[k][0][1]["box"][1] > 0.5, len(count[k]), -count[k][0][0]))
    f, ln = count[key][0]
    return key, f, ln
