"""Ortografia do texto lido na tela.

Dicionários Hunspell (os mesmos do LibreOffice), lidos pelo spylls (Python
puro, nada para instalar):
  - pt_BR (VERO, LibreOffice), en_US e en_GB (SCOWL), la (latim, Karl Zeiler).
O português manda: palavra sem acento que o inglês/latim aceitam mas que em
português leva acento ("familia", "salario"?) é avisada.
Lista fixa do núcleo em data/dict/palavras_nucleo.txt (PUC Minas etc.).
Uma palavra está certa se algum dicionário aceitar, ou se estiver na lista
própria (que cresce quando o JP clica "Aceitar" na revisão).

O OCR às vezes erra um acento ou uma letra. Por isso, antes de avisar, a
palavra é relida ampliada (ocr.reread_word). Se a releitura der uma palavra
do dicionário, foi engano do OCR e não vira aviso.

Não são verificadas: palavras com menos de 3 letras, siglas (até 6 letras
maiúsculas), nomes com maiúscula no meio (AIOps, DevOps, ChatGPT), endereços
de site, palavras cortadas na borda da tela, palavras lidas com pouca
confiança e palavras com maiúscula no meio da frase (nomes próprios), a não
ser que o problema seja acento.
"""
from __future__ import annotations

import re
import threading
import time
import unicodedata
from pathlib import Path

from . import ocr

DICTS = ("pt_BR", "en_US", "en_GB", "la")
MIN_LEN = 3
MIN_CONF = 60.0          # confiança mínima do OCR para checar a palavra
ACRONYM_MAX = 6
SUGGEST_BUDGET_S = 0.6   # tempo máximo para sugestões de uma palavra

LETTERS = "a-zA-ZÀ-ÖØ-öø-ÿ"
TOKEN_RE = re.compile(rf"[{LETTERS}]+(?:[-'’][{LETTERS}]+)*")
ALPHABET = "abcdefghijklmnopqrstuvwxyzáàâãéêíóôõúüç"
ACCENTS = {
    "a": "áàâã", "e": "éê", "i": "í", "o": "óôõ", "u": "úü", "c": "ç",
    "á": "aàâã", "à": "aáâã", "â": "aáàã", "ã": "aáàâ", "é": "eê", "ê": "eé",
    "í": "i", "ó": "oôõ", "ô": "oóõ", "õ": "oóô", "ú": "uü", "ü": "uú", "ç": "c",
}
# trocas comuns em português (erros de digitação de verdade)
SWAPS = [("s", "c"), ("c", "s"), ("ss", "ç"), ("ç", "ss"), ("s", "ç"), ("ç", "s"), ("s", "z"), ("z", "s"), ("x", "ch"),
         ("ch", "x"), ("g", "j"), ("j", "g"), ("ss", "s"), ("s", "ss"), ("c", "ç"), ("sc", "c"), ("c", "sc"),
         ("rr", "r"), ("r", "rr"), ("u", "l"), ("l", "u"), ("ão", "am"), ("am", "ão")]


def norm(s: str) -> str:
    """Minúsculas e sem acento (para comparar)."""
    s = unicodedata.normalize("NFD", s.lower())
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def dict_dir() -> Path:
    return ocr.data_dir() / "dict"


