"""Falas na placa de vídeo (pedido do JP, 22/10): no Windows o app usa o whisper-cli-vulkan primeiro e
volta para o processador se ele não abrir ou falhar. Aqui: leitura das mensagens do whisper, escolha da
placa (dedicada × integrada) e a volta para o processador com programas falsos."""
import os
import subprocess

import pytest

from conftest import ffmpeg
from revisor import speech

LOG_INTEGRADA = """whisper_backend_init_gpu: device 0: Vulkan0 (type: 2)
whisper_backend_init_gpu: found GPU device 0: Vulkan0 (type: 2, cnt: 0)
whisper_backend_init_gpu: using Vulkan0 backend
"""
LOG_DEDICADA = """whisper_backend_init_gpu: found GPU device 0: Vulkan0 (type: 2, cnt: 0)
whisper_backend_init_gpu: found GPU device 1: Vulkan1 (type: 1, cnt: 1)
whisper_backend_init_gpu: using Vulkan1 backend
"""


@pytest.fixture(autouse=True)
def limpo(monkeypatch):
    monkeypatch.setattr(speech, "_gpu_problem", None)
    monkeypatch.setattr(speech, "_gpu", {"dev": 0, "seen": {}, "done": False})
    monkeypatch.setattr(speech, "last_where", None)


def test_backend_of():
    assert speech.backend_of(LOG_INTEGRADA)["backend"] == "Vulkan"
    assert speech.backend_of(LOG_INTEGRADA)["gpu_type"] == 2
    assert speech.backend_of(LOG_DEDICADA, 1)["gpu_type"] == 1
    w = speech.backend_of("whisper_backend_init_gpu: no GPU found\n")
    assert w["backend"] == "CPU" and w["no_gpu"]
    m = speech.backend_of("ggml_metal_device_init: GPU name:   Apple M1 Max\nwhisper_backend_init_gpu: using MTL0 backend\n")
    assert m["backend"] == "Metal" and m["gpu"] == "Apple M1 Max"
    assert speech.where_text("Vulkan", "NVIDIA GeForce RTX 3060") == "placa de vídeo (NVIDIA GeForce RTX 3060)"
    assert speech.where_text("CPU", None) == "processador"


def test_prefere_placa_dedicada():
    # 1º pedaço caiu na integrada (Intel): o próximo tenta a placa seguinte
    speech._note_gpu(speech.backend_of(LOG_INTEGRADA, 0))
    assert speech._gpu["dev"] == 1 and not speech._gpu["done"]
    # a seguinte é a dedicada (Nvidia): fica nela
    speech._note_gpu(speech.backend_of(LOG_DEDICADA, 1))
    assert speech._gpu == {"dev": 1, "seen": {0: 2, 1: 1}, "done": True}


def test_so_integrada():
    speech._note_gpu(speech.backend_of(LOG_INTEGRADA, 0))
    assert speech._gpu["dev"] == 1
    # não existe placa 1: volta para a integrada e para de procurar
    speech._note_gpu(speech.backend_of("whisper_backend_init_gpu: no GPU found\n", 1))
    assert speech._gpu["dev"] == 0 and speech._gpu["done"]
    assert speech.gpu_problem() is None


def test_vulkan_sem_placa():
    speech._note_gpu(speech.backend_of("ggml_vulkan: No devices found.\nwhisper_backend_init_gpu: no GPU found\n", 0))
    assert speech.gpu_problem()        # daqui em diante só o processador


def _fake(path, body):
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(0o755)
    return str(path)


@pytest.mark.skipif(os.name == "nt", reason="programas falsos em shell")
def test_vulkan_falha_e_usa_processador(tmp_path, monkeypatch):
    ok_body = ('out=""; while [ $# -gt 0 ]; do [ "$1" = "-of" ] && out="$2"; shift; done\n'
               'echo \'{"transcription": []}\' > "$out.json"\n'
               'echo "whisper_backend_init_gpu: no GPU found" >&2\n')
    gpu = _fake(tmp_path / "whisper-cli-vulkan", 'echo "vk: device lost" >&2; exit 3\n')
    cpu = _fake(tmp_path / "whisper-cli", ok_body)
    model = tmp_path / "m.bin"
    model.write_bytes(b"x")
    monkeypatch.setattr(speech, "find_gpu_cli", lambda: gpu if speech._gpu_problem is None else None)
    monkeypatch.setattr(speech, "find_cli", lambda: cpu)
    vid = tmp_path / "a.mp4"
    subprocess.run([ffmpeg(), "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=2",
                    "-c:a", "aac", str(vid)], check=True)
    r = speech.transcribe_chunk(str(vid), 0.0, 2.0, model=str(model))
    assert r["backend"] == "CPU"
    assert "device lost" in speech.gpu_problem()
    assert speech.whisper_clis() == [cpu]            # o resto da sessão vai direto no processador
    ev = speech.engine_view()
    assert ev["text"] == "processador" and ev["problem"]
