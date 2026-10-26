"""Teste no navegador (Playwright) dos pedidos do JP de 26/10/2026:
relatório de tempo feito pelo app, assistir ao vídeo inteiro (Espaço, J K L, parar nos avisos)
e o modo editor ("Conferir antes de entregar" → Checagem → Pronto para enviar).

Uso (com o app já aberto: python3 -m revisor abrir --sem-navegador):
    python3 tools/ui_editor.py <pasta das aulas> <pasta dos brutos> <vinheta_inicio> <vinheta_final> <capturas> [--porta 8765]

O Chromium do Playwright não toca H.264 nem AAC: para testar o play, a pasta das aulas precisa de
vídeos que ele toque (AV1 ou VP9 com Opus, dentro de .mp4). O app analisa qualquer formato.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright


def api(base, path, body=None):
    req = urllib.request.Request(base + "api/" + path, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"} if body is not None else {})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def wait_analysis(pg, limit=900):
    t0 = time.time()
    while time.time() - t0 < limit:
        if pg.locator("text=Análise concluída").count():
            return
        time.sleep(2)
    raise SystemExit("a análise não terminou")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("aulas")
    ap.add_argument("brutos")
    ap.add_argument("vin_in")
    ap.add_argument("vin_out")
    ap.add_argument("saida")
    ap.add_argument("--porta", type=int, default=8765)
    a = ap.parse_args()
    aulas, brutos = Path(a.aulas).resolve(), Path(a.brutos).resolve()
    out = Path(a.saida)
    out.mkdir(parents=True, exist_ok=True)
    base = f"http://127.0.0.1:{a.porta}/"
    for old in aulas.glob("Relatorio_tempo_*.txt"):
        old.unlink()
    api(base, "settings/save", {"mode": "revisor"})
    api(base, "settings", {"vinheta_in": a.vin_in, "vinheta_out": a.vin_out, "transcribe": False, "play_stop_warn": False})
    try:
        api(base, "settings/editors", {"op": "add", "name": "Mônica"})
    except Exception:
        pass
    errors = []
    ok = []

    def check(cond, msg):
        (ok if cond else errors).append(msg)
        print(("ok  " if cond else "ERRO ") + msg)

    with sync_playwright() as p:
        b = p.chromium.launch(args=["--autoplay-policy=no-user-gesture-required"])
        ctx = b.new_context(viewport={"width": 1440, "height": 900})
        pg = ctx.new_page()
        pg.on("console", lambda m: errors.append(f"console {m.type}: {m.text}") if m.type == "error" else None)
        pg.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))

        # ------------------------------------------------ 1. relatório de tempo (modo revisor, Início)
        pg.goto(base + "#/inicio")
        pg.wait_for_selector("text=Nova revisão")
        pg.fill("#pasta", str(aulas))
        pg.press("#pasta", "Enter")
        pg.wait_for_selector("button:has-text('Gerar relatório de tempo')")
        pg.screenshot(path=out / "1a_sem_relatorio.png")
        pg.click("button:has-text('Gerar relatório de tempo')")
        pg.wait_for_selector(".modal:has-text('Relatório de tempo')")
        pg.locator(".modal input.input").nth(0).fill(str(brutos))
        check(pg.locator(".modal input.input").nth(1).input_value() == str(aulas), "pasta dos editados já preenchida")
        pg.click(".modal footer button:has-text('Gerar relatório de tempo')")
        pg.wait_for_selector(".modal:has-text('Salvo na pasta dos editados')")
        pg.click(".modal summary")
        pg.screenshot(path=out / "1b_relatorio_gerado.png")
        txt = pg.locator(".modal .tr-pre").inner_text()
        check("Ignorados por terminarem em -D ou -E: brutos 2, editados 0" in txt, "txt com a linha dos -D/-E")
        check("BRUTOS (3 arquivos)" in txt and "EDITADOS (2 arquivos)" in txt, "txt com 3 brutos e 2 editados")
        pg.click(".modal footer button:has-text('Fechar')")
        pg.wait_for_selector("text=Relatório de tempo lido")
        check(len(list(aulas.glob("Relatorio_tempo_*.txt"))) == 1, "txt salvo na pasta dos editados")

        # ------------------------------------------------ 2. analisar e assistir
        pg.fill("#tarja", "Maria Clara Souza")
        pg.click("text=Analisar vídeos")
        pg.wait_for_selector("text=Analisando os vídeos")
        wait_analysis(pg)
        pg.goto(base + "#/revisao/1")
        pg.wait_for_selector(".vw-img")
        pg.wait_for_timeout(800)
        hud0 = pg.inner_text(".vw-hud.tl")
        pg.keyboard.press("Space")
        pg.wait_for_selector(".vw.playing", timeout=8000)
        pg.wait_for_timeout(2500)
        t1 = pg.evaluate("document.querySelector('.vw-play') ? document.querySelector('.vw-play').currentTime : -1")
        check(t1 > 0.5, f"vídeo tocando no visor (currentTime {t1:.2f})")
        check("tocando" in pg.inner_text(".vw-hud.tl"), "HUD mostra 'tocando'")
        pg.screenshot(path=out / "2a_tocando.png")
        pg.keyboard.press("l")
        pg.wait_for_timeout(300)
        check("1,5×" in pg.inner_text(".vw-playhud"), "L acelera para 1,5×")
        pg.keyboard.press("j")
        pg.wait_for_timeout(300)
        t2 = pg.evaluate("document.querySelector('.vw-play').currentTime")
        check(t2 < t1 + 1.5, f"J voltou 5 s ({t2:.2f})")
        pg.keyboard.press("k")
        pg.wait_for_timeout(1500)
        check(not pg.locator(".vw.playing").count(), "K pausou")
        check(not pg.locator(".vw-play").count(), "o vídeo saiu depois da imagem parada carregar")
        hud1 = pg.inner_text(".vw-hud.tl")
        check("tocando" not in hud1 and hud1.split(" ")[0] != hud0.split(" ")[0], f"parado em outro frame ({hud1[:40]})")
        pg.screenshot(path=out / "2b_pausado.png")
        # clique na linha do tempo durante o play: continua tocando
        pg.keyboard.press("Space")
        pg.wait_for_selector(".vw.playing")
        box = pg.locator("canvas.wc").bounding_box()
        pg.mouse.click(box["x"] + box["width"] * 0.6, box["y"] + box["height"] / 2)
        pg.wait_for_timeout(800)
        check(pg.locator(".vw.playing").count() == 1, "clique na linha do tempo pula e continua tocando")
        tt = pg.evaluate("document.querySelector('.vw-play').currentTime")
        check(tt > 50, f"pulou para ~60% do vídeo ({tt:.1f} s)")
        pg.keyboard.press("ArrowRight")
        pg.wait_for_timeout(800)
        check(not pg.locator(".vw.playing").count() and " de " in pg.inner_text(".vw-hud.tl"), "→ pausa e vai ao próximo item")
        # parar nos avisos: volta ao começo e toca
        pg.mouse.click(box["x"] + 2, box["y"] + box["height"] / 2)
        pg.wait_for_timeout(500)
        pg.keyboard.press("a")
        pg.wait_for_timeout(300)
        check(pg.locator(".tool.on:has-text('Parar nos avisos')").count() == 1, "A liga 'Parar nos avisos'")
        pg.keyboard.press("Space")
        pg.wait_for_selector("#toast:has-text('Parou no aviso')", timeout=30000)
        pg.wait_for_timeout(600)
        check(not pg.locator(".vw.playing").count(), "parou sozinho no aviso")
        check(pg.locator(".rv-warn").count() == 1, "cartão do aviso aparece")
        pg.screenshot(path=out / "2c_parou_no_aviso.png")
        pg.keyboard.press("a")
        # C tocando: pausa e foca o comentário
        pg.keyboard.press("Space")
        pg.wait_for_selector(".vw.playing")
        pg.wait_for_timeout(700)
        pg.keyboard.press("c")
        pg.wait_for_timeout(600)
        check(not pg.locator(".vw.playing").count() and pg.evaluate("document.activeElement.id") == "cmt", "C pausa e abre o comentário")
        pg.keyboard.press("Escape")
        # Espaço com o botão "Assistir" em foco: não pode tocar e pausar ao mesmo tempo
        pg.click(".tool:has-text('Assistir')")
        pg.wait_for_selector(".vw.playing")
        pg.wait_for_timeout(500)
        pg.keyboard.press("Space")
        pg.wait_for_timeout(700)
        check(not pg.locator(".vw.playing").count(), "Espaço depois de clicar em Assistir pausa (sem clique duplo)")

        # ------------------------------------------------ 3. modo editor
        api(base, "settings/save", {"mode": "editor", "my_name": "Mônica"})
        pg.goto(base + "#/inicio")
        pg.reload()
        pg.wait_for_selector("text=Conferir antes de entregar")
        check(pg.locator("#steps .step:has-text('Checagem')").count() == 1, "etapas do modo editor")
        check(not pg.locator("#entrega").count() and not pg.locator("#curso").count(), "Início sem entrega e curso")
        pg.fill("#pasta", str(aulas))
        pg.press("#pasta", "Enter")
        pg.wait_for_selector("text=Já tem relatório de tempo")
        pg.fill("#brutos", str(brutos))
        pg.screenshot(path=out / "3a_inicio_editor.png")
        pg.click("button:has-text('Conferir os vídeos')")
        pg.wait_for_selector("text=Analisando os vídeos")
        wait_analysis(pg)
        check(pg.locator("button:has-text('Ver o que falta')").count() == 1, "Análise leva ao 'Ver o que falta'")
        pg.goto(base + "#/revisao/1")
        pg.wait_for_selector(".rv-chk")
        pg.wait_for_timeout(600)
        check(not pg.locator("#cmt").count(), "sem campo de comentário")
        check(not pg.locator(".tool:has-text('Comentar')").count() and not pg.locator(".tool:has-text('Conta-gotas')").count(),
              "sem Comentar e Conta-gotas")
        check(not pg.locator("select.rv-ed").count(), "sem escolha de editor na barra")
        n_w = pg.locator(".ed-w").count()
        check(n_w > 0, f"lista com {n_w} avisos")
        off0 = pg.locator(".ed-w.off").count()          # (de uma rodada anterior do teste)
        pg.locator(".ed-w:not(.off)").first.click()
        pg.wait_for_selector(".rv-warn:not(.off) button.mini:text-is('Ignorar')")
        pg.screenshot(path=out / "3b_checagem.png")
        pg.click(".rv-warn button.mini:text-is('Ignorar')")
        pg.wait_for_timeout(800)
        check(pg.locator(".ed-w.off").count() == off0 + 1, "Ignorar deixa o aviso apagado na lista")
        pg.keyboard.press("Space")
        pg.wait_for_selector(".vw.playing")
        pg.keyboard.press("Space")
        pg.goto(base + "#/final")
        pg.wait_for_selector("text=Pronto para enviar?")
        pg.wait_for_timeout(500)
        check(pg.locator(f".en-ig:text-is('{off0 + 1} ignorado{'s' if off0 else ''}')").count() >= 1, "Pronto para enviar mostra os ignorados")
        check(pg.locator(".f-card:has-text('Mônica')").count() == 1, "horas com o nome do editor")
        pg.screenshot(path=out / "3c_pronto_para_enviar.png", full_page=True)
        w = pg.locator(".en-w").first
        tc = w.locator(".mono").inner_text()
        w.click()
        pg.wait_for_selector(".rv-chk")
        pg.wait_for_timeout(800)
        check(pg.inner_text(".vw-hud.tl").startswith(tc[:5]) or tc in pg.inner_text(".vw-hud.tl"),
              f"aviso do Pronto para enviar abre no tempo certo ({tc})")
        pg.goto(base + "#/final")
        pg.wait_for_selector("text=Pronto para enviar?")
        pg.click(".f-card button:has-text('Gerar de novo')")
        pg.wait_for_selector(".modal")
        check(pg.locator(".modal input.input").nth(0).input_value() == str(brutos), "brutos lembrados na revisão")
        pg.click(".modal footer button:has-text('Gerar')")
        pg.wait_for_selector(".modal:has-text('Salvo na pasta dos editados')")
        pg.click(".modal footer button:has-text('Fechar')")
        pg.goto(base + "#/config")
        pg.wait_for_selector("#cfg-modo")
        check(not pg.locator(".cfg-nav button:has-text('Equipe')").count(), "Configurações sem Equipe no modo editor")
        pg.screenshot(path=out / "3d_config_modo.png")
        pg.goto(base + "#/resumo")
        pg.wait_for_selector("text=Pronto para enviar?")
        check(True, "Resumo geral leva ao Pronto para enviar")
        # janela estreita
        pg.set_viewport_size({"width": 1100, "height": 720})
        pg.goto(base + "#/revisao/1")
        pg.wait_for_selector(".rv-chk")
        pg.wait_for_timeout(700)
        pg.screenshot(path=out / "3e_checagem_1100.png")
        api(base, "settings/save", {"mode": "revisor"})
        b.close()
    errs = [e for e in errors if not e.startswith(("console", "pageerror")) or True]
    print(f"\n{len(ok)} ok, {len(errors)} problemas")
    for e in errors:
        print("  -", e)
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