class Checker:
    """Verificador com os dicionários carregados uma vez (≈5 s na primeira vez)."""

    _shared: dict[tuple, list] = {}
    _lock = threading.Lock()

    def __init__(self, langs=DICTS, custom: set[str] | list[str] | None = None, folder: Path | None = None):
        self.langs = tuple(langs)
        self.folder = Path(folder) if folder else dict_dir()
        self.custom: set[str] = set()
        self.add_custom(w for w in (custom or []) if w.strip())
        self.add_custom(load_custom(self.folder / "palavras_nucleo.txt"))
        self._dicts = None
        self._cache: dict[str, bool] = {}

    def add_custom(self, words) -> None:
        """Palavra ou expressão ("habeas corpus"): cada palavra da expressão também vale."""
        for w in words:
            w = nfc(w).lower().strip()
            if not w:
                continue
            self.custom.add(w)
            for t in TOKEN_RE.findall(w):
                self.custom.add(t)
        if hasattr(self, "_cache"):
            self._cache.clear()

    @property
    def dicts(self):
        if self._dicts is None:
            key = (str(self.folder), self.langs)
            with Checker._lock:
                if key not in Checker._shared:
                    from spylls.hunspell import Dictionary
                    ds = []
                    for name in self.langs:
                        base = self.folder / name
                        if base.with_suffix(".dic").is_file():
                            ds.append(Dictionary.from_files(str(base)))
                    Checker._shared[key] = ds
            self._dicts = Checker._shared[key]
        return self._dicts

    def _lookup(self, word: str, only_main: bool = False) -> bool:
        """Algum dicionário aceita a palavra? (only_main: só o português)"""
        key = ("1" if only_main else "*") + word
        if key in self._cache:
            return self._cache[key]
        ok = False
        for d in (self.dicts[:1] if only_main else self.dicts):
            try:
                if d.lookup(word):
                    ok = True
                    break
            except Exception:  # palavra estranha para o spylls: trata como não achada
                continue
        self._cache[key] = ok
        return ok

    def _missing_accent(self, w: str) -> bool:
        """Palavra sem acento que é português com acento ("familia" → "família").

        Inglês e latim aceitam muitas palavras portuguesas sem acento
        ("familia", "salario", "media"); nesses casos vale o português.
        """
        low = w.lower()
        for i, ch in enumerate(low):
            for alt in ACCENTS.get(ch, ""):
                if alt in "áàâãéêíóôõúüç" and self._lookup(low[:i] + alt + low[i + 1:], only_main=True):
                    return True
        return False

    def _word_ok(self, w: str) -> bool:
        for cand in (w, w.lower()) + ((w.capitalize(),) if w.isupper() else ()):
            if self._lookup(cand, only_main=True):
                return True
        for cand in (w, w.lower()) + ((w.capitalize(),) if w.isupper() else ()):
            if self._lookup(cand):
                return not self._missing_accent(w)
        return False

    def known(self, word: str) -> bool:
        w = nfc(word).strip("'’-")
        if not w:
            return True
        if w.lower() in self.custom:
            return True
        if self._word_ok(w):
            return True
        # palavra com hífen: aceita se cada parte existir (ex.: "salário-maternidade")
        parts = re.split(r"[-'’]", w)
        if len(parts) > 1 and all(len(p) < MIN_LEN or self.known(p) for p in parts):
            return True
        return False

    def accent_fix(self, word: str) -> list[str]:
        """Palavras do português que só diferem nos acentos (acento faltando, sobrando ou trocado)."""
        w = nfc(word)
        low = w.lower()
        base = norm(low) if all(ch.isalpha() or ch in "-'’" for ch in low) else low
        cands = []
        for c in [base] + [base[:i] + alt + base[i + 1:] for i, ch in enumerate(base)
                           for alt in ACCENTS.get(ch, "") if alt in "áàâãéêíóôõúüç"] + \
                [low[:i] + alt + low[i + 1:] for i, ch in enumerate(low) for alt in ACCENTS.get(ch, "")]:
            if c != low and c not in cands:
                cands.append(c)
        found = [c for c in cands if self._lookup(c, only_main=True)]
        n_acc = sum(ch in "áàâãéêíóôõúüç" for ch in low)
        # mesmo número de acentos primeiro ("pápeis" → "papéis" antes de "papeis")
        found.sort(key=lambda c: abs(sum(ch in "áàâãéêíóôõúüç" for ch in c) - n_acc))
        return _recase(found, w)

    def suggest(self, word: str, limit: int = 3) -> list[str]:
        """Sugestões rápidas: acento, trocas comuns e uma letra a mais/menos/trocada."""
        w = nfc(word)
        low = w.lower()
        t0 = time.time()
        found: list[str] = []
        seen = {low}

        def try_(cand: str) -> bool:
            if cand in seen or not cand:
                return False
            seen.add(cand)
            if self._lookup(cand, only_main=True):
                found.append(cand)
            return len(found) >= limit or time.time() - t0 > SUGGEST_BUDGET_S

        # 1) acentos (o erro mais comum)
        acc = self.accent_fix(w)
        if acc:
            return acc[:limit]
        if found:
            return _recase(found, w)
        # 2) trocas comuns
        for a, b in SWAPS:
            start = 0
            while True:
                i = low.find(a, start)
                if i < 0:
                    break
                if try_(low[:i] + b + low[i + len(a):]):
                    return _recase(found, w)
                start = i + 1
        if found:
            return _recase(found, w)
        # 3) uma edição
        n = len(low)
        for i in range(n - 1):                       # letras trocadas de lugar
            if try_(low[:i] + low[i + 1] + low[i] + low[i + 2:]):
                return _recase(found, w)
        if found:
            return _recase(found, w)
        for i in range(n):                           # letra a mais
            if try_(low[:i] + low[i + 1:]):
                return _recase(found, w)
        if found:
            return _recase(found, w)
        for i in range(n):                           # letra errada
            for ch in ALPHABET:
                if ch != low[i] and try_(low[:i] + ch + low[i + 1:]):
                    return _recase(found, w)
        if found:
            return _recase(found, w)
        # 4) dois acentos trocados (ex.: "previdenciaria")
        for i, ch in enumerate(low):
            for alt in ACCENTS.get(ch, ""):
                c1 = low[:i] + alt + low[i + 1:]
                for j in range(i + 1, len(low)):
                    for alt2 in ACCENTS.get(c1[j], ""):
                        if try_(c1[:j] + alt2 + c1[j + 1:]):
                            return _recase(found, w)
                if time.time() - t0 > SUGGEST_BUDGET_S:
                    break
        if found:
            return _recase(found, w)
        for i in range(n + 1):                       # letra faltando
            for ch in ALPHABET:
                if try_(low[:i] + ch + low[i:]):
                    return _recase(found, w)
        return _recase(found, w)


