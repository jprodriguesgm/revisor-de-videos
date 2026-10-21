"""Teste no navegador (Playwright) dos pedidos do JP de 21/10/2026:
fila de pastas, ↑ ↓ entre cortes, "Próxima aula"/"Próxima pasta", trecho com duração escolhida,
medidor de áudio e barra de abas centralizada.

Uso (com o app já aberto: python3 -m revisor abrir --sem-navegador):
    python3 tools/ui_novidades.py <aula A> <aula B> <vinheta_inicio> <vinheta_final> <pasta de trabalho> [--porta 8765]

Monta na pasta de trabalho: "Ana 21:10" (aulas A e B), "Bruno 21:10" (aula B com outro nome) e
"Carla 21:10" (12 vídeos curtos, para a barra de abas). Capturas em <pasta de trabalho>/capturas.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from revisor import media  # noqa: E402

SEP = ":" if os.name != "nt" else "-"


def api(base, path, body=None):
    req = urllib.request.Request(base + "api/" + path, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"} if body is not None else {})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("aula_a")
    ap.add_argument("aula_b")
    ap.add_argument("vin_in")
    ap.add_argument("vin_out")
    ap.add_argument("work")
    ap.add_argument("--porta", type=int, default=8765)
    a = ap.parse_args()
    work = Path(a.work)
    shots = work / "capturas"
    shots.mkdir(parents=True, exist_ok=True)
    ana, bruno, carla = (work / f"{n} 21{SEP}10" for n in ("Ana", "Bruno", "Carla"))
    for p in (ana, bruno, carla):
        p.mkdir(exist_ok=True)
    if not any(ana.glob("*.mp4")):
        shutil.copy(a.aula_a, ana / "01 Aula com erros.mp4")
        shutil.copy(a.aula_b, ana / "02 Aula limpa.mp4")
    if not any(bruno.glob("*.mp4")):
        shutil.copy(a.aula_b, bruno / "01 Outra aula.mp4")
    if not any(carla.glob("*.mp4")):
        for k in range(12):
            subprocess.run([media.ffmpeg(), "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                            f"testsrc2=size=320x180:rate=30000/1001:duration=5", "-f", "lavfi", "-i",
                            f"sine=frequency={300 + 40 * k}:sample_rate=48000:duration=5", "-c:v", "libx264",
                            "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
                            str(carla / f"{k + 1:02d} Bloco de conteúdo número {k + 1}.mp4")], check=True)

    base = f"http://127.0.0.1:{a.porta}/"
    api(base, "settings", {"vinheta_in": a.vin_in, "vinheta_out": a.vin_out})
    errors, report = [], []
    with sync_playwright() as p:
        b = p.chromium.launch(args=["--autoplay-policy=no-user-gesture-required"])
        ctx = b.new_context(viewport={"width": 1440, "height": 900})
        pg = ctx.new_page()
        pg.on("console", lambda m: errors.append(f"console {m.type}: {m.text}") if m.type in ("error", "warning") else None)
        pg.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))

        def start_in_ui(folder: Path, prof: str):
            pg.goto(base + "#/inicio")
            pg.wait_for_selector("text=Nova revisão")
            pg.fill("#pasta", str(folder))
            pg.press("#pasta", "Enter")
            pg.wait_for_selector("text=vídeo")
            pg.wait_for_timeout(600)
            pg.fill("#prof", prof)
            if not pg.locator("#entrega").get_attribute("readonly"):
                pg.fill("#entrega", "21/10/2026")
            pg.uncheck("text=Ouvir as falas")
            label = pg.text_content(".start .btn.primary")
            pg.click(".start .btn.primary")
            return label

        # 1) Ana pela tela: começa na hora
        lab = start_in_ui(ana, "Ana")
        pg.wait_for_selector("text=Analisando os vídeos")
        report.append(f"botão com nada rodando: {lab!r}")
        # 2) Bruno e Carla: entram na fila
        lab = start_in_ui(bruno, "Bruno")
        pg.wait_for_selector(".q-card")
        report.append(f"botão com a Ana rodando: {lab!r}")
        pg.wait_for_timeout(500)
        pg.screenshot(path=shots / "01_inicio_fila.png", full_page=True)
        start_in_ui(carla, "Carla")
        pg.wait_for_timeout(800)
        report.append("fila (início): " + " | ".join(pg.locator(".q-row").all_inner_texts()).replace("\n", " · "))
        report.append("aviso no topo: " + (pg.text_content("#queue-chip") or "").strip())
        pg.goto(base + "#/analise")
        pg.wait_for_selector(".q-card")
        pg.wait_for_timeout(1000)
        pg.screenshot(path=shots / "02_analise_com_fila.png")

        # 3) revisão da Ana: ↑ ↓, N, trecho com duração e medidor
        for _ in range(600):
            if api(base, "video?n=1").get("ready"):
                break
            time.sleep(1)
        pg.goto(base + "#/revisao/1")
        pg.wait_for_selector(".vw-img")
        pg.wait_for_timeout(1200)
        pg.keyboard.press("ArrowDown")
        pg.wait_for_timeout(700)
        hud1 = pg.text_content(".vw-hud.tl")
        pg.keyboard.press("ArrowDown")
        pg.wait_for_timeout(700)
        hud2 = pg.text_content(".vw-hud.tl")
        pg.keyboard.press("ArrowUp")
        pg.wait_for_timeout(700)
        hud3 = pg.text_content(".vw-hud.tl")
        report.append(f"↓: {hud1} | ↓: {hud2} | ↑: {hud3}")
        pg.screenshot(path=shots / "03_corte.png")
        pg.keyboard.press("v")
        pg.wait_for_selector(".vw-clip .vu")
        pg.wait_for_timeout(4000)
        report.append("medidor (pico): " + (pg.text_content(".vu-n") or "") +
                      " | trecho: " + pg.evaluate("document.querySelector('.vw-clip video').src.split('/api/')[1]"))
        pg.screenshot(path=shots / "04_trecho_medidor.png")
        pg.select_option(".clip-len", "2")
        pg.wait_for_timeout(2500)
        report.append("trecho com 2 s: " + pg.text_content(".vw-clip .cc .mono") +
                      " | guardado: " + str(api(base, "video?n=1")["clip_half_s"]))
        pg.screenshot(path=shots / "05_trecho_2s.png")
        pg.keyboard.press("Escape")
        report.append("botão lateral: " + pg.text_content(".rv-side .btn:has-text('Ver momento')"))
        report.append("próxima (vídeo 1): " + (pg.get_attribute(".rv-next", "title") or ""))
        pg.keyboard.press("n")
        pg.wait_for_function("location.hash === '#/revisao/2'")
        pg.wait_for_selector(".rv-next")
        pg.wait_for_timeout(1500)
        report.append("próxima (última aula da Ana): " + pg.text_content(".rv-next") + " · " + (pg.get_attribute(".rv-next", "title") or ""))
        pg.screenshot(path=shots / "06_ultima_aula.png")

        # 4) próxima pasta (Bruno): espera ficar pronto, clica
        for _ in range(900):
            q = api(base, "queue")
            if all(e["status"] == "done" for e in q["entries"]):
                break
            time.sleep(1)
        pg.goto(base + "#/revisao/2")
        pg.wait_for_selector(".rv-next")
        pg.wait_for_timeout(800)
        pg.click(".rv-next")
        pg.wait_for_function("document.querySelector('.rv-tab.on') && document.querySelector('.rv-tab.on').textContent.includes('Outra aula')", timeout=30000)
        report.append("depois de Próxima pasta: " + api(base, "review")["review"]["project"] + " · " + pg.text_content(".rv-tab.on"))
        pg.screenshot(path=shots / "07_proxima_pasta.png")

        # 5) Carla: 12 abas → a aba aberta fica no meio
        pg.click(".rv-next")                     # Bruno tem 1 aula → próxima pasta = Carla
        pg.wait_for_function("document.querySelectorAll('.rv-tab').length === 12", timeout=30000)
        pg.set_viewport_size({"width": 1100, "height": 760})
        for n in (9, 10, 3):
            pg.goto(base + f"#/revisao/{n}")
            pg.wait_for_selector(".rv-tab.on")
            pg.wait_for_timeout(1500)
            pos = pg.evaluate("""(() => { const t = document.querySelector('.rv-tabs'), o = t.querySelector('.rv-tab.on');
                const tr = t.getBoundingClientRect(), r = o.getBoundingClientRect();
                return {scroll: Math.round(t.scrollLeft), centro: Math.round((r.left + r.width / 2) - (tr.left + tr.width / 2)),
                        visivel: r.left >= tr.left - 1 && r.right <= tr.right + 1}; })()""")
            report.append(f"abas · vídeo {n}: {pos}")
        pg.screenshot(path=shots / "08_abas_centralizadas.png")
        pg.goto(base + "#/analise")
        pg.wait_for_selector(".q-card")
        pg.wait_for_timeout(800)
        pg.screenshot(path=shots / "09_analise_fila_pronta.png")
        b.close()

    print("\n".join(report))
    print("ERROS NO CONSOLE:" if errors else "sem erros no console")
    for e in errors:
        print("  ", e)


if __name__ == "__main__":
    main()
