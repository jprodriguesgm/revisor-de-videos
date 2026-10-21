#!/bin/bash
# Abre o Revisor de Vídeos no navegador (para testar no Mac antes do app empacotado).
# Precisa de: python3, ffmpeg/ffprobe e tesseract. Os pacotes do Python são instalados
# só para o seu usuário (sem administrador), numa pasta do próprio app.
cd "$(dirname "$0")" || exit 1
export PATH="$PWD/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

falta=""
command -v python3 >/dev/null 2>&1 || falta="$falta python3"
command -v ffmpeg  >/dev/null 2>&1 || falta="$falta ffmpeg"
command -v ffprobe >/dev/null 2>&1 || falta="$falta ffprobe"
command -v tesseract >/dev/null 2>&1 || echo "Aviso: sem tesseract, o texto da tela (ortografia e tarja) não é lido."
if [ -n "$falta" ]; then
  echo "Não encontrei:$falta"
  echo "Sem isso o Revisor não abre por aqui. O app empacotado (etapa 6) já leva tudo dentro."
  read -r -p "Aperte Enter para fechar."
  exit 1
fi

DADOS="$HOME/Library/Application Support/Revisor de Vídeos"
VENV="$DADOS/python"
if [ ! -x "$VENV/bin/python3" ]; then
  echo "Primeira vez: preparando o Python do Revisor (só uma vez, alguns minutos)…"
  mkdir -p "$DADOS"
  python3 -m venv "$VENV" || { read -r -p "Não deu para criar o Python do Revisor. Enter para fechar."; exit 1; }
  "$VENV/bin/python3" -m pip install --quiet --upgrade pip
  "$VENV/bin/python3" -m pip install --quiet -r requirements.txt || { read -r -p "Falhou ao instalar os pacotes. Enter para fechar."; exit 1; }
fi

echo "Abrindo o Revisor de Vídeos… (para fechar o app, feche esta janela)"
exec "$VENV/bin/python3" -m revisor