def _recase(cands: list[str], like: str) -> list[str]:
    if like.isupper():
        return [c.upper() for c in cands]
    if like[:1].isupper():
        return [c[:1].upper() + c[1:] for c in cands]
    return cands


# ---------------------------------------------------------------- o que checar

def tokens(text: str) -> list[str]:
    return TOKEN_RE.findall(nfc(text))


VOWELS = set("aeiouyáéíóúâêôãõàüAEIOUYÁÉÍÓÚÂÊÔÃÕÀÜ")


def should_check(tok: str) -> bool:
    letters = sum(ch.isalpha() for ch in tok)
    if letters < MIN_LEN:
        return False
    if not any(ch in VOWELS for ch in tok):
        return False                                   # "chs", "cfj": não é palavra (tela de calculadora, risco)
    core = tok.replace("-", "").replace("'", "").replace("’", "")
    if core.isupper() and len(core) <= ACRONYM_MAX:
        return False                                   # sigla: BPC, LOAS, INSS
    if any(ch.isupper() for ch in core[1:]) and not core.isupper():
        return False                                   # AIOps, DevOps, ChatGPT, iPhone
    return True


URL_RE = re.compile(r"(://|www\.|@|\.(com|br|org|net|edu|gov|io)\b)", re.I)


def word_problems(word: dict, checker: Checker, sentence_start: bool = True) -> list[str]:
    """Pedaços de uma palavra lida (dict de ocr.Word) que não estão nos dicionários.

    `sentence_start=False`: palavra no meio da frase. Se começar com maiúscula,
    provavelmente é nome próprio (Spotify, Moreno) — só avisa se for palavra
    portuguesa com acento errado ("Familia" → "Família").
    """
    if word.get("conf", 0) < MIN_CONF or word.get("cut"):
        return []
    if URL_RE.search(word["text"]):
        return []                                      # endereço de site / e-mail
    if any(ch.isdigit() for ch in word["text"]):
        return []                                      # Word2Vec, COVID-19, 3ª, R$10mil
    bad = []
    for tok in tokens(word["text"]):
        if not should_check(tok) or checker.known(tok):
            continue
        if not sentence_start and tok[:1].isupper() and not tok.isupper() and not checker.accent_fix(tok):
            continue                                   # nome próprio no meio da frase
        bad.append(tok)
    if not bad:
        return []
    # releitura ampliada achou outra coisa? Vale a releitura se ela for uma palavra certa
    rr = word.get("reread")
    if rr:
        rt = [t for t in tokens(rr) if should_check(t)]
        if rt and all(checker.known(t) for t in rt):
            return []
    return bad


def _join_hyphenated(lines: list[dict]) -> list[dict]:
    """Junta palavra quebrada no fim da linha ("previden-" + "ciário")."""
    if len(lines) < 2:
        return lines
    lines = sorted(lines, key=lambda ln: (ln["box"][1], ln["box"][0]))
    for a, b in zip(lines[:-1], lines[1:]):
        if not a["words"] or not b["words"]:
            continue
        last, first = a["words"][-1], b["words"][0]
        if last["text"].endswith("-") and first["text"][:1].islower():
            joined = last["text"][:-1] + first["text"]
            last["joined"] = joined
            first["joined_into_previous"] = True
    return lines


