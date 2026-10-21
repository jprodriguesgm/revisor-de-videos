"""Leitura do texto que aparece na tela (OCR), com o Tesseract.

Não lemos o vídeo inteiro: só os frames em que a etapa 1 já achou algo
(texto que entrou, texto que saiu sem ter sido visto entrando, slide que
mudou, frame logo depois de cada corte) e uma varredura do começo do
conteúdo (3 frames/s nos primeiros 45 s) para achar a tarja de nome, que
entra animada e às vezes fica só 1–2 s antes de um corte.

Cada leitura guarda linhas e palavras com a posição na tela (0–1) e a
confiança do Tesseract (0–100). A ortografia (spell.py) e a tarja de nome
(nametag.py) usam essas leituras; dá para refazer as duas sem ler o vídeo de
novo (por exemplo, quando o JP aceita uma palavra na lista própria).
"""
from __future__ import annotations

import io
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

from . import media
from .timecode import Rate

LANGS = "por"              # só português: o "por+eng" perde acentos (testado) e o "por" lê bem os termos em inglês
MIN_LINE_CONF = 45.0       # linha com confiança média abaixo disso é ruído (fundo, roupa…)
CROP_MARGIN_X = 0.035      # margem em volta da região do texto (fração da tela)
CROP_MARGIN_Y = 0.06
AFTER_CUT = 20             # frames depois do corte (o slide leva ~12 para assentar)
SETTLE = 4                 # frames antes da saída do texto (ainda inteiro na tela)
TEXT_READ_DELAY = 30       # texto que entrou: lê 1 s depois (entrada em "wipe"/letra por letra
                           # ainda está pela metade logo no começo; visto nas aulas reais)
TAG_SCAN_FPS = int(os.environ.get("REVISOR_SCAN_FPS", "3"))   # varredura da tarja: frames/s no começo
STATIC_DIFF = 0.6          # varredura: frame praticamente igual ao anterior (slide parado) não é relido
SCAN_BATCH = 9             # varredura: frames por chamada do Tesseract (3 s)


class OCRError(RuntimeError):
    pass


# ---------------------------------------------------------------- Tesseract

def data_dir() -> Path:
    base = getattr(sys, "_MEIPASS", None)  # app empacotado (PyInstaller)
    if base and (Path(base) / "revisor" / "data").is_dir():
        return Path(base) / "revisor" / "data"
    return Path(__file__).resolve().parent / "data"


def tessdata_dir() -> Path:
    if os.environ.get("REVISOR_TESSDATA"):
        return Path(os.environ["REVISOR_TESSDATA"])
    return data_dir() / "tessdata"


_TESS = None


def tesseract() -> str:
    global _TESS
    if _TESS is None:
        try:
            _TESS = media.find_tool("tesseract")
        except media.MediaError as e:
            raise OCRError("Tesseract não encontrado (leitura do texto da tela desligada)") from e
    return _TESS


def available() -> bool:
    try:
        tesseract()
    except OCRError:
        return False
    return (tessdata_dir() / "por.traineddata").is_file()


@dataclass
class Word:
    text: str
    conf: float
    box: tuple[float, float, float, float]      # x, y, w, h (0–1, tela inteira)
    reread: str | None = None                   # releitura ampliada (só das palavras suspeitas)
    cut: bool = False                           # encostada na borda da tela (palavra cortada)

    def to_dict(self):
        d = {"text": self.text, "conf": round(self.conf, 1), "box": [round(v, 4) for v in self.box]}
        if self.reread is not None:
            d["reread"] = self.reread
        if self.cut:
            d["cut"] = True
        return d


@dataclass
class Line:
    words: list[Word] = field(default_factory=list)

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)

    @property
    def conf(self) -> float:
        return float(np.mean([w.conf for w in self.words])) if self.words else 0.0

    @property
    def box(self) -> tuple[float, float, float, float]:
        x0 = min(w.box[0] for w in self.words)
        y0 = min(w.box[1] for w in self.words)
        x1 = max(w.box[0] + w.box[2] for w in self.words)
        y1 = max(w.box[1] + w.box[3] for w in self.words)
        return (x0, y0, x1 - x0, y1 - y0)

    def to_dict(self):
        return {"text": self.text, "conf": round(self.conf, 1), "box": [round(v, 4) for v in self.box],
                "words": [w.to_dict() for w in self.words]}


