"""Análise de áudio: níveis em dB, avisos e envelope para a forma de onda.

Unidade base: janelas de 10 ms. Tudo é calculado em uma passada só,
sem guardar o áudio inteiro na memória.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from . import media

WIN = 0.010          # janela base (s)
ENV_STEP = 0.100     # resolução do envelope mandado para a interface (s)
SILENCE_DB = -80.0   # abaixo disso é silêncio digital (corte de edição)
ACTIVE_DB = -45.0    # acima disso consideramos que tem fala/música
GAP_EDGE_DB = -40.0  # 10 ms antes do silêncio ainda nesse volume = corte seco no áudio
GAP_START_DB = -18.0 # 10 ms depois do silêncio já nesse volume = fala começa cortada
                     # (-30 dava alarme em início de frase normal: o gate abre rápido)
JUMP_WIN_S = 3.0     # janelas de comparação da mudança de volume (antes 1,5 s)
JUMP_DB = 10.0
NOISE_STABLE_SEGS = 4   # trechos de 5 s que precisam ficar iguais antes e depois
NOISE_SPREAD_DB = 6.0
NOISE_DB = 13.0         # mudança mínima do ruído de fundo. Nas aulas aprovadas, quedas de
                        # 9–12 dB eram inaudíveis (o JP conferiu com a caixa no máximo)
# Corte no meio da fala (etapa 2b): o editor cortou (jump cut) no meio de uma
# palavra. Só é procurado nos cortes do vídeo: lá, se há fala dos dois lados E o
# som "pula" (emenda), vira aviso. Troca de câmera (plano aberto/close) tem o mesmo
# corte no vídeo, mas o áudio é contínuo: não pula.
# Como medir o pulo: cada 10 ms do áudio é "previsto" (predição linear, LPC) a partir
# dos 30 ms anteriores. Na emenda a previsão erra num estalo isolado (s1: pico do
# erro × maior pico dos vizinhos a 4–25 ms) e continua errando logo depois (s2).
# Nos pulsos normais da voz o erro se repete a cada período, parecido com os vizinhos.
# Calibrado com emendas plantadas em áudio real (tools/cut_diag2.py e cut_diag3.py):
#  - em qualquer ponto da aula dava 3 a 5 alarmes falsos por minuto nas aulas
#    aprovadas (desligado: CUT_ANYWHERE = False);
#  - junto do corte do vídeo (±2 frames), s1 ≥ 12 e s2 ≥ 3 pegam ~55% das emendas;
#    chance de alarme falso numa troca de câmera ~1%.
#  - em 16 kHz quase nenhuma emenda aparece (testado): fica em 48 kHz.
CUT_MS = 0.001
LPC_ORDER = 16
CUT_SPEECH_DB = -35.0       # fala dos dois lados (RMS 5–25 ms antes e depois)
CUT_ANYWHERE = False
CUT_S1, CUT_S2 = 20.0, 10.0           # (só se CUT_ANYWHERE)
CUT_NEAR_S1, CUT_NEAR_S2 = 12.0, 3.0  # junto de um corte do vídeo
CUT_NEAR_S = 0.07                     # "junto" = até ~2 frames


def db(x):
    return 20.0 * np.log10(np.maximum(x, 1e-10))


@dataclass
class AudioEvent:
    kind: str          # clip | spike | gap | level_jump | noise_change | long_silence | speech_cut
    start: float
    end: float
    value: float       # dB relevante para o tipo (ex.: pico, variação)
    note: str = ""

    def to_dict(self):
        return {"kind": self.kind, "start": round(self.start, 3), "end": round(self.end, 3),
                "value": round(float(self.value), 1), "note": self.note}


@dataclass
class AudioResult:
    duration: float
    peak_dbfs: float
    peak_time: float
    min_db: float
    min_time: float
    avg_db: float
    floor_db: float
    lufs: float | None
    lra: float | None
    true_peak_dbfs: float | None
    envelope_db: list[int]           # pico por janela de 100 ms (dBFS arredondado)
    events: list[AudioEvent] = field(default_factory=list)

    def to_dict(self):
        return {
            "duration": round(self.duration, 3),
            "peak_dbfs": round(self.peak_dbfs, 1), "peak_time": round(self.peak_time, 2),
            "min_db": round(self.min_db, 1), "min_time": round(self.min_time, 2),
            "avg_db": round(self.avg_db, 1), "floor_db": round(self.floor_db, 1),
            "lufs": self.lufs, "lra": self.lra, "true_peak_dbfs": self.true_peak_dbfs,
            "envelope_step": ENV_STEP, "envelope_db": self.envelope_db,
            "events": [e.to_dict() for e in self.events],
        }


def _windows(path: str, sr: int, loud: dict, fine: dict | None = None, progress=None, duration: float | None = None):
    """Pico, soma de quadrados e contagem de amostras saturadas por janela de 10 ms.

    Se `fine` for um dicionário, recebe também, por janela de 1 ms, a energia
    ("e") e o erro da predição linear (pico "res_peak" e energia "res_pow").
    """
    n = int(sr * WIN)
    peaks, sq, clips = [], [], []
    e1, h1, r1 = [], [], []
    hist = np.zeros(0)
    rest = np.zeros(0, np.float32)
    done = 0
    for chunk in media.iter_audio(path, sr, loudness=loud):
        done += chunk.size
        if progress and duration:          # a barra anda na leitura do áudio (antes ficava parada em 93%)
            progress(min(done / sr / duration, 1.0))
        x = np.concatenate([rest, chunk]) if rest.size else chunk
        m = (x.size // n) * n
        if m:
            w = x[:m].reshape(-1, n)
            a = np.abs(w)
            peaks.append(a.max(axis=1))
            sq.append((w.astype(np.float64) ** 2).sum(axis=1))
            clips.append((a >= 0.999).sum(axis=1))
            if fine is not None:
                xm = x[:m].astype(np.float64)
                yh = np.concatenate([hist, xm])
                skip = hist.size
                y = yh[skip:]
                res = _lpc_residual(yh, sr)[skip:]
                k1 = sr // 1000
                nb = y.size // k1
                e1.append((y[:nb * k1].reshape(-1, k1) ** 2).mean(axis=1))
                h1.append(np.abs(res[:nb * k1]).reshape(-1, k1).max(axis=1))
                r1.append((res[:nb * k1].reshape(-1, k1) ** 2).mean(axis=1))
                hist = xm[-int(0.06 * sr):]
        rest = x[m:].copy()
    if fine is not None:
        fine["e"] = np.concatenate(e1) if e1 else np.zeros(0)
        fine["res_peak"] = np.concatenate(h1) if h1 else np.zeros(0)
        fine["res_pow"] = np.concatenate(r1) if r1 else np.zeros(0)
    if not peaks:
        return np.zeros(0), np.zeros(0), np.zeros(0), n
    return np.concatenate(peaks), np.concatenate(sq), np.concatenate(clips), n


def _levinson(r: np.ndarray, order: int):
    a = np.zeros(order + 1)
    a[0] = 1.0
    e = r[0]
    if e <= 1e-12:
        return None
    for i in range(1, order + 1):
        k = -(r[i] + np.dot(a[1:i], r[i - 1:0:-1])) / e
        a[1:i + 1] = a[1:i + 1] + k * np.concatenate([a[1:i][::-1], [1.0]])
        e *= (1.0 - k * k)
        if e <= 1e-15:
            return None
    return a


def _lpc_residual(x: np.ndarray, sr: int) -> np.ndarray:
    """Erro da previsão de cada bloco de 10 ms pelo modelo dos 30 ms anteriores."""
    hop, ctx, p = int(sr * 0.010), int(sr * 0.030), LPC_ORDER
    res = np.zeros_like(x)
    if x.size < ctx + hop:
        return res
    win = np.hanning(ctx)
    for s0 in range(ctx, x.size - hop + 1, hop):
        seg = x[s0 - ctx:s0] * win
        r = np.array([np.dot(seg[:ctx - k], seg[k:]) for k in range(p + 1)])
        a = _levinson(r, p)
        if a is None:
            continue
        blk = np.lib.stride_tricks.sliding_window_view(x[s0 - p:s0 + hop], p + 1)[:, ::-1]
        res[s0:s0 + hop] = blk @ a
    return res


def _around(x: np.ndarray, lo: int, hi: int, fn) -> np.ndarray:
    """fn(x[k+lo … k+hi]) para cada k (bordas preenchidas com zero)."""
    pad = max(-lo, hi, 0)
    xp = np.concatenate([np.zeros(pad), x, np.zeros(pad)])
    w = np.lib.stride_tricks.sliding_window_view(xp, 2 * pad + 1)
    return fn(w[:, pad + lo:pad + hi + 1], axis=1)


def cut_scores(e1: np.ndarray, res_peak: np.ndarray, res_pow: np.ndarray):
    """Por ms: s1 (estalo isolado), s2 (erro continua depois), nível antes/depois (dB)."""
    ctx = np.maximum(_around(res_peak, -25, -4, np.max), _around(res_peak, 4, 25, np.max))
    s1 = 20 * np.log10((res_peak + 1e-9) / (ctx + 1e-9))
    s2 = 10 * np.log10((_around(res_pow, 2, 11, np.mean) + 1e-12) / (_around(res_pow, -15, -6, np.mean) + 1e-12))
    rb = 10 * np.log10(_around(e1, -25, -5, np.mean) + 1e-12)
    ra = 10 * np.log10(_around(e1, 5, 25, np.mean) + 1e-12)
    return s1, s2, rb, ra


def find_speech_cuts(e1: np.ndarray, res_peak: np.ndarray, res_pow: np.ndarray,
                     video_cuts: list[float] | None = None, details: bool = False) -> list[dict]:
    """Emendas no meio da fala. `video_cuts`: tempos (s) dos cortes do vídeo, onde a
    regra é mais sensível. Devolve [{"t", "s1", "s2", "near_cut"}]."""
    n = res_peak.size
    if n < 100:
        return []
    s1, s2, rb, ra = cut_scores(e1, res_peak, res_pow)
    speech = (rb > CUT_SPEECH_DB) & (ra > CUT_SPEECH_DB)
    near = np.zeros(n, bool)
    for t in video_cuts or []:
        k = int(round(t / CUT_MS))
        w = int(CUT_NEAR_S / CUT_MS)
        near[max(0, k - w):min(n, k + w + 1)] = True
    hit = speech & near & (s1 >= CUT_NEAR_S1) & (s2 >= CUT_NEAR_S2)
    if CUT_ANYWHERE:
        hit |= speech & (s1 >= CUT_S1) & (s2 >= CUT_S2)
    hit[:50] = False
    hit[-50:] = False
    out = []
    for k in np.flatnonzero(hit):
        if out and k * CUT_MS - out[-1]["t"] < 0.05:      # mesma emenda
            if s1[k] > out[-1]["s1"]:
                out[-1].update(t=k * CUT_MS, s1=float(s1[k]), s2=float(s2[k]))
            continue
        d = {"t": k * CUT_MS, "s1": float(s1[k]), "s2": float(s2[k]), "near_cut": bool(near[k])}
        if details:
            d.update(rb=float(rb[k]), ra=float(ra[k]))
        out.append(d)
    return out


def _rms_db(sq: np.ndarray, n: int, k: int) -> np.ndarray:
    """RMS em dB de janelas de k×10 ms, uma por janela base (média móvel centrada)."""
    if sq.size == 0:
        return sq
    ker = np.ones(k) / k
    m = np.convolve(sq / n, ker, mode="same")
    return 10.0 * np.log10(np.maximum(m, 1e-20))


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """Trechos contínuos onde mask é True: [(início, fim_exclusivo), ...]."""
    if mask.size == 0:
        return []
    d = np.diff(np.concatenate([[0], mask.astype(np.int8), [0]]))
    return list(zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1)))


def _merge(events: list[AudioEvent], gap: float) -> list[AudioEvent]:
    out: list[AudioEvent] = []
    for e in sorted(events, key=lambda e: e.start):
        if out and out[-1].kind == e.kind and e.start - out[-1].end <= gap:
            out[-1].end = max(out[-1].end, e.end)
            out[-1].value = max(out[-1].value, e.value)
        else:
            out.append(e)
    return out


def analyze(path: str, sr: int = 48000, content: tuple[float, float] | None = None,
            speech_cuts: bool = True, video_cuts: list[float] | None = None,
            progress=None, duration: float | None = None) -> AudioResult:
    """`content` = (início, fim) em segundos do trecho entre as vinhetas.
    `progress(0..1)` é chamado enquanto o áudio é lido (precisa de `duration`)."""
    loud: dict = {}
    fine: dict | None = {} if speech_cuts else None
    peaks, sq, clips, n = _windows(path, sr, loud, fine, progress, duration)
    total = peaks.size
    dur = total * WIN
    if total == 0:
        return AudioResult(0, -120, 0, -120, 0, -120, -120, None, None, None, [], [])

    # ---- envelope do arquivo inteiro (pico por 100 ms), incluindo vinhetas
    full_db = db(peaks)
    step = int(round(ENV_STEP / WIN))
    m = (total // step) * step
    env = full_db[:m].reshape(-1, step).max(axis=1) if m else full_db
    if total > m:
        env = np.concatenate([env, [full_db[m:].max()]])
    envelope = [int(max(-90, round(v))) for v in env]

    # ---- números e avisos só no conteúdo (sem as vinhetas)
    off = 0.0
    if content is not None:
        a0 = max(0, int(content[0] / WIN))
        a1 = min(total, int(np.ceil(content[1] / WIN)))
        if a1 - a0 > 100:
            peaks, sq, clips = peaks[a0:a1], sq[a0:a1], clips[a0:a1]
            off = a0 * WIN
            total = peaks.size

    peak_db = db(peaks)
    r50 = _rms_db(sq, n, 5)      # 50 ms
    r400 = _rms_db(sq, n, 40)    # 400 ms
    events: list[AudioEvent] = []

    # ---- números do resumo
    i_pk = int(np.argmax(peaks))
    active = r400 > ACTIVE_DB
    raw_sil = db(np.sqrt(sq / n)) < SILENCE_DB
    # janelas a menos de 0,4 s de um silêncio digital não contam para o mínimo
    near_sil = np.convolve(raw_sil.astype(np.int8), np.ones(81, np.int8), mode="same") > 0
    not_digital_silence = (r400 > SILENCE_DB) & ~near_sil
    valid = np.flatnonzero(not_digital_silence)
    if valid.size:
        i_min = int(valid[np.argmin(r400[valid])])
        min_db = float(r400[i_min])
    else:
        i_min, min_db = 0, -120.0
    if active.any():
        avg_db = float(10 * np.log10(np.mean(10 ** (r400[active] / 10))))
    else:
        avg_db = float(np.median(r400))
    floor_db = float(np.percentile(r50[not_digital_silence], 10)) if valid.size else -120.0

    # ---- clipping: 3+ amostras saturadas numa janela
    for a, b in _runs(clips >= 3):
        events.append(AudioEvent("clip", float(a * WIN), float(b * WIN), float(peak_db[a:b].max()), "áudio estourando"))

    # ---- pico: 50 ms muito acima do nível da fala ao redor
    half = int(3.0 / WIN)
    hop = int(0.5 / WIN)
    local = np.full(total, -120.0)
    for c in range(0, total, hop):
        a, b = max(0, c - half), min(total, c + half)
        seg = r50[a:b]
        act = seg[seg > ACTIVE_DB]
        local[c:c + hop] = np.median(act) if act.size > 20 else ACTIVE_DB
    spike = (r50 > local + 9.0) & (peak_db > -6.0)
    for a, b in _runs(spike):
        if (b - a) * WIN <= 1.5:
            events.append(AudioEvent("spike", float(a * WIN), float(b * WIN), float(peak_db[a:b].max()), "pico de volume"))

    # ---- buraco / queda brusca: silêncio digital colado em fala
    # As aulas do núcleo passam por um "gate"/redutor de ruído: entre as frases o
    # áudio vai a silêncio digital, mas DESCENDO aos poucos (dezenas de ms).
    # Corte de edição é diferente: a fala está no volume normal nos 10 ms
    # imediatamente antes do silêncio (ou começa no meio, já alta, logo depois).
    rms10 = db(np.sqrt(sq / n))
    sil = rms10 < SILENCE_DB
    for a, b in _runs(sil):
        if (b - a) * WIN < 0.15 or a == 0 or b >= total:
            continue
        lv_before = float(rms10[a - 1])
        lv_after = float(rms10[b]) if b < total else -120.0
        abrupt_in = lv_before > GAP_EDGE_DB
        abrupt_out = lv_after > GAP_START_DB
        if abrupt_in or abrupt_out:
            events.append(AudioEvent("gap", float(a * WIN), float(b * WIN), max(lv_before, lv_after),
                                     "áudio corta de repente" if abrupt_in else "áudio volta de repente"))

    # ---- mudança de volume: mediana da fala antes × depois
    w = int(JUMP_WIN_S / WIN)
    jumps = []
    for c in range(w, total - w, hop):
        L = r50[c - w:c]
        R = r50[c:c + w]
        la, ra = L[L > ACTIVE_DB], R[R > ACTIVE_DB]
        if la.size > 0.4 * w and ra.size > 0.4 * w:
            dv = float(np.median(ra) - np.median(la))
            if abs(dv) >= JUMP_DB:
                jumps.append((c, dv))
    # supressão: fica o maior de cada vizinhança de 3 s
    jumps.sort(key=lambda j: -abs(j[1]))
    kept: list[tuple[int, float]] = []
    for c, dv in jumps:
        if all(abs(c - k) > int(3.0 / WIN) for k, _ in kept):
            kept.append((c, dv))
    for c, dv in kept:
        events.append(AudioEvent("level_jump", c * WIN, c * WIN + 0.5, dv,
                                 f"volume {'sobe' if dv > 0 else 'cai'} {abs(dv):.0f} dB"))

    # ---- ruído de fundo: medido só nas pausas da fala, em trechos de 5 s
    # pausas coladas no silêncio digital (rabicho do gate) não valem como ruído
    near_gate = np.convolve(sil.astype(np.int8), np.ones(31, np.int8), mode="same") > 0
    seg = int(5.0 / WIN)
    floors: list[tuple[int, float]] = []
    for a in range(0, total - seg + 1, seg):
        s = r50[a:a + seg]
        s = s[(s > SILENCE_DB) & ~near_gate[a:a + seg]]
        if s.size < seg * 0.3:
            continue
        med = np.median(s)
        pauses = s[s < med - 12.0]
        if pauses.size >= 10:              # pelo menos 100 ms de pausa no trecho
            floors.append((a, float(np.median(pauses))))
    # Precisa ficar: 4 trechos (≈20 s) estáveis antes e 4 depois. Nas aulas reais,
    # com o gate, o "ruído" medido nas pausas sobe e desce o tempo todo (±10 dB
    # alternando) sem mudança real; uma mudança de verdade (ar-condicionado
    # ligado num take) fica.
    # Perto do fim da aula não dá para esperar 20 s: vale o que sobrar.
    K = NOISE_STABLE_SEGS
    for k in range(K, len(floors)):
        bvals = [f for _, f in floors[k - K:k]]
        avals = [f for _, f in floors[k:k + K]]
        if len(avals) < K and floors[-1][0] < total - 2 * seg:
            continue      # faltam trechos medidos no meio da aula (muita fala): não decide
        before = float(np.mean(bvals))
        after = float(np.mean(avals))
        dv = after - before
        stable = (max(bvals) - min(bvals) <= NOISE_SPREAD_DB) and (max(avals) - min(avals) <= NOISE_SPREAD_DB)
        if abs(dv) >= NOISE_DB and stable:
            a = floors[k][0]
            # acha o ponto exato: primeiro instante em que o mínimo de 1 s cruza a metade do salto
            lo, hi = max(0, a - seg), min(total, a + 2 * seg)
            mid = before + dv / 2
            sub = []
            for s0 in range(lo, hi - 100, 25):          # janelas de 1 s, passo de 0,25 s
                w1 = r50[s0:s0 + 100]
                w1 = w1[w1 > SILENCE_DB]
                if w1.size < 50:
                    continue
                p = w1[w1 < np.median(w1) - 12.0]
                if p.size >= 5:
                    sub.append((s0, float(np.median(p))))
            for j, (s0, fl) in enumerate(sub):
                nxt = [f for _, f in sub[j:j + 6]]
                if (dv > 0 and all(f > mid for f in nxt)) or (dv < 0 and all(f < mid for f in nxt)):
                    a = s0
                    break
            events.append(AudioEvent("noise_change", a * WIN, a * WIN + 5.0, float(dv),
                                     f"ruído de fundo {'sobe' if dv > 0 else 'cai'} {abs(dv):.0f} dB"))
    # só o primeiro de mudanças seguidas do mesmo sentido
    nc = [e for e in events if e.kind == "noise_change"]
    for prev, cur in zip(nc, nc[1:]):
        if cur.start - prev.start <= 10.0 and np.sign(cur.value) == np.sign(prev.value):
            events.remove(cur)

    # ---- silêncio longo (≥ 3 s sem fala, mas sem ser silêncio digital)
    quiet = (r400 < max(floor_db + 6.0, -55.0)) & ~sil
    for a, b in _runs(quiet):
        if (b - a) * WIN >= 3.0:
            events.append(AudioEvent("long_silence", a * WIN, b * WIN, float(np.median(r400[a:b])),
                                     "silêncio longo"))

    # ---- corte no meio da fala (emenda sem transição)
    if fine is not None and fine["e"].size:
        f0 = int(round(off / CUT_MS))
        f1 = f0 + int(round(total * WIN / CUT_MS))
        vc = [t - off for t in (video_cuts or []) if off <= t <= off + total * WIN]
        for c in find_speech_cuts(fine["e"][f0:f1], fine["res_peak"][f0:f1], fine["res_pow"][f0:f1], vc):
            t = c["t"]
            note = "corte no meio da fala · conferir"
            events.append(AudioEvent("speech_cut", t, t + 0.05, c["s1"], note))

    events = _merge(events, 0.5)
    events.sort(key=lambda e: e.start)
    for e in events:
        e.start = float(e.start + off)
        e.end = float(e.end + off)
    return AudioResult(
        duration=dur, peak_dbfs=float(peak_db[i_pk]), peak_time=i_pk * WIN + off,
        min_db=min_db, min_time=i_min * WIN + off, avg_db=avg_db, floor_db=floor_db,
        lufs=loud.get("lufs"), lra=loud.get("lra"), true_peak_dbfs=loud.get("true_peak_dbfs"),
        envelope_db=envelope, events=events,
    )
