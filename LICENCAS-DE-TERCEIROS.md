# Licenças de terceiros

O código do Revisor de Vídeos é licenciado sob a **GPL-3.0-or-later** (arquivo [LICENSE](LICENSE)).
O app pronto (Releases) leva dentro os programas e dados abaixo. Todos têm licença livre e
compatível com a GPL-3.0. Nenhum deles se conecta à internet quando o app está em uso.

| Peça | Versão | Licença | Para que serve no app | Código-fonte |
|---|---|---|---|---|
| FFmpeg / FFprobe | 8.1.3 no Mac (montado do código); build do BtbN no Windows | GPL-2.0-or-later (montado com libx264) | ler os vídeos, áudio, trechos | https://ffmpeg.org · https://github.com/BtbN/FFmpeg-Builds |
| x264 (libx264) | ramo `stable` | GPL-2.0-or-later | gerar o trecho em MP4 quando o navegador não toca o original | https://code.videolan.org/videolan/x264 |
| Tesseract OCR | 5.5.3 | Apache-2.0 | ler o texto da tela (ortografia, tarja) | https://github.com/tesseract-ocr/tesseract |
| Leptonica | 1.87.0 | licença Leptonica (estilo BSD-2) | imagens para o Tesseract | https://github.com/DanBloomberg/leptonica |
| tessdata_fast `por` | — | Apache-2.0 | modelo de português do Tesseract | https://github.com/tesseract-ocr/tessdata_fast |
| whisper.cpp (ggml) | v1.9.5 | MIT | transcrever as falas, sem internet | https://github.com/ggml-org/whisper.cpp |
| Modelo `ggml-small-q5_1.bin` | — | MIT (pesos do Whisper, OpenAI) | modelo de fala | https://huggingface.co/ggerganov/whisper.cpp |
| Python | 3.12 | PSF License 2.0 | o app em si | https://www.python.org |
| NumPy | — | BSD-3-Clause (e partes 0BSD, MIT, Zlib, CC0) | contas de imagem e áudio | https://numpy.org |
| Pillow | — | MIT-CMU (HPND) | imagens | https://python-pillow.org |
| spylls | 0.1.7 | MIT | ortografia (Hunspell em Python) | https://github.com/zverok/spylls |
| PyInstaller (bootloader) | — | GPL-2.0-or-later com exceção do bootloader | empacotar o app | https://pyinstaller.org |
| Dicionário pt-BR (VERO) | — | LGPL-3.0 / MPL-1.1 | ortografia em português | [revisor/data/dict/LICENSE_pt_BR.txt](revisor/data/dict/LICENSE_pt_BR.txt) |
| Dicionários en-US e en-GB (SCOWL / LibreOffice) | — | ver o arquivo (LGPL e licenças permissivas) | ortografia em inglês | [revisor/data/dict/LICENSE_en.txt](revisor/data/dict/LICENSE_en.txt) |
| Dicionário de latim | — | GPL-2.0-or-later | ortografia em latim | [revisor/data/dict/LICENSE_la.txt](revisor/data/dict/LICENSE_la.txt) |
| IBM Plex Sans e Mono | — | SIL Open Font License 1.1 | fontes das telas | [revisor/ui/fonts/LICENSE_IBM_Plex.txt](revisor/ui/fonts/LICENSE_IBM_Plex.txt) |

As versões exatas e a forma como cada programa é montado estão em
[packaging/build_deps.py](packaging/build_deps.py). A montagem é feita pelo GitHub Actions
([.github/workflows/montar.yml](.github/workflows/montar.yml)), com o registro público de cada
montagem: qualquer pessoa pode conferir de onde veio cada arquivo do app.