def run_tesseract(img: np.ndarray, psm: int, invert_auto: bool, langs: str = LANGS) -> list[list[str]]:
    """Roda o Tesseract numa imagem cinza (uint8) e devolve as linhas do TSV."""
    buf = io.BytesIO()
    # PGM (sem compressão): o Tesseract do app é montado sem bibliotecas de imagem
    # (só lê PNM), e assim ainda fica mais rápido que PNG.
    Image.fromarray(img).save(buf, "PPM")
    cmd = [tesseract(), "stdin", "stdout", "--tessdata-dir", str(tessdata_dir()),
           "-l", langs, "--psm", str(psm),
           "-c", "tessedit_create_txt=0", "-c", "tessedit_create_tsv=1",
           "-c", f"tessedit_do_invert={1 if invert_auto else 0}"]
    env = dict(os.environ, OMP_THREAD_LIMIT="1")   # mais rápido com vários Tesseracts seguidos
    r = subprocess.run(cmd, input=buf.getvalue(), capture_output=True, env=env,
                       **media._hidden_window_kwargs())
    if r.returncode != 0:
        raise OCRError(r.stderr.decode(errors="ignore")[-300:])
    rows = []
    for ln in r.stdout.decode("utf-8", errors="ignore").splitlines()[1:]:
        c = ln.split("\t")
        if len(c) == 12 and c[0] == "5" and c[11].strip():
            rows.append(c)
    return rows


def _lines_from_rows(rows, x0: int, y0: int, scale: float, W: int, H: int) -> list[Line]:
    lines: dict[tuple, Line] = {}
    for c in rows:
        key = (int(c[1]), int(c[2]), int(c[3]), int(c[4]))
        left, top, w, h = (int(c[6]), int(c[7]), int(c[8]), int(c[9]))
        conf = float(c[10])
        box = ((x0 + left / scale) / W, (y0 + top / scale) / H, (w / scale) / W, (h / scale) / H)
        lines.setdefault(key, Line()).words.append(Word(c[11].strip(), conf, box))
    return list(lines.values())


def text_is_light(gray: np.ndarray) -> bool:
    """Texto claro sobre fundo escuro? (o texto é a classe com menos pixels)"""
    hist = np.bincount(gray.ravel(), minlength=256).astype(np.float64)
    total = hist.sum()
    if total == 0:
        return False
    # limiar de Otsu
    omega = np.cumsum(hist) / total
    mu = np.cumsum(hist * np.arange(256)) / total
    mu_t = mu[-1]
    with np.errstate(divide="ignore", invalid="ignore"):
        sb = (mu_t * omega - mu) ** 2 / (omega * (1 - omega))
    t = int(np.nanargmax(sb))
    bright = hist[t + 1:].sum() / total
    return bright < 0.5


def read_image(gray: np.ndarray, region: tuple[float, float, float, float] | None,
               W: int, H: int) -> list[Line]:
    """Lê o texto de um frame cinza (Y) inteiro ou de uma região dele."""
    if region is None:
        rows = run_tesseract(gray, psm=11, invert_auto=True)
        lines = _lines_from_rows(rows, 0, 0, 1.0, W, H)
    else:
        x, y, w, h = region
        x0 = max(0, int((x - CROP_MARGIN_X) * W))
        x1 = min(W, int(np.ceil((x + w + CROP_MARGIN_X) * W)))
        y0 = max(0, int((y - CROP_MARGIN_Y) * H))
        y1 = min(H, int(np.ceil((y + h + CROP_MARGIN_Y) * H)))
        inner = gray[y0:y1, x0:x1]
        if inner.size == 0:
            return []
        light = text_is_light(inner)
        # lê a FAIXA inteira (largura toda da tela) nas linhas do texto: a região
        # achada na etapa 1 corta o texto que passa por cima do professor
        crop = gray[y0:y1, :]
        if light:
            crop = 255 - crop
        # texto pequeno lê melhor um pouco maior
        scale = 1.0
        if crop.shape[0] < 120:
            scale = 2.0
            crop = np.asarray(Image.fromarray(crop).resize((crop.shape[1] * 2, crop.shape[0] * 2),
                                                           Image.LANCZOS))
        rows = run_tesseract(crop, psm=11, invert_auto=False)
        lines = _lines_from_rows(rows, 0, y0, scale, W, H)
    _mark_cut_words(lines, W)
    return [ln for ln in lines if _useful(ln)]


