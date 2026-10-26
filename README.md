# Revisor de Vídeos

App para revisar rápido as videoaulas editadas antes da entrega. Ele analisa cada vídeo e marca o que
precisa de atenção: áudio (picos, estouro, ruído, mudança de volume), cortes, textos que entram e saem
da tela, **ortografia** do texto na tela (português, inglês e latim), **tarja** com o nome do professor,
transições de slide, vinhetas, imagem congelada e falas como "errei" ou "retomando" (takes repetidos).
Na tela de revisão você anda de item em item, comenta, copia o frame com o comentário para o editor
e gera um SRT com as correções para importar na timeline.

Feito no Núcleo de Produção Digital da PUC Minas para o fluxo de videoaulas da pós-graduação.

![Tela de revisão](docs/guia/08-revisao.png)

## Baixar

| | Link direto (sempre a versão oficial mais nova) |
|---|---|
| **Mac** (chip Apple M1 ou mais novo, macOS 11+) | [Revisor-de-Videos-mac.zip](https://github.com/jprodriguesgm/revisor-de-videos/releases/latest/download/Revisor-de-Videos-mac.zip) |
| **Windows** 10/11 (64 bits) | [Revisor-de-Videos-windows.zip](https://github.com/jprodriguesgm/revisor-de-videos/releases/latest/download/Revisor-de-Videos-windows.zip) |

**Como instalar, cadastrar a equipe e usar: [GUIA.md](GUIA.md)** (passo a passo com imagens).

Todas as versões: [Releases](https://github.com/jprodriguesgm/revisor-de-videos/releases). Versões
"Montagem N (teste)" são de teste; a oficial é a marcada como **Latest**.

## Para a TI: privacidade e segurança

- **Nada sai do computador.** O app abre um servidor local que só escuta em `127.0.0.1` (recusa
  conexões de outros endereços e pedidos de outros sites) e mostra as telas no navegador.
- **Sem internet e sem IA online.** OCR (Tesseract) e transcrição de fala (whisper.cpp) rodam no
  próprio computador, com os modelos dentro do app. Nenhum vídeo, frame, áudio ou comentário é enviado
  a lugar nenhum.
- **Não pede administrador e não instala nada no sistema.** Os dados (configurações, cache, revisões)
  ficam numa pasta do usuário: `~/Library/Application Support/Revisor de Vídeos` (Mac) ou
  `%APPDATA%\Revisor de Vídeos` (Windows).
- **O app não tem assinatura da Apple nem da Microsoft** (o autor não tem conta de desenvolvedor). Por isso
  o Mac pede o comando `xattr` na primeira abertura e o Windows mostra "O Windows protegeu o computador".
- **Montagem rastreável.** Cada versão é montada pelo GitHub Actions a partir deste código
  ([.github/workflows/montar.yml](.github/workflows/montar.yml)), com testes e diagnóstico publicados
  na página de cada versão. Os programas de terceiros são montados do código-fonte oficial
  ([packaging/build_deps.py](packaging/build_deps.py)). Para conferir, dá para montar o app você mesmo
  (ver "Para quem programa").
- O repositório guarda **só código**: nenhum vídeo, frame ou dado de aula. Os nomes nos testes são
  fictícios.

## Licença

Copyright (C) 2026 João Paulo Rodrigues.

Software livre: você pode redistribuir e modificar sob os termos da **GNU General Public License,
versão 3 ou posterior** ([LICENSE](LICENSE)). Sem garantia de qualquer tipo.
Os programas e dados de terceiros que vão dentro do app e as licenças de cada um estão em
[LICENCAS-DE-TERCEIROS.md](LICENCAS-DE-TERCEIROS.md).

## Para quem programa

Python + FFmpeg (análise), numpy e Pillow; telas em HTML/CSS/JS puro servidas pela biblioteca padrão do
Python. As decisões do projeto estão em [PROJETO.md](PROJETO.md).

### O que precisa
- Python 3.10+ com `numpy`, `Pillow` e `spylls` (ver `requirements.txt`).
- FFmpeg/FFprobe e Tesseract (4.1 ou 5.x). No app final vão dentro do pacote
  (pasta `bin/`); para testar, os do sistema servem.
- Dados que já vão no repositório (`revisor/data/`):
  - `tessdata/por.traineddata` (tessdata_fast, Apache 2.0)
  - `dict/` dicionários Hunspell pt_BR (VERO, LGPL/MPL), en_US e en_GB
    (SCOWL/LibreOffice), la (latim, GPL) e `palavras_nucleo.txt`.
- Fala (etapa 2b, opcional): `whisper-cli` (whisper.cpp) e o modelo
  `ggml-small-q5_1.bin` (em `revisor/data/models/`, `bin/../models/` ou na variável
  `REVISOR_WHISPER_MODEL`). Sem eles a análise roda e a fala fica "sem_whisper".
- Só para gerar os vídeos de teste: `opencv-python`.

### Montar o app
GitHub → aba **Actions** → "Montar o app" → **Run workflow**. Com o campo **Versão oficial** vazio sai
uma versão de **teste** ("Montagem N (teste)", pré-lançamento). Com `1.1.0` no campo (ou uma etiqueta
`v1.1.0`) sai a versão **oficial**, que o link `releases/latest` entrega. Os zips têm nome fixo:
`Revisor-de-Videos-mac.zip` e `Revisor-de-Videos-windows.zip`.
Na mão (no próprio sistema):

    python packaging/build_deps.py      # bin/ (ffmpeg, ffprobe, tesseract, whisper-cli) e models/
    pip install -r requirements.txt pyinstaller
    pyinstaller --noconfirm packaging/revisor.spec      # dist/

`"Revisor de Videos" diagnostico` confere se tudo está dentro do app.

### Abrir pelo código
    python3 -m revisor                 # abre as telas no navegador (servidor só em 127.0.0.1)
    python3 -m revisor abrir --sem-navegador --porta 8765
    python3 -m revisor abrir --fechar-sozinho   # como o app: fecha sem página aberta
No Mac, dois cliques em `Abrir Revisor.command` (precisa de python3, ffmpeg e
tesseract no computador; o app empacotado da etapa 6 leva tudo dentro).
Configurações, cache e revisões salvas ficam em
`~/Library/Application Support/Revisor de Vídeos` (Mac) ou `%APPDATA%\Revisor de Vídeos`
(Windows); a variável `REVISOR_HOME` troca essa pasta.

### Testar
    python3 tools/make_test_videos.py          # gera aulas sintéticas com gabarito
    python3 -m revisor analisar <pasta> --cache cache \
        --vinheta-inicio tools/testdata/vinheta_inicio.mp4 \
        --vinheta-final tools/testdata/vinheta_final.mp4 \
        --nome-tarja "Maria Clara Souza"
    python3 tools/evaluate.py cache tools/testdata
    python3 -m pytest -q tests

    # telas no navegador (Playwright), com o app aberto (inclui a tela de revisão; e ui_novidades.py para a fila):
    python3 tools/ui_smoke.py <pasta das aulas> tools/testdata/vinheta_inicio.mp4 \
        tools/testdata/vinheta_final.mp4 <pasta das capturas>

    # relatório de tempo, assistir ao vídeo inteiro e modo editor (aulas em AV1/VP9 + Opus: ver o docstring):
    python3 tools/ui_editor.py <pasta das aulas> <pasta dos brutos> tools/testdata/vinheta_inicio.mp4 \
        tools/testdata/vinheta_final.mp4 <pasta das capturas>

    # etapa 2 sozinha, em análises que já estão no cache:
    python3 tools/text_only.py cache [-v] [--nome "Nome"] [--so-checar] [trecho do nome do vídeo]

    # etapa 2b (fala), calibragem:
    python3 tools/speech_calib.py rapido <cache> <Entrada.mov> <Saida.mov> <vídeos...> --budget 150
    python3 tools/speech_calib.py mostrar <cache> [--cortes]
