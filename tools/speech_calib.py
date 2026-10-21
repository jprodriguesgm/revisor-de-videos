"""Calibragem da etapa 2b (fala) com aulas reais.

  python tools/speech_calib.py fala <cache> [--budget 150] [trecho do nome ...]
      Transcreve (em pedaços guardados no cache) as aulas já analisadas e mostra os
      avisos da fala e os cortes no meio da fala. Com --budget, para depois de N
      segundos; rodar de novo continua de onde parou.

  python tools/speech_calib.py montar <video> <pasta de saída> [--semente 1]
      Monta, a partir do áudio de uma aula aprovada, um áudio COM ERROS e o gabarito:
      emendas no meio da fala (pedaço removido sem transição) e takes repetidos
      (começo de frase dito, abandonado e dito de novo). Só áudio (m4a), fica no Mac.

  python tools/speech_calib.py medir <pasta de saída> [--budget 150]
      Roda áudio + fala no áudio montado e compara com o gabarito.

  python tools/speech_calib.py bruto <bruto> <editado> <cache> [--budget 150]
      Transcreve o bruto e o editado e mostra o que o editor cortou (trechos do bruto
      que não estão no editado) ao lado dos avisos que o app deu no bruto.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from difflib import SequenceMatcher
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from revisor import analyze, audio, media, speech  # noqa: E402

SR = 48000


def _arg(argv, name, default=None, cast=str):
    if name in argv:
        return cast(argv[argv.index(name) + 1])
    return default


def _fmt(t):
    return f"{int(t // 60):02d}:{t % 60:05.2f}"


# ------------------------------------------------------------------ fala no cache

def cmd_fala(argv):
    cache = Path(argv[0])
    budget = _arg(argv, "--budget", None, float)
    skip = {argv[argv.index("--budget") + 1]} if "--budget" in argv else set()
    which = [x for x in argv[1:] if not x.startswith("--") and x not in skip]
    st = analyze.Settings()
    t_start = time.time()
    for p in sorted(cache.glob("*/analysis.json")):
        a = json.loads(p.read_text(encoding="utf-8"))
        if which and not any(speech.norm(w) in speech.norm(a["file"]) for w in which):
            continue
        left = None if budget is None else budget - (time.time() - t_start)
        if left is not None and left < 20:
            print("(tempo do comando acabou; rode de novo para continuar)")
            break
        sp = a.get("speech") or {}
        if a.get("speech_version") != analyze.SPEECH_VERSION or sp.get("status") != "ok":
            analyze.update_audio_speech(a, Path(a["path"]), p.parent, st, budget_s=left)
            analyze.refresh_speech_checks(a, st)
            p.write_text(json.dumps(a, ensure_ascii=False), encoding="utf-8")
        sp = a.get("speech") or {}
        mins = a["duration"] / 60
        print(f"== {a['file']}  ({mins:.1f} min)  fala: {sp.get('status')} "
              f"{sp.get('chunks_done')}/{sp.get('chunks')} pedaços, {len(sp.get('words', []))} palavras, "
              f"{sp.get('seconds')} s de Whisper", flush=True)
        if sp.get("status") == "erro":
            print("   ERRO:", sp.get("error"))
        if sp.get("status") != "ok":
            continue
        for e in a["events"]:
            if e["kind"] in analyze.SPEECH_KINDS:
                print(f"   {e['tc']}  {e['note']}\n            «{e['extra'].get('context', '')}»")
        for e in (a.get("audio") or {}).get("events", []):
            if e["kind"] == "speech_cut":
                print(f"   {_fmt(e['start'])}  áudio: {e['note']}  ({e['value']} dB)")


# ------------------------------------------------------------------ fala sem a análise de imagem

def cmd_rapido(argv):
    """rapido <cache> <vinheta entrada> <vinheta saída> <vídeo> [<vídeo> ...] [--budget N]

    Só o necessário para a fala: vinhetas (onde começa e acaba o conteúdo), áudio e
    transcrição. Guarda <cache>/<id>/fala.json. Rodar de novo continua de onde parou.
    """
    from revisor import vinheta
    budget = _arg(argv, "--budget", None, float)
    args = [a for k, a in enumerate(argv) if not a.startswith("--") and (k == 0 or argv[k - 1] != "--budget")]
    cache, vin_in, vin_out, vids = Path(args[0]), args[1], args[2], args[3:]
    t0 = time.time()
    sigs = None
    for v in vids:
        info = media.probe(v)
        vid = analyze.video_id(Path(v).name, info.duration)
        d = cache / vid
        d.mkdir(parents=True, exist_ok=True)
        fj = d / "fala.json"
        st = json.loads(fj.read_text(encoding="utf-8")) if fj.exists() else {"file": Path(v).name}
        st["path"] = str(v)
        if "content" not in st:
            if sigs is None:
                sigs = (vinheta.signature(vin_in), vinheta.signature(vin_out))
            r = vinheta.find(v, info.rate, info.frames, *sigs)
            c0 = info.rate.seconds_of(r.content_first_frame or 0)
            c1 = info.rate.seconds_of(r.end_first_frame if r.end_first_frame is not None else info.frames)
            st["content"] = [c0, c1]
            st["vinheta_ok"] = [r.content_first_frame is not None, r.end_first_frame is not None]
        if "audio" not in st:
            st["audio"] = audio.analyze(v, content=tuple(st["content"])).to_dict() if info.has_audio else None
            fj.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
        sp = st.get("speech") or {}
        if sp.get("status") != "ok":
            left = None if budget is None else budget - (time.time() - t0)
            if left is not None and left < 25:
                print(f"{st['file']}: (tempo do comando acabou; rode de novo)")
                break
            au = st["audio"]
            sp = speech.transcribe(v, tuple(st["content"]), d, au["envelope_db"], au["envelope_step"], budget_s=left)
            st["speech"] = sp
            fj.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
        _show(st)
        if sp.get("status") != "ok":
            break


def _show(st, phrases=None):
    sp = st.get("speech") or {}
    au = st.get("audio") or {}
    c0, c1 = st["content"]
    print(f"== {st['file']}  conteúdo {_fmt(c0)}–{_fmt(c1)}  fala: {sp.get('status')} "
          f"{sp.get('chunks_done')}/{sp.get('chunks')} pedaços, {len(sp.get('words', []))} palavras, "
          f"Whisper {sp.get('seconds')} s", flush=True)
    if sp.get("status") != "ok":
        return
    act = speech.activity_from_envelope(au.get("envelope_db") or [], au.get("envelope_step", 0.1))
    for f in speech.checks(sp, phrases, act):
        print(f"   {_fmt(f['start'])}  {speech.note_for(f)}\n            «{f.get('context', '')}»")
    cuts = [e for e in au.get("events", []) if e["kind"] == "speech_cut"]
    if SHOW_CUTS:
        for e in cuts:
            print(f"   {_fmt(e['start'])}  áudio: {e['note']}  ({e['value']} dB)")
    elif cuts:
        print(f"   ({len(cuts)} avisos de corte no meio da fala)")


SHOW_CUTS = "--cortes" in sys.argv


def cmd_mostrar(argv):
    """mostrar <cache> [trecho do nome] — refaz e mostra os avisos (sem transcrever)."""
    filt = [a for a in argv[1:] if not a.startswith("--")]
    for fj in sorted(Path(argv[0]).glob("*/fala.json")):
        st = json.loads(fj.read_text(encoding="utf-8"))
        if filt and not any(speech.norm(f) in speech.norm(st["file"]) for f in filt):
            continue
        if "--audio" in argv:      # refaz o áudio (regras novas do corte no meio da fala)
            st["audio"] = audio.analyze(st["path"], content=tuple(st["content"])).to_dict()
            fj.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
        _show(st)


# ------------------------------------------------------------------ montar erros

def _decode(path, start=None, end=None):
    cmd = [media.ffmpeg(), "-hide_banner", "-nostdin", "-loglevel", "error"]
    if start is not None:
        cmd += ["-ss", f"{start:.3f}"]
    cmd += ["-i", str(path)]
    if end is not None:
        cmd += ["-t", f"{end - (start or 0):.3f}"]
    cmd += ["-map", "0:a:0", "-ac", "1", "-ar", str(SR), "-f", "f32le", "pipe:1"]
    r = subprocess.run(cmd, capture_output=True, check=True)
    return np.frombuffer(r.stdout, np.float32).copy()


def _rms_db(x, win):
    n = x.size // win
    w = x[:n * win].reshape(n, win).astype(np.float64)
    return 10 * np.log10(np.maximum((w ** 2).mean(axis=1), 1e-12))


def cmd_montar(argv):
    video, out = Path(argv[0]), Path(argv[1])
    seed = _arg(argv, "--semente", 1, int)
    max_s = _arg(argv, "--max", 420.0, float)       # usa até 7 min do conteúdo
    rng = np.random.default_rng(seed)
    out.mkdir(parents=True, exist_ok=True)
    cache = [json.loads(p.read_text(encoding="utf-8")) for p in Path(_arg(argv, "--cache", "cache")).glob("*/analysis.json")] \
        if "--cache" in argv else []
    a = next((c for c in cache if c["file"] == video.name), None)
    if a:
        rate = analyze._rate_of(a)
        c0, c1 = rate.seconds_of(a["content"]["first_frame"]), rate.seconds_of(a["content"]["end_frame"])
    else:
        info = media.probe(video)
        c0, c1 = 7.0, info.duration - 5.0
    c1 = min(c1, c0 + max_s)
    x = _decode(video, c0, c1)
    w10 = SR // 100
    lv = _rms_db(x, w10)                     # 10 ms
    sil = lv < -80                           # silêncio digital (gate)

    # frases: trechos entre silêncios de ≥ 150 ms
    runs, k, n = [], 0, lv.size
    while k < n:
        if sil[k]:
            j = k
            while j < n and sil[j]:
                j += 1
            if j - k >= 15:
                runs.append((k, j))
            k = j
        else:
            k += 1
    phrases = [(runs[i][1], runs[i + 1][0]) for i in range(len(runs) - 1)
               if 200 <= runs[i + 1][0] - runs[i][1] <= 700]          # frases de 2 a 7 s

    edits = []          # (posição em 10 ms no original, tipo, dados)
    # 1) takes repetidos: 3 frases longe umas das outras
    used = []
    for (a0, a1) in rng.permutation(phrases).tolist():
        if len([e for e in edits if e[1] == "repeat"]) >= 3:
            break
        if any(abs(a0 - u) < 3000 for u in used):
            continue
        frac = rng.uniform(0.45, 0.75)
        edits.append((a0, "repeat", {"a0": a0, "cut": int(a0 + (a1 - a0) * frac)}))
        used.append(a0)
    # 2) emendas no meio da fala: 12 pontos com fala dos dois lados
    loud = np.flatnonzero((lv > -30) & (np.roll(lv, 3) > -30) & (np.roll(lv, -3) > -30))
    tries = 0
    while len([e for e in edits if e[1] == "cut"]) < 12 and tries < 5000:
        tries += 1
        p = int(rng.choice(loud))
        remove = int(rng.uniform(15, 150))
        if p + remove + 5 >= n or lv[p + remove] <= -30 or lv[p + remove + 3] <= -30:
            continue
        if any(abs(p - e[0]) < 1500 for e in edits):
            continue
        off = int(rng.integers(0, w10))         # posição dentro dos 10 ms (amostra qualquer)
        edits.append((p, "cut", {"p": p, "remove": remove, "off": off}))
    edits.sort(key=lambda e: e[0])

    pieces, gab = [], []
    pos = 0                                   # em amostras do original
    out_len = 0
    for p, kind, d in edits:
        if kind == "repeat":
            s0 = d["a0"] * w10
            if s0 < pos:
                continue
            pieces.append(x[pos:s0]); out_len += s0 - pos
            first = x[s0:d["cut"] * w10]
            gap = np.zeros(int(SR * rng.uniform(0.3, 0.8)), np.float32)
            t_first = out_len / SR
            pieces += [first, gap]; out_len += first.size + gap.size
            gab.append({"kind": "repeat", "t": round(t_first, 2), "restart": round(out_len / SR, 2)})
            pos = s0
        else:
            s0 = d["p"] * w10 + d["off"]
            s1 = s0 + d["remove"] * w10
            if s0 < pos:
                continue
            pieces.append(x[pos:s0]); out_len += s0 - pos
            gab.append({"kind": "cut", "t": round(out_len / SR, 3), "removed_ms": d["remove"] * 10})
            pos = s1
    pieces.append(x[pos:])
    y = np.concatenate(pieces)
    raw = out / "montado.f32"
    raw.write_bytes(y.astype(np.float32).tobytes())
    m4a = out / "montado.m4a"
    subprocess.run([media.ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-f", "f32le", "-ar", str(SR),
                    "-ac", "1", "-i", str(raw), "-c:a", "aac", "-b:a", "96k", str(m4a)], check=True)
    raw.unlink()
    # o mesmo trecho sem erros, para contar alarmes falsos no mesmo áudio
    raw = out / "limpo.f32"
    raw.write_bytes(x.astype(np.float32).tobytes())
    subprocess.run([media.ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-f", "f32le", "-ar", str(SR),
                    "-ac", "1", "-i", str(raw), "-c:a", "aac", "-b:a", "96k", str(out / "limpo.m4a")], check=True)
    raw.unlink()
    (out / "gabarito.json").write_text(json.dumps({"video": video.name, "content_start": c0, "events": gab},
                                                  ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"montado: {len(y) / SR:.1f} s, {sum(g['kind'] == 'cut' for g in gab)} emendas, "
          f"{sum(g['kind'] == 'repeat' for g in gab)} takes repetidos → {out}")


def cmd_medir(argv):
    out = Path(argv[0])
    budget = _arg(argv, "--budget", None, float)
    gab = json.loads((out / "gabarito.json").read_text(encoding="utf-8"))
    t0 = time.time()
    res = {}
    for name in ("montado", "limpo"):
        f = out / f"{name}.m4a"
        rf = out / f"{name}.audio.json"
        if rf.exists():
            au = json.loads(rf.read_text())
        else:
            au = audio.analyze(str(f)).to_dict()
            rf.write_text(json.dumps(au))
        left = None if budget is None else budget - (time.time() - t0)
        sp = speech.transcribe(str(f), (0.0, au["duration"]), out / f"{name}_cache", au["envelope_db"],
                               au["envelope_step"], budget_s=left)
        res[name] = (au, sp)
        if sp["status"] != "ok":
            print(f"{name}: fala {sp['chunks_done']}/{sp['chunks']} pedaços — rode de novo para continuar")
            return
    for name, (au, sp) in res.items():
        act = speech.activity_from_envelope(au["envelope_db"], au["envelope_step"])
        found = speech.checks(sp, None, act)
        cuts = [e for e in au["events"] if e["kind"] == "speech_cut"]
        print(f"\n== {name}: {len(sp['words'])} palavras, Whisper {sp['seconds']} s; "
              f"{len(cuts)} cortes no meio da fala, {len(found)} avisos de fala")
        if name == "limpo":
            for e in cuts:
                print(f"   FALSO corte  {_fmt(e['start'])}  ({e['value']} dB)")
            for f in found:
                print(f"   FALSO fala   {_fmt(f['start'])}  {speech.note_for(f)}")
            continue
        used_c, used_f = set(), set()
        for g in gab["events"]:
            if g["kind"] == "cut":
                hit = [k for k, e in enumerate(cuts) if k not in used_c and abs(e["start"] - g["t"]) <= 0.03]
                if hit:
                    used_c.add(hit[0])
                    print(f"   OK     emenda {_fmt(g['t'])} (tirou {g['removed_ms']} ms)  {cuts[hit[0]]['value']} dB")
                else:
                    print(f"   FALTOU emenda {_fmt(g['t'])} (tirou {g['removed_ms']} ms)")
            else:
                hit = [k for k, f in enumerate(found) if k not in used_f and f["kind"] == "speech_repeat"
                       and abs(f.get("restart", f["start"]) - g["restart"]) <= 2.0]
                if hit:
                    used_f.add(hit[0])
                    print(f"   OK     take repetido {_fmt(g['restart'])}  {speech.note_for(found[hit[0]])}")
                else:
                    near = " ".join(w[2] for w in sp["words"] if g["t"] - 1 <= w[0] <= g["restart"] + 4)
                    print(f"   FALTOU take repetido {_fmt(g['restart'])}  transcrito: «{near}»")
        for k, e in enumerate(cuts):
            if k not in used_c:
                print(f"   FALSO? corte {_fmt(e['start'])}  ({e['value']} dB)")
        for k, f in enumerate(found):
            if k not in used_f:
                print(f"   FALSO? fala  {_fmt(f['start'])}  {speech.note_for(f)}")


# ------------------------------------------------------------------ bruto × editado

def cmd_bruto(argv):
    raw_v, edit_v, cache = Path(argv[0]), Path(argv[1]), Path(argv[2])
    budget = _arg(argv, "--budget", None, float)
    t0 = time.time()
    got = {}
    for v in (raw_v, edit_v):
        d = cache / ("bruto_" + speech.norm(v.stem)[:40])
        d.mkdir(parents=True, exist_ok=True)
        rf = d / "audio.json"
        if rf.exists():
            au = json.loads(rf.read_text())
        else:
            au = audio.analyze(str(v)).to_dict()
            rf.write_text(json.dumps(au))
        left = None if budget is None else budget - (time.time() - t0)
        sp = speech.transcribe(str(v), (0.0, au["duration"]), d, au["envelope_db"], au["envelope_step"], budget_s=left)
        if sp["status"] != "ok":
            print(f"{v.name}: {sp['chunks_done']}/{sp['chunks']} pedaços — rode de novo para continuar")
            return
        got[v] = (au, sp)
    au, sp = got[raw_v]
    _, sp_e = got[edit_v]
    rw = [speech.norm(w[2]) for w in sp["words"]]
    ew = [speech.norm(w[2]) for w in sp_e["words"]]
    sm = SequenceMatcher(None, rw, ew, autojunk=False)
    removed = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ("delete", "replace") and i2 - i1 >= 3:
            removed.append((sp["words"][i1][0], sp["words"][i2 - 1][1], " ".join(w[2] for w in sp["words"][i1:i2])))
    act = speech.activity_from_envelope(au["envelope_db"], au["envelope_step"])
    found = speech.checks(sp, None, act)
    print(f"bruto: {len(rw)} palavras; editado: {len(ew)} palavras; {len(removed)} trechos cortados pelo editor")
    for a0, a1, txt in removed:
        hit = [f for f in found if a0 - 3 <= f["start"] <= a1 + 3]
        mark = "AVISADO " if hit else "sem aviso"
        print(f"   {_fmt(a0)}–{_fmt(a1)} {mark} «{txt[:160]}»")
        for f in hit:
            print(f"        → {speech.note_for(f)}")
    print("avisos fora dos cortes:")
    for f in found:
        if not any(a0 - 3 <= f["start"] <= a1 + 3 for a0, a1, _ in removed):
            print(f"   {_fmt(f['start'])} {speech.note_for(f)}  «{f.get('context', '')[:120]}»")


if __name__ == "__main__":
    cmd = sys.argv[1]
    {"fala": cmd_fala, "rapido": cmd_rapido, "mostrar": cmd_mostrar, "montar": cmd_montar, "medir": cmd_medir, "bruto": cmd_bruto}[cmd](sys.argv[2:])