def _iou(a, b) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    iw = max(0.0, min(ax + aw, bx + bw) - max(ax, bx))
    ih = max(0.0, min(ay + ah, by + bh) - max(ay, by))
    inter = iw * ih
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


# ---------------------------------------------------------------- varredura da tarja

BOX = 6                    # bloco de 6×6 px (meia resolução) para achar linhas de texto
EDGE_T = 35                # diferença entre pixels vizinhos que conta como borda de letra
DENSITY_T = 0.12           # fração do bloco com bordas para ser "texto"
CANVAS_MAX_H = 4000        # altura máxima da imagem montada para uma chamada do Tesseract
STACK_MODES = (11,)        # leitura da pilha: "texto espalhado" (psm 11). Nas 10 tarjas reais,
                           # com as 4 versões de cada recorte, empatou com psm 4 e com 4+11 (o
                           # dobro do tempo); psm 6 perdia tarjas
STACK_TEXT_H = 90          # altura do recorte (linha de texto + margem) depois de ajustar o tamanho


def _otsu(c: np.ndarray) -> int:
    hist = np.bincount(c.ravel(), minlength=256).astype(np.float64)
    tot = hist.sum()
    om = np.cumsum(hist) / tot
    mu = np.cumsum(hist * np.arange(256)) / tot
    with np.errstate(divide="ignore", invalid="ignore"):
        sb = (mu[-1] * om - mu) ** 2 / (om * (1 - om))
    return int(np.nanargmax(sb))


def find_text_boxes(g: np.ndarray) -> list[tuple[int, int, int, int]]:
    """Retângulos com cara de linha de texto (muitas bordas de letra lado a lado).

    Funciona com texto claro ou escuro, em caixa colorida ou direto na imagem —
    a página inteira no Tesseract não acha a tarja quando o fundo é degradê ou
    tem o professor (testado). Devolve (x0, y0, x1, y1) em pixels de `g`.
    """
    from .video import _components
    gf = g.astype(np.int16)
    gx = np.abs(np.diff(gf, axis=1, append=gf[:, -1:]))
    gy = np.abs(np.diff(gf, axis=0, append=gf[-1:, :]))
    strong = ((gx > EDGE_T) | (gy > EDGE_T)).astype(np.float32)
    H, W = g.shape
    gh, gw = H // BOX, W // BOX
    dens = strong[:gh * BOX, :gw * BOX].reshape(gh, BOX, gw, BOX).mean(axis=(1, 3))
    m = dens > DENSITY_T
    # junta as letras de uma linha (fecha buracos na horizontal)
    k = 3
    pad = np.pad(m, ((0, 0), (k, k))).astype(np.int32)
    cs = np.cumsum(pad, axis=1)
    win = cs[:, 2 * k:] - np.concatenate([np.zeros((gh, 1), np.int32), cs[:, :-2 * k - 1]], axis=1)
    dil = win > 0
    boxes = []
    for pts in _components(dil):
        y0, x0 = pts.min(0)
        y1, x1 = pts.max(0) + 1
        for ya, yb in _row_bands(m, y0, y1, x0, x1):
            xs = np.flatnonzero(m[ya:yb, x0:x1].any(axis=0))
            if not len(xs):
                continue
            xa, xb = x0 + xs[0], x0 + xs[-1] + 1
            h, w = yb - ya, xb - xa
            if h < 2 or h > 20 or w < 4 or w < 1.2 * h:
                continue
            if m[ya:yb, xa:xb].mean() < 0.25:
                continue
            boxes.append((int(xa * BOX), int(ya * BOX), int(xb * BOX), int(yb * BOX)))
    return boxes


