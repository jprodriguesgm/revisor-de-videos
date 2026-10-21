"""Etapa 2b — fala: transcrição offline (whisper.cpp) e avisos de "conferir".

Tudo roda no computador, sem internet. O que sai daqui:
  1. Frases de erro ditas pelo professor ("errei", "vou voltar", "deixa eu repetir"…),
     com lista editável.
  2. Trechos repetidos: o professor começa uma frase, para e começa de novo
     (take que não foi cortado).
O terceiro aviso da fala, corte no meio da palavra, não precisa de transcrição
e fica em audio.py.

Como roda:
- O áudio do conteúdo (entre as vinhetas) é dividido em pedaços de ~2 min,
  cortados em pausas da fala. Cada pedaço vai para o whisper-cli (whisper.cpp)
  e o resultado vai para o cache do vídeo (speech/chunk_NNN.json). Assim a
  transcrição pode parar e continuar, e a barra de progresso anda por pedaço.
- Palavras com tempo de início e fim (tempos dos tokens; com -dtw ficam mais
  precisos).
- Os avisos são refeitos sem transcrever de novo quando a lista de frases muda
  (refresh feito por analyze.refresh_speech_checks).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import media

MODEL_NAME = "ggml-small-q5_1.bin"
CHUNK_S = 120.0          # tamanho alvo do pedaço
CHUNK_SEARCH_S = 20.0    # procura a pausa mais longa até 20 s antes do alvo
SAMPLE_RATE = 16000      # o Whisper trabalha em 16 kHz mono

# "Prompt" inicial: um exemplo de fala transcrita AO PÉ DA LETRA. Sem isso o
# Whisper tende a "limpar" a fala (some com hesitação, "errei", repetição) —
# justamente o que queremos ver.
PROMPT = ("Olá, pessoal. Então, é... nessa aula a gente vai, a gente vai ver... "
          "Errei, vou voltar. Deixa eu repetir: nessa aula a gente vai ver o conceito.")

# Frases de erro (lista padrão; vai para as configurações e pode ser editada).
# Comparadas sem acento, sem maiúsculas e sem pontuação, como palavras inteiras.
ERROR_PHRASES_DEFAULT = [
    "retomando", "errei", "eu errei", "me enganei", "falei errado", "falei errada",
    "vou voltar", "deixa eu voltar", "deixa eu repetir", "vou repetir", "vou falar de novo",
    "vou gravar de novo", "gravar de novo", "vou comecar de novo", "vamos de novo",
    "pode cortar", "corta ai", "vou regravar",
    "desculpa", "desculpe", "foi mal", "gaguejei", "travei",
]
# Fora da lista (alarme falso nas aulas aprovadas): "de novo" ("olhando de novo para a
# imagem"), "do começo" ("a palavra do começo"), "corta" sozinho.

# Repetição (take não cortado)
REP_MIN_WORDS = 4         # trecho repetido com pelo menos 4 palavras…
REP_MIN_CHARS = 18        # …e 18 letras (sem contar espaços)
REP_MIN_CONTENT = 2       # pelo menos 2 palavras que não são "de", "a", "que"…
REP_MAX_ABANDON = 8       # palavras ditas entre o fim da 1ª tentativa e o recomeço (regra da pausa)
REP_MAX_ABANDON_ANY = 20  # com reticências ou palavra de erro no meio, aceita até 20
REP_MAX_GAP_S = 25.0      # recomeço até 25 s depois do início da 1ª tentativa

STOPWORDS = set("""
a o as os um uma uns umas de da do das dos em na no nas nos por pra pro para com sem
e ou mas que se como quando onde ja nao sim eh e ta tá isso esse essa este esta aqui ai
la entao ne la eu voce voces a gente gente nos ele ela eles elas me te lhe seu sua
ao aos à às pelo pela pelos pelas tambem mais muito bem vai vou vamos ser ter tem
""".split())


class SpeechError(RuntimeError):
    pass


# ------------------------------------------------------------------ ferramentas

def _model_dirs() -> list[Path]:
    dirs = []
    if os.environ.get("REVISOR_WHISPER_MODEL_DIR"):
        dirs.append(Path(os.environ["REVISOR_WHISPER_MODEL_DIR"]))
    for d in media._bundled_dirs():
        dirs.append(d.parent / "models")
        dirs.append(d)
    dirs.append(Path(__file__).resolve().parent / "data" / "models")
    return dirs


def find_model() -> str | None:
    if os.environ.get("REVISOR_WHISPER_MODEL") and Path(os.environ["REVISOR_WHISPER_MODEL"]).is_file():
        return os.environ["REVISOR_WHISPER_MODEL"]
    for d in _model_dirs():
        p = d / MODEL_NAME
        if p.is_file():
            return str(p)
    return None


def find_cli() -> str | None:
    for name in ("whisper-cli", "whisper-cpp", "main"):
        try:
            p = media.find_tool(name)
        except media.MediaError:
            continue
        if name != "main" or "whisper" in p:
            return p
    return None


def available() -> bool:
    return find_model() is not None and find_cli() is not None


def threads() -> int:
    n = os.cpu_count() or 4
    return max(1, min(8, n))


# ------------------------------------------------------------------ texto

def norm(word: str) -> str:
    """Forma de comparação: minúscula, sem acento, só letras e números."""
    w = unicodedata.normalize("NFKD", word.lower())
    w = "".join(c for c in w if not unicodedata.combining(c))
    return re.sub(r"[^0-9a-z]+", "", w)


def norm_phrase(text: str) -> list[str]:
    return [t for t in (norm(x) for x in re.split(r"[\s\-–—/]+", text)) if t]


@dataclass
class Word:
    start: float
    end: float
    text: str
    p: float = 1.0

    def to_list(self):
        return [round(self.start, 2), round(self.end, 2), self.text, round(self.p, 2)]


def words_from_whisper_json(data: dict, offset: float = 0.0) -> list[Word]:
    """Junta os tokens do JSON completo do whisper-cli em palavras com tempo."""
    out: list[Word] = []
    for seg in data.get("transcription", []):
        cur: list[dict] = []

        def flush():
            if not cur:
                return
            text = "".join(t["text"] for t in cur).strip()
            if not norm(text):
                # pontuação solta: gruda na palavra anterior
                if out and text:
                    out[-1].text += text
                return
            t0 = _tok_start(cur[0])
            t1 = _tok_end(cur[-1])
            p = float(np.mean([t.get("p", 1.0) for t in cur]))
            out.append(Word(offset + t0, offset + max(t1, t0), text, p))

        for tok in seg.get("tokens", []):
            txt = tok.get("text", "")
            if txt.startswith("[_") or txt.startswith("<|"):
                continue          # tokens especiais (início, tempo…)
            if txt.startswith(" ") and cur:
                flush()
                cur = []
            cur.append(tok)
        flush()
    return out


def _tok_start(t: dict) -> float:
    d = t.get("t_dtw", -1)
    if isinstance(d, (int, float)) and d >= 0:
        return d / 100.0           # t_dtw vem em centésimos de segundo
    return t["offsets"]["from"] / 1000.0


def _tok_end(t: dict) -> float:
    return t["offsets"]["to"] / 1000.0


# ------------------------------------------------------------------ pedaços

def plan_chunks(content: tuple[float, float], env_db: list[int] | None, env_step: float) -> list[tuple[float, float]]:
    """Divide o conteúdo em pedaços de ~CHUNK_S, cortando no meio da pausa mais longa."""
    a, b = content
    if b - a <= CHUNK_S * 1.3:
        return [(a, b)]
    quiet = None
    if env_db:
        e = np.asarray(env_db, dtype=np.float32)
        quiet = e < -50.0
    chunks = []
    start = a
    while b - start > CHUNK_S * 1.3:
        target = start + CHUNK_S
        cut = target
        if quiet is not None:
            i0 = int((target - CHUNK_SEARCH_S) / env_step)
            i1 = int(target / env_step)
            best, best_len, run = None, 0, 0
            for i in range(max(i0, 0), min(i1 + 1, quiet.size)):
                run = run + 1 if quiet[i] else 0
                if run >= best_len and run > 0:
                    best_len, best = run, i - run // 2
            if best is not None and best_len >= 2:     # pelo menos 200 ms de pausa
                cut = best * env_step
        chunks.append((start, cut))
        start = cut
    chunks.append((start, b))
    return chunks


def _extract_wav(video_path: str, start: float, end: float, dst: str) -> None:
    cmd = [media.ffmpeg(), "-hide_banner", "-nostdin", "-loglevel", "error", "-y",
           "-ss", f"{start:.3f}", "-i", str(video_path), "-t", f"{end - start:.3f}",
           "-map", "0:a:0", "-ac", "1", "-ar", str(SAMPLE_RATE), "-c:a", "pcm_s16le", dst]
    r = subprocess.run(cmd, capture_output=True, **media._hidden_window_kwargs())
    if r.returncode != 0:
        raise SpeechError(r.stderr.decode(errors="ignore")[-400:])


def transcribe_chunk(video_path: str, start: float, end: float, model: str | None = None,
                     cli: str | None = None, n_threads: int | None = None) -> dict:
    model = model or find_model()
    cli = cli or find_cli()
    if not model or not cli:
        raise SpeechError("whisper não encontrado")
    with tempfile.TemporaryDirectory(prefix="revisor_fala_") as tmp:
        wav = os.path.join(tmp, "a.wav")
        _extract_wav(video_path, start, end, wav)
        out = os.path.join(tmp, "out")
        cmd = [cli, "-m", model, "-f", wav, "-l", "pt", "-t", str(n_threads or threads()),
               "-mc", "0",            # não usa o texto anterior: evita "loop" e não alisa repetições
               "-bs", "1", "-bo", "1",  # guloso: 2–3× mais rápido; a diferença no texto é pequena
               "-sns",
               "--prompt", PROMPT,
               "-ojf", "-of", out, "-np"]
        if "small" in Path(model).name:
            cmd[cmd.index("-ojf"):cmd.index("-ojf")] = ["-dtw", "small"]
        t = time.time()
        r = subprocess.run(cmd, capture_output=True, **media._hidden_window_kwargs())
        if r.returncode != 0 or not os.path.exists(out + ".json"):
            raise SpeechError((r.stderr or b"").decode(errors="ignore")[-600:])
        raw = json.loads(Path(out + ".json").read_text(encoding="utf-8", errors="replace"))
    words = words_from_whisper_json(raw, offset=start)
    return {"start": round(start, 3), "end": round(end, 3), "seconds": round(time.time() - t, 2),
            "words": [w.to_list() for w in words],
            "segments": [[round(start + s["offsets"]["from"] / 1000, 2), round(start + s["offsets"]["to"] / 1000, 2),
                          s.get("text", "").strip()] for s in raw.get("transcription", [])]}


def transcribe(video_path: str, content: tuple[float, float], cache_dir: str | Path,
               env_db: list[int] | None = None, env_step: float = 0.1,
               progress=None, budget_s: float | None = None) -> dict:
    """Transcreve o conteúdo em pedaços, guardando cada pedaço no cache.

    `budget_s`: para depois desse tempo (pedaço já feito fica guardado);
    o resultado volta com status "parcial". Usado nos testes no Mac.
    """
    cache_dir = Path(cache_dir) / "speech"
    cache_dir.mkdir(parents=True, exist_ok=True)
    chunks = plan_chunks(content, env_db, env_step)
    plan_key = [[round(a, 2), round(b, 2)] for a, b in chunks]
    plan_file = cache_dir / "plan.json"
    old = json.loads(plan_file.read_text()) if plan_file.exists() else None
    if old != {"model": MODEL_NAME, "chunks": plan_key}:
        for f in cache_dir.glob("chunk_*.json"):
            f.unlink()
        plan_file.write_text(json.dumps({"model": MODEL_NAME, "chunks": plan_key}))
    t0 = time.time()
    done: list[dict] = []
    status = "ok"
    last = 0.0
    for k, (a, b) in enumerate(chunks):
        f = cache_dir / f"chunk_{k:03d}.json"
        if f.exists():
            done.append(json.loads(f.read_text(encoding="utf-8")))
        else:
            if budget_s is not None and time.time() - t0 + last * 1.2 > budget_s:
                status = "parcial"
                break
            t = time.time()
            res = transcribe_chunk(video_path, a, b)
            last = time.time() - t
            f.write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
            done.append(res)
        if progress:
            progress((k + 1) / len(chunks))
    words = [w for c in done for w in c["words"]]
    segs = [s for c in done for s in c["segments"]]
    return {"status": status, "model": MODEL_NAME, "chunks": len(chunks), "chunks_done": len(done),
            "seconds": round(sum(c["seconds"] for c in done), 1), "words": words, "segments": segs}


# ------------------------------------------------------------------ avisos

def _words(speech: dict) -> list[Word]:
    return [Word(w[0], w[1], w[2], w[3] if len(w) > 3 else 1.0) for w in speech.get("words", [])]


def find_error_phrases(words: list[Word], phrases: list[str]) -> list[dict]:
    """Frase de erro dita pelo professor. Cada ocorrência vira um aviso."""
    toks = [norm(w.text) for w in words]
    pats = sorted({tuple(norm_phrase(p)) for p in phrases if norm_phrase(p)}, key=len, reverse=True)
    out = []
    taken = set()
    for i in range(len(toks)):
        for pat in pats:
            n = len(pat)
            if tuple(toks[i:i + n]) == pat and not any(j in taken for j in range(i, i + n)):
                taken.update(range(i, i + n))
                a = max(0, i - 6)
                b = min(len(words), i + n + 6)
                out.append({"kind": "speech_phrase", "start": words[i].start, "end": words[i + n - 1].end,
                            "phrase": " ".join(w.text for w in words[i:i + n]).strip(" ,.;:!?"),
                            "context": " ".join(w.text for w in words[a:b]),
                            "match": " ".join(pat)})
                break
    return out


def _is_content(t: str) -> bool:
    return len(t) >= 3 and t not in STOPWORDS


def _similar(a: str, b: str) -> bool:
    """Mesma palavra, aceitando um erro pequeno de transcrição (uma letra)."""
    if a == b:
        return True
    if min(len(a), len(b)) < 5 or abs(len(a) - len(b)) > 1:
        return False
    # distância de edição ≤ 1
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) <= 1
    if len(a) > len(b):
        a, b = b, a
    for k in range(len(b)):
        if b[:k] + b[k + 1:] == a:
            return True
    return False


def _match_len(toks: list[str], i: int, j: int, limit: int) -> int:
    """Quantas palavras seguidas a partir de i e de j são iguais (tolera 1 troca no meio)."""
    n = 0
    miss = 0
    while i + n < limit and j + n < len(toks):
        if _similar(toks[i + n], toks[j + n]):
            n += 1
            continue
        break
    return n


# Palavras que o professor diz ao errar, no trecho entre a tentativa abandonada e o
# recomeço. "Retomando" apareceu em todos os erros do bruto de teste.
CUES = {"retomando", "retomar", "retomo", "opa", "ops", "errei", "desculpa", "desculpe", "perdao",
        "voltar", "volto", "repetir", "repito", "novo", "corta", "cortar", "enganei", "gravar", "regravar"}
REP_PAUSE_S = 1.2          # pausa longa entre a tentativa abandonada e o recomeço…
REP_PAUSE_MAX_ABANDON = 3  # …com no máximo 3 palavras entre as duas (com 5 dava alarme falso:
                           # "…histórico com desfecho. Detecção de anomalias que precisa de histórico")
_END = (".", "?", "!", "…")


def _ends_sentence(w: Word) -> bool:
    t = w.text.rstrip("\"'»”)")
    return t.endswith(_END) and not t.endswith("...")


def find_repeats(words: list[Word], speech_active=None, all_candidates: bool = False) -> list[dict]:
    """Trecho dito, abandonado e dito de novo logo depois (take não cortado).

    Candidato: as mesmas ≥ 4 palavras (≥ 18 letras, ≥ 2 palavras "de conteúdo")
    aparecem duas vezes; a segunda começa até 20 palavras depois do fim da primeira
    e até 25 s depois do começo dela.

    Só vira aviso com um sinal de erro (nas aulas aprovadas, repetir uma frase de
    propósito é comum: "a estratégia de penetração. A estratégia de penetração é…"):
      - reticências no fim da 1ª tentativa ("qualquer... Retomando.");
      - palavra de erro entre as duas ("retomando", "opa", "errei", "de novo"…);
      - a frase inteira dita duas vezes seguidas, igual, do começo ao fim;
      - pausa longa (≥ 1,2 s) entre a 1ª tentativa e o recomeço, com no máximo 3
        palavras no meio.
    `speech_active(t0, t1)` → fração do tempo com fala; descarta repetição em
    silêncio (o Whisper às vezes "inventa" texto repetido em silêncio).
    """
    toks = [norm(w.text) for w in words]
    n = len(toks)
    loop = _loops(toks)
    out = []
    covered_until = -1
    for i in range(n):
        if i <= covered_until or not toks[i] or loop[i]:
            continue
        best = None
        j = i + 1
        while j < n and words[j].start - words[i].start <= REP_MAX_GAP_S:
            if toks[j] == toks[i] or _similar(toks[j], toks[i]):
                L = _match_len(toks, i, j, limit=j)      # 1ª tentativa termina antes da 2ª começar
                abandon = j - (i + L)
                if L >= REP_MIN_WORDS and 0 <= abandon <= REP_MAX_ABANDON_ANY:
                    chars = sum(len(t) for t in toks[i:i + L])
                    content = sum(_is_content(t) for t in toks[i:i + L])
                    if chars >= REP_MIN_CHARS and content >= REP_MIN_CONTENT:
                        best = (j, L, abandon)      # o recomeço mais próximo
                        break
            j += 1
        if best is None:
            continue
        j, L, abandon = best
        a_text = " ".join(w.text for w in words[i:i + L])
        b_end = min(n, j + L)
        if speech_active is not None:
            if speech_active(words[j].start, words[b_end - 1].end) < 0.4 or \
                    speech_active(words[i].start, words[i + L - 1].end) < 0.4:
                covered_until = b_end - 1
                continue
        between = words[i + L - 1:j]                 # último da 1ª tentativa … antes do recomeço
        ellipsis = any("..." in w.text or "…" in w.text for w in between)
        cue = sorted({toks[k] for k in range(i + L, j) if toks[k] in CUES})
        pause = max((words[k + 1].start - words[k].end for k in range(i + L - 1, j)), default=0.0)
        # a mesma frase até o ponto final, duas vezes seguidas ("…de texto. o trabalho … de texto.")
        whole = (abandon == 0 and L >= 6 and _ends_sentence(words[i + L - 1]) and _ends_sentence(words[j + L - 1]))
        reasons = []
        if ellipsis:
            reasons.append("reticências")
        if cue:
            reasons.append("palavra de erro: " + ", ".join(cue))
        if whole:
            reasons.append("frase inteira dita 2 vezes")
        if pause >= REP_PAUSE_S and abandon <= REP_PAUSE_MAX_ABANDON:
            reasons.append(f"pausa de {pause:.1f} s")
        if not reasons and not all_candidates:
            continue
        out.append({"kind": "speech_repeat", "start": words[i].start, "end": words[b_end - 1].end,
                    "restart": words[j].start, "words": L, "abandoned": abandon,
                    "first": a_text, "reasons": reasons, "pause": round(pause, 2),
                    "context": " ".join(w.text for w in words[i:min(n, j + L + 4)])})
        covered_until = j - 1      # a 2ª tentativa ainda pode ser repetida de novo (3º take)
    return out


def _loops(toks: list[str], min_period: int = 2, max_period: int = 20, reps: int = 3) -> list[bool]:
    """Marca palavras de um "loop": o mesmo trecho 3+ vezes seguidas, igualzinho.

    É o defeito típico do Whisper em trecho de silêncio/música. Take repetido de
    verdade quase nunca sai três vezes idêntico e completo.
    """
    n = len(toks)
    mark = [False] * n
    for p in range(min_period, max_period + 1):
        i = 0
        while i + p * reps <= n:
            k = 1
            while i + p * (k + 1) <= n and toks[i + p * k:i + p * (k + 1)] == toks[i:i + p]:
                k += 1
            if k >= reps:
                for x in range(i, i + p * k):
                    mark[x] = True
                i += p * k
            else:
                i += 1
    return mark


def checks(speech: dict, phrases: list[str] | None = None, speech_active=None) -> list[dict]:
    """Avisos da fala, um por erro: frase de erro dentro de um take repetido vira
    motivo do take (não um aviso a mais), e a mesma frase repetida em até 10 s
    ("Vou voltar. Vou voltar onde…") vira um aviso só."""
    words = _words(speech)
    phr = find_error_phrases(words, phrases if phrases is not None else ERROR_PHRASES_DEFAULT)
    reps = find_repeats(words, speech_active)
    keep = []
    for f in phr:
        host = next((r for r in reps if r["start"] - 1.0 <= f["start"] <= r["restart"] + 1.0), None)
        if host is not None:
            why = f"palavra de erro: {f['phrase'].lower()}"
            if not any(f["match"] in x for x in host["reasons"]):
                host["reasons"].append(why)
            continue
        if keep and keep[-1]["match"] == f["match"] and f["start"] - keep[-1]["start"] <= 10.0:
            keep[-1]["end"] = f["end"]
            keep[-1]["count"] = keep[-1].get("count", 1) + 1
            continue
        keep.append(f)
    res = keep + reps
    res.sort(key=lambda r: r["start"])
    return res


def note_for(f: dict) -> str:
    if f["kind"] == "speech_phrase":
        return f"fala: '{f['phrase']}' · possível erro não cortado (conferir)"
    w = f["first"]
    if len(w) > 60:
        w = w[:57].rstrip() + "…"
    why = f" · {f['reasons'][0]}" if f.get("reasons") else ""
    return f"fala repetida: '{w}'{why} · possível take não cortado (conferir)"


def activity_from_envelope(env_db: list[int], step: float, thr: float = -45.0):
    """Função t0,t1 → fração do tempo com som acima de `thr` (pico por janela)."""
    e = np.asarray(env_db, dtype=np.float32) if env_db else np.zeros(0)

    def f(t0: float, t1: float) -> float:
        if e.size == 0:
            return 1.0
        a = max(0, int(t0 / step))
        b = min(e.size, max(a + 1, int(np.ceil(t1 / step))))
        seg = e[a:b]
        return float((seg > thr).mean()) if seg.size else 0.0
    return f