def check_reads(reads: list[dict], checker: Checker, skip_lines: set[str] | None = None) -> list[dict]:
    """Palavras com problema, uma vez por vídeo (a primeira vez que aparecem).

    As leituras da varredura da tarja não entram (são para a tarja; texto
    pequeno de slide lido por ela vira lixo — visto nas aulas reais). Os slides
    são lidos em resolução cheia depois de cada corte.
    `skip_lines`: linhas já conferidas por outra regra (o nome na tarja).
    """
    skip = {norm(x) for x in (skip_lines or set())}
    out: dict[str, dict] = {}
    for rd in reads:
        for ln in _join_hyphenated([dict(x, words=[dict(w) for w in x["words"]]) for x in rd["lines"]]):
            key_line = norm(ln["text"])
            if key_line in skip:
                continue
            if rd["source"] == "tag_scan":
                continue        # varredura é só para a tarja (slide pequeno lido por ela vira lixo)
            checkable = [t for w in ln["words"] for t in tokens(w["text"]) if should_check(t)]
            if len(checkable) == 1 and len(ln["words"]) == 1 and len(checkable[0]) <= 4:
                continue                                   # palavrinha solta ("exe"): quase sempre lixo do OCR
            prev = ""
            for i, w in enumerate(ln["words"]):
                start = i == 0 or prev.endswith((".", "!", "?", "•", "*")) or prev in ("-", "–", "—")
                prev = w["text"]
                if w.get("joined_into_previous"):
                    continue
                ww = dict(w, text=w.get("joined", w["text"]))
                for tok in word_problems(ww, checker, sentence_start=start):
                    key = norm(tok)
                    if key in out:
                        if rd["frame"] not in out[key]["frames"]:
                            out[key]["frames"].append(rd["frame"])
                        continue
                    out[key] = {"word": tok, "frame": rd["frame"], "box": w["box"], "line": ln["text"],
                                "conf": w["conf"], "reread": w.get("reread"), "frames": [rd["frame"]],
                                "source": rd["source"]}
    # palavra cortada: texto animado (entrando letra por letra ou com máscara)
    # lido no meio. Se a mesma palavra aparece inteira em outra leitura do
    # vídeo ("finan" → "financeiro", "ntexto" → "Contexto"), não é erro.
    whole = set()
    for rd in reads:
        for ln in rd["lines"]:
            for w in ln["words"]:
                for t in tokens(w["text"]):
                    whole.add(norm(t))
    res = []
    for f in sorted(out.values(), key=lambda f: f["frame"]):
        k = norm(f["word"])
        if any(len(o) > len(k) and (o.startswith(k) or o.endswith(k)) for o in whole):
            continue
        res.append(f)
    for f in res:
        f["suggestions"] = checker.suggest(f["word"])
    return res


def note_for(f: dict) -> str:
    s = f"ortografia: '{f['word']}'"
    if f.get("suggestions"):
        s += " → " + ", ".join(f["suggestions"])
    if len(f.get("frames", [])) > 1:
        s += f" (aparece {len(f['frames'])} vezes)"
    return s


def load_custom(path: str | Path | None) -> list[str]:
    if not path:
        return []
    p = Path(path)
    if not p.is_file():
        return []
    return [ln.strip() for ln in p.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("#")]


def add_to_custom(path: str | Path, word: str) -> None:
    """Botão "Aceitar": a palavra entra na lista própria (um por linha)."""
    p = Path(path)
    words = load_custom(p)
    if norm(word) in {norm(w) for w in words} and nfc(word).lower() in {nfc(w).lower() for w in words}:
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(nfc(word) + "\n")


def remove_from_custom(path: str | Path, word: str) -> bool:
    """Tira uma palavra/expressão da lista própria (configurações). True se tirou."""
    p = Path(path)
    if not p.is_file():
        return False
    target = nfc(word).strip().lower()
    lines = p.read_text(encoding="utf-8").splitlines()
    keep = [ln for ln in lines if nfc(ln).strip().lower() != target]
    if len(keep) == len(lines):
        return False
    tmp = p.with_suffix(".tmp")
    tmp.write_text("".join(ln + "\n" for ln in keep), encoding="utf-8")
    tmp.replace(p)
    return True