def _row_bands(m: np.ndarray, y0: int, y1: int, x0: int, x1: int) -> list[tuple[int, int]]:
    """Mancha alta demais ou rala (texto grudado na moldura da caixa ou no cenário) é
    cortada em faixas de linhas com muitas bordas; mancha que já é uma linha fica inteira."""
    if y1 - y0 <= 20 and m[y0:y1, x0:x1].mean() >= 0.25:
        return [(y0, y1)]
    frac = m[y0:y1, x0:x1].mean(axis=1)
    on = frac > 0.2
    out = []
    k = 0
    while k < len(on):
        if not on[k]:
            k += 1
            continue
        j = k
        while j < len(on) and on[j]:
            j += 1
        out.append((y0 + k, y0 + j))
        k = j
    return out


def half(g: np.ndarray) -> np.ndarray:
    """Meia resolução (média de 2×2 pixels)."""
    h, w = g.shape[0] // 2 * 2, g.shape[1] // 2 * 2
    return g[:h, :w].reshape(h // 2, 2, w // 2, 2).mean(axis=(1, 3)).astype(np.uint8)


def _longest_run(b: np.ndarray) -> np.ndarray:
    """Maior sequência de pixels pretos seguidos em cada linha de `b` (bool)."""
    out = np.zeros(b.shape[0], np.int32)
    for i, row in enumerate(b):
        if not row.any():
            continue
        d = np.diff(np.concatenate([[0], row.astype(np.int8), [0]]))
        starts, ends = np.flatnonzero(d == 1), np.flatnonzero(d == -1)
        out[i] = int((ends - starts).max())
    return out


def _erase_thin_lines(c: np.ndarray, frac: float = 0.6, max_thick: int = 8) -> None:
    """Apaga linhas retas finas (borda da caixa da tarja) de um recorte preto e branco.

    Borda é um traço CONTÍNUO de mais de 60% da largura e fino (até 8 px).
    Letra grande e em negrito tem espaço entre as letras: não é apagada.
    """
    for axis in (1, 0):
        b = (c == 0) if axis == 1 else (c == 0).T
        full = _longest_run(b) > frac * b.shape[1]
        k, n = 0, len(full)
        while k < n:
            if not full[k]:
                k += 1
                continue
            j = k
            while j < n and full[j]:
                j += 1
            if j - k <= max_thick:
                if axis == 1:
                    c[k:j, :] = 255
                else:
                    c[:, k:j] = 255
            k = j


def _clear_border_blobs(c: np.ndarray, max_iter: int = 400) -> None:
    """Pinta de branco o que é preto e encosta na borda do recorte.

    Fundo escuro em volta de uma tarja clara (ou a moldura da caixa) vira uma
    mancha grande grudada na borda e confunde o Tesseract; as letras ficam no
    meio do recorte (há margem) e não são tocadas.
    """
    black = c == 0
    reach = np.zeros_like(black)
    reach[0, :] = black[0, :]
    reach[-1, :] = black[-1, :]
    reach[:, 0] |= black[:, 0]
    reach[:, -1] |= black[:, -1]
    for _ in range(max_iter):
        grow = reach.copy()
        grow[1:, :] |= reach[:-1, :]
        grow[:-1, :] |= reach[1:, :]
        grow[:, 1:] |= reach[:, :-1]
        grow[:, :-1] |= reach[:, 1:]
        grow &= black
        if (grow == reach).all():
            break
        reach = grow
    # se quase tudo encosta na borda, é o próprio texto grudado: não mexe
    if reach.sum() < 0.9 * black.sum():
        c[reach] = 255


def _read_score(lines: list[Line]) -> float:
    return sum(w.conf * sum(ch.isalpha() for ch in w.text) for ln in lines for w in ln.words if w.conf >= 60)


def merge_lines(base: list[Line], extra: list[Line]) -> list[Line]:
    """Junta duas leituras do mesmo frame; onde se sobrepõem, fica a mais confiável."""
    out = list(base)
    for le in extra:
        clash = [lb for lb in out if _iou(lb.box, le.box) > 0.3]
        if not clash:
            out.append(le)
        elif all(_read_score([le]) > _read_score([lb]) for lb in clash):
            out = [lb for lb in out if lb not in clash] + [le]
    return out


def _local_mean(c: np.ndarray, r: int) -> np.ndarray:
    """Média da vizinhança (2r+1)×(2r+1) de cada pixel (imagem integral)."""
    c = c.astype(np.float32)
    ii = np.pad(c, ((1, 0), (1, 0))).cumsum(0).cumsum(1)
    H, W = c.shape
    y0 = np.clip(np.arange(H) - r, 0, H)
    y1 = np.clip(np.arange(H) + r + 1, 0, H)
    x0 = np.clip(np.arange(W) - r, 0, W)
    x1 = np.clip(np.arange(W) + r + 1, 0, W)
    s = ii[y1][:, x1] - ii[y0][:, x1] - ii[y1][:, x0] + ii[y0][:, x0]
    return s / ((y1 - y0)[:, None] * (x1 - x0)[None, :])


def _resize(c: np.ndarray, f: float) -> np.ndarray:
    if abs(f - 1.0) <= 0.05:
        return c
    return np.asarray(Image.fromarray(c).resize((max(1, int(c.shape[1] * f)), max(1, int(c.shape[0] * f))),
                                                Image.LANCZOS))


def _clean_bw(b: np.ndarray) -> np.ndarray:
    # tira o fundo escuro em volta e as bordas da caixa: atrapalham o Tesseract
    _clear_border_blobs(b)
    _erase_thin_lines(b)
    return b


def _crop_variants(g: np.ndarray, x0: int, y0: int, x1: int, y1: int):
    """Versões preto-no-branco de uma caixa de texto (coordenadas em meia resolução).

    Nenhum preparo serviu para todas as tarjas reais (caixa clara sobre fundo
    escuro, texto claro em caixa colorida, letra fina…), e o recorte da caixa
    vem da grade de blocos. Então vão 4 versões para a pilha e fica a que o
    Tesseract leu melhor:
      justa (margem pequena) + limiar global (Otsu), nas duas polaridades;
      folgada (margem grande: pé e alto das letras) + limiar local, nas duas.
    """
    out = []
    # justa
    pad = 8
    xa, ya = max(0, 2 * x0 - pad), max(0, 2 * y0 - pad)
    c0 = g[ya:2 * y1 + pad, xa:2 * x1 + pad]
    if c0.size:
        f = float(np.clip(STACK_TEXT_H / max(c0.shape[0], 1), 0.35, 1.5))
        c = _resize(c0, f)
        for cc in (c, 255 - c):
            out.append((_clean_bw(np.where(cc > _otsu(cc), 255, 0).astype(np.uint8)), xa, ya, f))
    # folgada
    py = 8 + int(0.4 * 2 * (y1 - y0))
    xb, yb = max(0, 2 * x0 - 16), max(0, 2 * y0 - py)
    c0 = g[yb:2 * y1 + py, xb:2 * x1 + 16]
    if c0.size:
        f = float(np.clip(STACK_TEXT_H / max(c0.shape[0], 1), 0.6, 1.5))
        c = _resize(c0, f).astype(np.float32)
        m = _local_mean(c, max(8, c.shape[0] // 4))
        for cc, mm in ((c, m), (255 - c, 255 - m)):
            out.append((_clean_bw(np.where(cc < mm - 12, 0, 255).astype(np.uint8)), xb, yb, f))
    return out


def read_frames_stacked(items: list[tuple["Read", np.ndarray]], W: int, H: int) -> None:
    """Lê vários frames (resolução cheia) numa chamada só do Tesseract.

    Acha as linhas de texto em meia resolução, recorta cada uma do frame
    inteiro, deixa o recorte preto no branco (polaridade e limiar próprios),
    empilha tudo numa imagem e distribui as palavras de volta para o frame e a
    posição certos.
    """
    crops = []      # (read, recorte, x0, y0, fator, nº da caixa)
    n_box = 0
    for rd, g in items:
        for x0, y0, x1, y1 in find_text_boxes(half(g)):
            for c, xa, ya, f in _crop_variants(g, x0, y0, x1, y1):
                crops.append((rd, c, xa, ya, f, n_box))
            n_box += 1
    for rd, _ in items:
        rd.lines = []
    gap = 24
    k = 0
    while k < len(crops):
        batch = []
        h = gap
        while k < len(crops):
            same = [kk for kk in range(k, len(crops)) if crops[kk][5] == crops[k][5]]
            add = sum(crops[kk][1].shape[0] + gap for kk in same)
            if batch and h + add > CANVAS_MAX_H:
                break
            for kk in same:                # as versões da mesma caixa vão juntas
                batch.append(crops[kk])
            h += add
            k = same[-1] + 1
        Wc = max(c.shape[1] for _, c, _, _, _, _ in batch) + 40
        canvas = np.full((h, Wc), 255, np.uint8)
        offs = []
        y = gap
        for rd, c, xa, ya, f, nb in batch:
            canvas[y:y + c.shape[0], 20:20 + c.shape[1]] = c
            offs.append((y, y + c.shape[0]))
            y += c.shape[0] + gap
        # leitura da pilha (STACK_MODES); com mais de um modo, para cada recorte
        # fica a leitura com mais letras lidas com confiança
        per_mode = []
        for psm in STACK_MODES:
            lines: dict[tuple, Line] = {}
            for r in run_tesseract(canvas, psm=psm, invert_auto=False):
                cy = int(r[7]) + int(r[9]) / 2
                for j, (a, b) in enumerate(offs):
                    if a - gap / 2 <= cy <= b + gap / 2:
                        rd, c, xa, ya, f, nb = batch[j]
                        left = (int(r[6]) - 20) / f + xa
                        top = (int(r[7]) - a) / f + ya
                        box = (left / W, top / H, int(r[8]) / f / W, int(r[9]) / f / H)
                        key = (j, int(r[2]), int(r[3]), int(r[4]))
                        lines.setdefault(key, Line()).words.append(Word(r[11].strip(), float(r[10]), box))
                        break
            by_crop: dict[int, list[Line]] = {}
            for key, ln in lines.items():
                by_crop.setdefault(key[0], []).append(ln)
            per_mode.append(by_crop)
        # por caixa: a melhor leitura entre as versões do recorte (e os modos)
        options: dict[int, list] = {}
        for j, item in enumerate(batch):
            for m in per_mode:
                options.setdefault(item[5], [item[0], []])[1].append(m.get(j, []))
        for rd, opts in options.values():
            rd.lines.extend(max(opts, key=_read_score))
    for rd, _ in items:
        _mark_cut_words(rd.lines, W)
        rd.lines = [ln for ln in rd.lines if _useful(ln)]


def _mark_cut_words(lines: list[Line], W: int) -> None:
    """Palavra encostada na borda da tela está cortada: não entra na ortografia."""
    edge = 4.0 / W
    for ln in lines:
        for w in ln.words:
            if w.box[0] <= edge or w.box[0] + w.box[2] >= 1.0 - edge:
                w.cut = True


ONE_LETTER_WORDS = set("aeoéàAEOÉÀ")


def _trim(ln: Line) -> None:
    """Tira das pontas da linha os restos de borda ("Ç Felipe Arantes ," → "Felipe Arantes")."""
    def junk(w: Word) -> bool:
        t = w.text
        return len(t) == 1 and (not t.isalnum() or (t not in ONE_LETTER_WORDS and not t.isdigit()))
    while ln.words and junk(ln.words[0]):
        ln.words.pop(0)
    while ln.words and junk(ln.words[-1]):
        ln.words.pop()


def _useful(ln: Line) -> bool:
    """Descarta linhas que são só ruído (riscos, pedaços do cenário)."""
    _trim(ln)
    if not ln.words:
        return False
    letters = sum(ch.isalpha() for ch in ln.text)
    if letters < 2:
        return False
    return ln.conf >= MIN_LINE_CONF


# ---------------------------------------------------------------- o que ler

@dataclass
class Read:
    frame: int
    source: str                  # text_in | text_in_end | text_out | change | cut | tag_scan
    region: tuple | None         # None = tela inteira
    event_frame: int | None = None
    lines: list[Line] = field(default_factory=list)

    def to_dict(self):
        return {"frame": self.frame, "source": self.source,
                "region": [round(v, 4) for v in self.region] if self.region else None,
                "event_frame": self.event_frame, "lines": [ln.to_dict() for ln in self.lines]}


def plan_reads(events, content: tuple[int, int]) -> list[Read]:
    """Escolhe os frames a ler a partir dos eventos da etapa 1."""
    c_first, c_end = content
    reads: list[Read] = []

    def clamp(f: int) -> int:
        return int(min(max(f, c_first), c_end - 1))

    cuts = sorted(e.frame for e in events if e.kind == "cut" and e.frame is not None)
    for ev in events:
        if ev.frame is None:
            continue
        if ev.kind == "text_in" and ev.region:
            f = (ev.show_frame or ev.frame) + TEXT_READ_DELAY
            until = ev.extra.get("until_frame")
            if until is not None:
                f = min(f, until - SETTLE)
            nxt = [c for c in cuts if c > ev.frame]
            if nxt:
                f = min(f, nxt[0] - 2)
            f = max(f, (ev.show_frame or ev.frame) + 2)
            reads.append(Read(clamp(f), "text_in", tuple(ev.region), ev.frame))
            # segunda leitura no fim (texto que vai aparecendo palavra por palavra
            # só fica inteiro depois): a ortografia compara as duas
            last = min([x for x in (until - SETTLE if until is not None else f + 90,
                                    (nxt[0] - 2) if nxt else None) if x is not None])
            if last - f >= 30:
                reads.append(Read(clamp(last), "text_in_end", tuple(ev.region), ev.frame))
        elif ev.kind == "text_out" and ev.region and ev.extra.get("pair_of_frame") is None:
            reads.append(Read(clamp(ev.frame - SETTLE), "text_out", tuple(ev.region), ev.frame))
        elif ev.kind == "change":
            reads.append(Read(clamp((ev.show_frame or ev.frame) + TEXT_READ_DELAY // 2), "change", None, ev.frame))
        elif ev.kind == "cut":
            nxt = [c for c in cuts if c > ev.frame]
            f = ev.frame + AFTER_CUT
            if nxt:
                f = min(f, (ev.frame + nxt[0]) // 2)
            reads.append(Read(clamp(f), "cut", None, ev.frame))
    reads.sort(key=lambda r: (r.frame, r.region is not None))
    return reads


def reread_word(gray: np.ndarray, box: tuple[float, float, float, float], W: int, H: int) -> str:
    """Relê uma palavra ampliada (segunda opinião antes de avisar erro de ortografia)."""
    x, y, w, h = box
    px, py, pw, ph = x * W, y * H, w * W, h * H
    x0 = max(0, int(px - 0.6 * ph))
    x1 = min(W, int(np.ceil(px + pw + 0.6 * ph)))
    y0 = max(0, int(py - 0.45 * ph))
    y1 = min(H, int(np.ceil(py + ph + 0.45 * ph)))
    crop = gray[y0:y1, x0:x1]
    if crop.size == 0:
        return ""
    if text_is_light(crop):
        crop = 255 - crop
    scale = float(np.clip(90.0 / max(ph, 1.0), 1.5, 4.0))
    big = np.asarray(Image.fromarray(crop).resize((max(1, int(crop.shape[1] * scale)),
                                                   max(1, int(crop.shape[0] * scale))), Image.LANCZOS))
    rows = run_tesseract(big, psm=7, invert_auto=False)
    return " ".join(c[11].strip() for c in rows if float(c[10]) >= 30)


def _workers() -> int:
    if os.environ.get("REVISOR_OCR_WORKERS"):
        return max(1, int(os.environ["REVISOR_OCR_WORKERS"]))
    return max(1, min(4, (os.cpu_count() or 2)))


def scan_frames(rate: Rate, content: tuple[int, int], window_s: float, fps: float = TAG_SCAN_FPS) -> list[int]:
    """Frames da varredura da tarja: começo do conteúdo, 3 por segundo, até `window_s`."""
    c_first, c_end = content
    t0 = rate.seconds_of(c_first)
    out = []
    k = 0
    while True:
        f = rate.frame_at(t0 + k / fps)
        if f >= c_end or k / fps > window_s:
            break
        out.append(max(f, c_first))
        k += 1
    return out


def read_video(path: str, rate: Rate, events, content: tuple[int, int],
               width: int, height: int, progress=None, on_frame=None,
               tag_window_s: float = 45.0) -> list[Read]:
    """Lê o texto dos frames escolhidos. Erros num frame não derrubam o resto.

    Duas partes:
    1. frames que a etapa 1 marcou (texto, slide, depois de cada corte);
    2. varredura do começo do conteúdo (3 frames/s até `tag_window_s`) para a
       tarja de nome, que costuma entrar animada e ficar poucos segundos — a
       etapa 1 não a vê como "texto que entrou e ficou parado".
    Vários Tesseracts rodam ao mesmo tempo (até 4).

    `on_frame(read, gray)` é chamado com o frame ainda na memória (a ortografia
    usa para reler ampliadas as palavras suspeitas sem decodificar de novo).
    """
    from concurrent.futures import ThreadPoolExecutor

    reads = plan_reads(events, content)
    scan = [Read(f, "tag_scan", None) for f in scan_frames(rate, content, tag_window_s)] if tag_window_s > 0 else []
    scan_index = {id(rd): k for k, rd in enumerate(scan)}
    by_frame: dict[int, list[Read]] = {}
    for rd in reads:
        by_frame.setdefault(rd.frame, []).append(rd)
    total = len(by_frame) + len(scan)
    done = [0]

    def tick():
        done[0] += 1
        if progress:
            progress(min(done[0] / max(total, 1), 1.0))

    def process(group: list[Read], gray: np.ndarray | None):
        try:
            if gray is None:
                gray = media.read_frame_full(path, rate, group[0].frame, width, height).y
            for rd in group:
                rd.lines = read_image(gray, rd.region, width, height)
                if on_frame and rd.lines:
                    on_frame(rd, gray)
        except (media.MediaError, OCRError, OSError):
            for rd in group:
                rd.lines = []
        tick()

    def process_scan(batch: list[tuple[Read, np.ndarray]]):
        try:
            read_frames_stacked(batch, width, height)
            # rede de segurança: 1 frame por segundo também é lido inteiro
            for rd, g in batch:
                if scan_index.get(id(rd), 1) % TAG_SCAN_FPS == 0:
                    full = _lines_from_rows(run_tesseract(g, psm=11, invert_auto=True), 0, 0, 1.0, width, height)
                    _mark_cut_words(full, width)
                    rd.lines = merge_lines(rd.lines, [ln for ln in full if _useful(ln)])
            if on_frame:
                for rd, small in batch:
                    if rd.lines:
                        on_frame(rd, small)
        except (OCRError, OSError):
            for rd, _ in batch:
                rd.lines = []
        for _ in batch:
            tick()

    with ThreadPoolExecutor(max_workers=_workers()) as pool:
        # 2) varredura: um FFmpeg só entrega os frames em sequência; frame igual
        #    ao anterior não é relido; os frames vão em lotes de 3 s para o Tesseract
        if scan:
            pending = []
            same_as: dict[int, Read] = {}
            t0 = rate.seconds_of(scan[0].frame) - 0.25 / float(rate.fps)
            dur = rate.seconds_of(scan[-1].frame) - rate.seconds_of(scan[0].frame) + 1.0 / TAG_SCAN_FPS
            last_small, last_rd = None, None
            batch: list[tuple[Read, np.ndarray]] = []
            try:
                for rd, fr in zip(scan, media.iter_yuv(path, width, height, fps=_fps_str(TAG_SCAN_FPS),
                                                       start=t0, duration=dur)):
                    small = fr.y.copy()
                    tiny = small[::12, ::12].astype(np.int16)
                    if last_small is not None and np.abs(tiny - last_small).mean() < STATIC_DIFF:
                        same_as[id(rd)] = last_rd
                        tick()
                        continue
                    last_small, last_rd = tiny, rd
                    batch.append((rd, small))
                    if len(batch) >= SCAN_BATCH:
                        pending.append(pool.submit(process_scan, batch))
                        batch = []
                    if len(pending) > 2 * _workers():      # não acumula frames na memória
                        pending.pop(0).result()
            except media.MediaError:
                pass
            if batch:
                pending.append(pool.submit(process_scan, batch))
            for fu in pending:
                fu.result()
            for rd in scan:
                src = same_as.get(id(rd))
                if src is not None:
                    rd.lines = src.lines
        # 1) frames marcados pela etapa 1
        list(pool.map(lambda g: process(g, None), by_frame.values()))
    # a varredura só guarda os frames em que leu alguma coisa
    out = reads + [rd for rd in scan if rd.lines]
    out.sort(key=lambda r: (r.frame, r.region is not None))
    return out


def _fps_str(fps: float) -> str:
    return str(int(fps)) if float(fps).is_integer() else f"{fps:.3f}"
