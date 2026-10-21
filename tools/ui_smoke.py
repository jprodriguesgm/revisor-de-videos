"""Teste das telas no navegador (Playwright): percorre Início → Análise → Resumo → Revisão
(frame, lista com passos, comentário, cópia, G, P, zoom, trecho de 8 s, abas).

Uso (com o app já aberto: python3 -m revisor abrir --sem-navegador):
    python3 tools/ui_smoke.py <pasta das aulas> <vinheta_inicio> <vinheta_final> <saída das capturas> [--porta 8765]
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pasta")
    ap.add_argument("vin_in")
    ap.add_argument("vin_out")
    ap.add_argument("saida")
    ap.add_argument("--porta", type=int, default=8765)
    ap.add_argument("--tarja", default="Maria Clara Souza")
    ap.add_argument("--sair", action="store_true", help="no fim, aperta Sair (o app fecha)")
    a = ap.parse_args()
    out = Path(a.saida)
    out.mkdir(parents=True, exist_ok=True)
    base = f"http://127.0.0.1:{a.porta}/"
    errors = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1440, "height": 900}, permissions=["clipboard-read", "clipboard-write"])
        pg = ctx.new_page()
        pg.on("console", lambda m: errors.append(f"console {m.type}: {m.text}") if m.type in ("error", "warning") else None)
        pg.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        pg.goto(base + "#/inicio")
        pg.wait_for_selector("text=Nova revisão")
        pg.screenshot(path=out / "1a_inicio_vazio.png")

        # pasta: janela do sistema não existe aqui → navegador de pastas do app
        pg.click("text=Escolher pasta")
        pg.wait_for_selector(".modal")
        pg.fill(".modal input.input", str(Path(a.pasta).parent))
        pg.press(".modal input.input", "Enter")
        pg.wait_for_selector(f".modal .item:has-text('{Path(a.pasta).name}')")
        pg.screenshot(path=out / "1b_navegador_pastas.png")
        pg.click(f".modal .item:has-text('{Path(a.pasta).name}')")
        pg.wait_for_selector(".modal button:has-text('Escolher esta pasta (')")
        pg.click(".modal button:has-text('Escolher esta pasta')")
        pg.wait_for_selector("text=Relatório de tempo lido")

        for label, f in (("Inicial", a.vin_in), ("Final", a.vin_out)):
            pg.click(f".vinhetas .v:has-text('{label}') button")
            pg.wait_for_selector(".modal")
            pg.fill(".modal input.input", str(Path(f).parent))
            pg.press(".modal input.input", "Enter")
            pg.click(f".modal .item:has-text('{Path(f).name}')")
            pg.click(".modal button:has-text('Escolher este vídeo')")
            pg.wait_for_selector(f".vinhetas .v:has-text('{Path(f).name}')")
            # a tela é redesenhada; a pasta continua preenchida
            pg.wait_for_selector("text=Relatório de tempo lido")
        pg.fill("#tarja", a.tarja)
        pg.screenshot(path=out / "1c_inicio_preenchido.png")
        print("professor:", pg.input_value("#prof"), "| entrega:", pg.input_value("#entrega"),
              "| tarja:", pg.input_value("#tarja"))

        pg.click("text=Analisar vídeos")
        pg.wait_for_selector("text=Analisando os vídeos")
        time.sleep(1.5)
        pg.screenshot(path=out / "2a_analise.png")
        t0 = time.time()
        while time.time() - t0 < 900:
            if pg.locator("text=Análise concluída").count():
                break
            time.sleep(2)
        pg.screenshot(path=out / "2b_analise_pronta.png")
        pg.click("text=Ver resumo geral")
        pg.wait_for_selector("text=Quem editou cada vídeo")
        pg.wait_for_timeout(800)
        pg.screenshot(path=out / "3a_resumo.png", full_page=True)
        pg.select_option(".ed-head select", "Mônica")
        pg.click("text=Aplicar a todos")
        pg.wait_for_timeout(1200)
        pg.screenshot(path=out / "3b_resumo_editores.png", full_page=True)
        eds = pg.eval_on_selector_all(".grid-row select", "els => els.map(e => e.value)")
        print("editores:", eds)
        pg.click("text=Começar revisão pelo vídeo 01")
        pg.wait_for_selector(".vw-img")
        pg.wait_for_timeout(1500)
        pg.screenshot(path=out / "4a_revisao.png")
        n_items = pg.locator(".film .fi").count()
        print("itens no vídeo 01:", n_items, "|", pg.text_content(".rv-count"))
        # lista: anda até achar um item com passos
        for _ in range(n_items):
            if pg.locator(".vw-steps:not(.hidden)").count():
                break
            pg.keyboard.press("ArrowRight")
            pg.wait_for_timeout(250)
        if pg.locator(".vw-steps:not(.hidden)").count():
            pg.click(".vw-steps .st >> nth=0")
            pg.wait_for_timeout(600)
            pg.screenshot(path=out / "4b_lista_passo1.png")
        # comentário (salva sozinho) e cópia
        pg.keyboard.press("c")
        pg.keyboard.type("Texto entra antes da fala.")
        pg.wait_for_timeout(1200)
        pg.keyboard.press("Escape")
        pg.keyboard.press("Control+c")
        pg.wait_for_timeout(1500)
        print("copiado:", pg.evaluate("navigator.clipboard.readText()"))
        # G, P, zoom, trecho
        pg.keyboard.press("g")
        pg.wait_for_timeout(1500)
        pg.screenshot(path=out / "4c_graficos.png")
        pg.keyboard.press("p")
        box = pg.locator(".vw").bounding_box()
        pg.mouse.move(box["x"] + box["width"] * 0.3, box["y"] + box["height"] * 0.4)
        pg.wait_for_timeout(800)
        pg.mouse.click(box["x"] + box["width"] * 0.3, box["y"] + box["height"] * 0.4)
        pg.wait_for_timeout(1200)
        pg.screenshot(path=out / "4d_conta_gotas.png")
        pg.keyboard.press("Escape")
        pg.mouse.move(box["x"] + box["width"] * 0.5, box["y"] + box["height"] * 0.5)
        pg.mouse.wheel(0, -500)
        pg.wait_for_timeout(1200)
        pg.screenshot(path=out / "4e_zoom.png")
        pg.keyboard.press("z")
        pg.keyboard.press("v")
        pg.wait_for_timeout(5000)
        pg.screenshot(path=out / "4f_trecho_8s.png")
        print("trecho:", pg.evaluate("(() => { const v = document.querySelector('.vw-clip video'); "
                                      "return v ? [Math.round(v.currentTime * 10) / 10, v.src.split('/api/')[1]] : null })()"))
        pg.keyboard.press("Escape")
        tabs = pg.locator(".rv-tab")
        if tabs.count() > 1:
            tabs.nth(1).click()
            pg.wait_for_selector(".rv-tab.on >> nth=0")
            pg.wait_for_timeout(1500)
            pg.screenshot(path=out / "4g_video_02.png")
            pg.keyboard.press("c")
            pg.keyboard.type("Áudio baixo no começo.")
            pg.wait_for_timeout(1200)
            pg.keyboard.press("Escape")

        # ---- etapa 5: resumo final
        pg.click("#steps a:has-text('Resumo final')")
        pg.wait_for_selector(".f-row")
        pg.wait_for_timeout(1200)
        pg.screenshot(path=out / "6a_resumo_final.png", full_page=True)
        print("comentários no resumo final:", pg.locator(".f-row").count(), "|", pg.text_content(".f-top"))
        pg.click(".f-row >> nth=-1 >> .f-seg button:has-text('Sem frame')")
        pg.wait_for_timeout(500)
        pg.click("button:has-text('Copiar selecionados, como marcado')")
        pg.wait_for_timeout(2500)
        print("copiado (resumo final):", pg.evaluate("navigator.clipboard.readText()").replace("\n", " | "))
        html = pg.evaluate("""(async () => { const it = (await navigator.clipboard.read())[0];
            return it.types.includes('text/html') ? (await (await it.getType('text/html')).text()).length : 0 })()""")
        print("HTML copiado (com imagem):", html, "caracteres")
        pg.click(".f-row >> nth=0 >> .cbx")
        pg.wait_for_timeout(500)
        pg.click("button:has-text('Gerar SRT de cada vídeo')")
        pg.wait_for_timeout(1500)
        print("SRT:", sorted(p.name for p in Path(a.pasta).glob("*.srt")))
        pg.screenshot(path=out / "6b_resumo_final_marcado.png", full_page=True)

        # ---- pacote: exportar e abrir
        pg.click("text=Salvar e exportar revisão")
        pg.wait_for_selector("text=Levar a revisão para outro computador")
        dest = out / "pacotes"
        dest.mkdir(exist_ok=True)
        pg.fill(".pk-sec >> nth=0 >> input.input", str(dest))
        pg.screenshot(path=out / "7a_pacote.png", full_page=True)
        pg.click("button:has-text('Exportar pacote')")
        pg.wait_for_selector("text=Pacote salvo.")
        pkg = next(dest.iterdir())
        print("pacote:", pkg.name, sorted(x.name for x in pkg.iterdir()))
        pg.fill(".pk-sec >> nth=1 >> input.input", str(pkg))
        pg.press(".pk-sec >> nth=1 >> input.input", "Enter")
        pg.wait_for_selector(".pk-v")
        pg.wait_for_timeout(500)
        pg.screenshot(path=out / "7b_pacote_aberto.png", full_page=True)
        if pg.locator(".pk-conf").count():
            pg.click(".pk-conf button:has-text('Juntar as duas')")
        pg.click("button:has-text('Abrir revisão') >> nth=-1")
        pg.wait_for_timeout(2000)
        print("depois de abrir o pacote:", pg.evaluate("location.hash"))

        # ---- relatório do mês
        pg.click(".top-actions a:has-text('Relatório do mês')")
        pg.wait_for_selector(".rel-t")
        pg.wait_for_timeout(600)
        pg.screenshot(path=out / "8a_relatorio.png", full_page=True)
        print("relatório:", pg.text_content(".stats").replace("\n", " "))

        # ---- configurações
        pg.click(".top-actions a:has-text('Configurações')")
        pg.wait_for_selector("#cfg-cache")
        pg.wait_for_timeout(1500)
        pg.screenshot(path=out / "9a_config.png")
        pg.fill("#cfg-newed", "Paula")
        pg.click("#cfg-equipe button:has-text('Adicionar')")
        pg.wait_for_timeout(600)
        pg.click(".cfg-nav button:has-text('Equipe')")
        pg.wait_for_timeout(900)
        pg.screenshot(path=out / "9b_config_equipe.png")
        pg.select_option("#cfg-tc", "ndf")
        pg.wait_for_timeout(500)
        pg.fill("#cfg-neww", "habeas corpus")
        pg.click("#cfg-ortografia button:has-text('Adicionar')")
        pg.wait_for_timeout(800)
        pg.screenshot(path=out / "9c_config_tudo.png", full_page=True)
        pg.select_option("#cfg-tc", "seconds")
        pg.set_viewport_size({"width": 1100, "height": 800})
        for hsh, name in (("#/final", "6c_final_estreito"), ("#/relatorio", "8b_relatorio_estreito"),
                          ("#/pacote", "7c_pacote_estreito")):
            pg.goto(base + hsh)
            pg.wait_for_timeout(1500)
            pg.screenshot(path=out / f"{name}.png", full_page=True)
        pg.set_viewport_size({"width": 1440, "height": 900})

        # voltar ao início: a revisão salva aparece
        pg.goto(base + "#/inicio")
        pg.wait_for_selector("text=Nova revisão")
        pg.click("text=Abrir revisão salva")
        pg.wait_for_selector(".modal .saved")
        pg.screenshot(path=out / "5_abrir_salva.png")
        pg.keyboard.press("Escape")

        # etapa 6: botão Sair (fecha o app; a página mostra que foi fechado)
        if a.sair:
            pg.click("#quit-btn")
            pg.wait_for_selector(".modal >> text=Fechar o Revisor de Vídeos?")
            pg.screenshot(path=out / "10a_sair.png")
            pg.click(".modal footer .btn.primary")
            pg.wait_for_selector("text=O Revisor de Vídeos foi fechado.")
            pg.screenshot(path=out / "10b_fechado.png")
        b.close()
    print("\n".join(errors) or "sem erros no console")
    return 1 if any("pageerror" in e or "console error" in e for e in errors) else 0


if __name__ == "__main__":
    sys.exit(main())
