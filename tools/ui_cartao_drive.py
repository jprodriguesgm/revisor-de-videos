"""Teste no navegador (Playwright) dos pedidos do JP de 23/11/2026: colar o cartão do Planner, revisão
reconhecida pelos vídeos, transcrição pronta (e adicionada à mão) e o Google Drive opcional.

Uso (abre o próprio app numa pasta de trabalho temporária, com um rclone de mentira):
    python3 tools/ui_cartao_drive.py <pasta de trabalho> [--porta 8799] [--chrome /caminho/do/chrome]

Capturas em <pasta de trabalho>/capturas. Nomes fictícios.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tests"))
from revisor import media, transcricao  # noqa: E402

CARD = """> ###Preenchimento do professor

Data da gravação: 01/10/2026

Nome completo do professor:  Maria Clara Souza Andrade

Nome que será utilizado na aula:  Maria Clara Souza

Matrícula: não sei

Telefone: (31) 90000-0000

Curso:  MBA em Finanças Corporativas

Tipo do curso:  Pós Graduação

Disciplina: Valuation de Empresas

Microfundamento: Não
"""
NAMES = ["01 Introdução ao valuation.mp4", "02 Fluxo de caixa descontado.mp4", "03 Múltiplos de mercado.mp4"]


def video(path: Path, dur: float, freq: int):
    subprocess.run([media.ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    f"testsrc2=size=640x360:rate=30000/1001:duration={dur}", "-f", "lavfi", "-i",
                    f"sine=frequency={freq}:sample_rate=48000:duration={dur}", "-c:v", "mpeg4", "-q:v", "4",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path)], check=True)


def api(base, path, body=None):
    req = urllib.request.Request(base + "api/" + path, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"} if body is not None else {})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def wait_queue(base, timeout=240):
    for _ in range(timeout * 2):
        q = api(base, "queue")
        if q["entries"] and all(e["status"] in ("done", "error") for e in q["entries"]):
            return
        time.sleep(0.5)
    raise SystemExit("a análise não terminou")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("work")
    ap.add_argument("--porta", type=int, default=8799)
    ap.add_argument("--chrome", default=None)
    a = ap.parse_args()
    work = Path(a.work)
    shots = work / "capturas"
    shots.mkdir(parents=True, exist_ok=True)
    home = work / "home"
    # pasta 1 (primeira revisão)
    p1 = work / "conferir" / "2026 11 10 Maria Clara Souza"
    p1.mkdir(parents=True, exist_ok=True)
    for k, n in enumerate(NAMES):
        if not (p1 / n).exists():
            video(p1 / n, 8 + k, 440 + 110 * k)
    d0 = media.probe(p1 / NAMES[0]).duration
    d2 = media.probe(p1 / NAMES[2]).duration
    transcricao.write(p1 / "Transcrições", NAMES[0], transcricao.build(
        NAMES[0], d0, [[1.0, 1.4, "pessoal", 1.0], [1.5, 1.9, "errei", 1.0]], [[1.0, 1.9, "pessoal errei"]], model="ggml-small-q5_1.bin"))
    transcricao.write(p1 / "Transcrições", NAMES[2], transcricao.build(NAMES[2], d2 + 5, [[1, 2, "oi", 1.0]], [[1, 2, "oi"]]))
    srt = work / "02 premiere.srt"
    srt.write_text("1\n00:00:01,000 --> 00:00:03,000\nvamos retomando daqui\n", encoding="utf-8")
    # rclone de mentira + "Drive"
    from test_drive import FAKE, _setup                                 # noqa: E402
    fake_tmp = work / "fake"
    fake_tmp.mkdir(exist_ok=True)
    fake = _setup(fake_tmp)
    assert FAKE
    dest = work / "Vídeos para conferir"
    dest.mkdir(exist_ok=True)

    env = dict(os.environ, REVISOR_HOME=str(home), FAKE_DRIVE=str(fake_tmp / "drive"))
    srv = subprocess.Popen([sys.executable, "-m", "revisor", "abrir", "--sem-navegador", "--porta", str(a.porta)],
                           cwd=str(HERE), env=env)
    base = f"http://127.0.0.1:{a.porta}/"
    for _ in range(100):
        try:
            api(base, "state")
            break
        except Exception:
            time.sleep(0.2)
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path=a.chrome) if a.chrome else p.chromium.launch()
            pg = b.new_page(viewport={"width": 1440, "height": 1000})
            errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(base + "#/inicio")
            pg.fill("#pasta", str(p1))
            pg.press("#pasta", "Enter")
            pg.wait_for_selector("text=Tem o cartão do Planner?")
            pg.wait_for_selector(".checks .ok")
            pg.screenshot(path=str(shots / "01-inicio-colar-cartao.png"), full_page=True)
            # .txt exportado (Windows-1252, com tabulação)
            txt = work / "cartao.txt"
            txt.write_bytes("Nome que será utilizado na aula\tAna Lima\nCurso = MBA em Gestão\n".encode("cp1252"))
            pg.click("text=Colar cartão")
            pg.set_input_files(".modal input[type=file]", str(txt))
            pg.wait_for_selector(".read >> text=MBA em Gestão")
            pg.screenshot(path=str(shots / "02b-janela-cartao-txt.png"), full_page=True)
            pg.click(".modal footer >> text=Cancelar")
            pg.click("text=Colar cartão")
            pg.fill("textarea.paste", CARD)
            pg.wait_for_selector(".read .r.warn")
            pg.screenshot(path=str(shots / "02-janela-cartao.png"), full_page=True)
            pg.click("text=Preencher a revisão")
            pg.wait_for_selector("text=Cartão colado.")
            assert pg.input_value("#prof") == "Maria Clara Souza"
            assert pg.input_value("#curso") == "MBA em Finanças Corporativas"
            assert pg.input_value("#tarja") == "Maria Clara Souza"
            assert pg.is_visible("text=Data da gravação diferente")
            pg.screenshot(path=str(shots / "03-inicio-preenchido.png"), full_page=True)
            pg.click("text=Analisar vídeos")
            pg.wait_for_url("**#/analise")
            wait_queue(base)
            pg.wait_for_timeout(1200)
            assert pg.is_visible("text=Falas: transcrição pronta")
            assert pg.is_visible("text=Transcrição não bate")
            pg.screenshot(path=str(shots / "04-analise-transcricao.png"), full_page=True)
            pg.click("text=Adicionar transcrição manualmente")
            pg.select_option("#tr-video", label=NAMES[1].rsplit(".", 1)[0])
            pg.fill("#tr-file", str(srt))
            pg.screenshot(path=str(shots / "05-adicionar-transcricao.png"), full_page=True)
            pg.click(".modal footer >> text=Adicionar")
            pg.wait_for_selector("#toast.show")
            wait_queue(base)
            pg.wait_for_timeout(1500)
            assert pg.locator("text=Falas: transcrição pronta (por frase)").count() == 1
            pg.screenshot(path=str(shots / "06-analise-depois-de-adicionar.png"), full_page=True)
            # baixou de novo com outro nome
            p2 = work / "conferir" / "2026 11 10 Maria Clara"
            p2.mkdir(exist_ok=True)
            for k, n in enumerate(NAMES):
                if not (p2 / n).exists():
                    video(p2 / n, 8 + k + (1 if k == 2 else 0), 440 + 110 * k)
            pg.goto(base + "#/inicio")
            pg.fill("#pasta", str(p2))
            pg.press("#pasta", "Enter")
            pg.wait_for_selector(".match")
            pg.screenshot(path=str(shots / "07-revisao-reconhecida.png"), full_page=True)
            pg.click("text=Continuar nessa revisão")
            pg.wait_for_selector("text=Continuando a revisão")
            assert pg.input_value("#prof") == "Maria Clara Souza"
            pg.screenshot(path=str(shots / "08-revisao-continuada.png"), full_page=True)
            # Google Drive
            pg.goto(base + "#/config/drive")
            pg.wait_for_selector("text=Desligado.")
            pg.screenshot(path=str(shots / "09-config-drive-desligado.png"))
            api(base, "settings/save", {"drive_rclone": str(fake), "drive_root": "Gravações IEC", "drive_dest": str(dest)})
            pg.click("button.switch")
            pg.wait_for_selector("text=1 · Conexão")
            pg.click("text=Testar conexão")
            pg.wait_for_selector("text=Conectado na conta")
            pg.screenshot(path=str(shots / "10-config-drive-ligado.png"))
            pg.goto(base + "#/inicio")
            pg.reload()
            pg.wait_for_selector("text=Baixar do Drive")
            pg.click("text=Baixar do Drive")
            pg.fill("#dr-link", "https://drive.google.com/drive/folders/SAIDA1234567890")
            pg.click(".modal >> text=Ler")
            pg.wait_for_selector(".dl-row")
            assert pg.input_value("#dr-name") == "2026 11 10 Maria Clara Souza"
            pg.screenshot(path=str(shots / "11-baixar-do-drive.png"), full_page=True)
            pg.click(".modal footer >> text=Baixar 2 vídeos")
            pg.wait_for_function("() => location.hash.startsWith('#/inicio') && !document.querySelector('.modal')", timeout=30000)
            pg.wait_for_selector(".checks .ok")
            assert "2026 11 10 Maria Clara Souza" in pg.input_value("#pasta")
            pg.screenshot(path=str(shots / "12-depois-de-baixar.png"), full_page=True)
            assert not errs, errs
            b.close()
        print("TUDO OK")
    finally:
        srv.terminate()


if __name__ == "__main__":
    main()
