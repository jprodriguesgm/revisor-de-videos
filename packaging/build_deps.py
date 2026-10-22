"""Prepara os programas que vão DENTRO do app (etapa 6).

    python packaging/build_deps.py                 # tudo
    python packaging/build_deps.py tesseract whisper

Resultado na raiz do repositório (fora do git):
    bin/      ffmpeg, ffprobe, tesseract, whisper-cli  (+ DLLs do FFmpeg no Windows)
    models/   ggml-small-q5_1.bin (Whisper "small", 190 MB)

Como cada um é feito:
- Tesseract: montado do código-fonte com a Leptonica SEM bibliotecas de imagem (o app
  manda as imagens em PGM). Fica um executável só, sem dependências.
- whisper-cli: montado do código-fonte (Mac com Metal = placa de vídeo do M1; Windows com
  AVX2 no processador). Um executável só. No Windows vai também o whisper-cli-vulkan (placa
  de vídeo pelo Vulkan: Nvidia, Intel, AMD), que o app usa primeiro; precisa do Vulkan SDK na
  montagem (variável VULKAN_SDK; o GitHub Actions instala) e do driver da placa no computador.
- FFmpeg: no Mac, montado do código-fonte com libx264 (estática) e VideoToolbox, sem
  bibliotecas de fora do sistema. No Windows, a versão pronta do BtbN (GPL, com libx264).
  No Linux (só testes), copia o FFmpeg do sistema.
- Modelo do Whisper: baixado do Hugging Face.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "build" / "deps"
BIN = ROOT / "bin"
MODELS = ROOT / "models"

LEPTONICA_TAG = "1.87.0"
TESSERACT_TAG = "5.5.3"
WHISPER_TAG = "v1.9.5"
FFMPEG_TAG = "n8.1.3"
X264_BRANCH = "stable"
MODEL_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small-q5_1.bin"
MODEL_NAME = "ggml-small-q5_1.bin"

IS_WIN = os.name == "nt"
IS_MAC = sys.platform == "darwin"
EXE = ".exe" if IS_WIN else ""
JOBS = str(os.cpu_count() or 4)
MAC_MIN = "11.0"


def log(msg: str):
    print(f"\n=== {msg}", flush=True)


def run(cmd: list[str], cwd: Path | None = None, env: dict | None = None):
    print("+", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], cwd=cwd, env=env, check=True)


def clone(repo: str, tag: str, dest: Path):
    if (dest / ".git").is_dir():
        return
    if dest.exists():
        shutil.rmtree(dest)
    run(["git", "clone", "--depth", "1", "-b", tag, f"https://github.com/{repo}", dest])


def download(url: str, dest: Path):
    if dest.is_file() and dest.stat().st_size > 0:
        return
    print(f"baixando {url}", flush=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "revisor-build"})
    with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as fh:
        shutil.copyfileobj(r, fh, 1 << 20)
    tmp.replace(dest)


def cmake_common() -> list[str]:
    args = ["-DCMAKE_BUILD_TYPE=Release", "-DBUILD_SHARED_LIBS=OFF"]
    if IS_MAC:
        args += [f"-DCMAKE_OSX_DEPLOYMENT_TARGET={MAC_MIN}", "-DCMAKE_OSX_ARCHITECTURES=arm64"]
    if IS_WIN:
        # runtime do C++ dentro do executável (não depende do "Visual C++ Redistributable")
        args += ["-DCMAKE_POLICY_DEFAULT_CMP0091=NEW", "-DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded"]
    return args


def cmake_build(src: Path, build: Path, args: list[str], install: Path | None = None, target: str | None = None):
    cfg = ["cmake", "-S", src, "-B", build] + cmake_common() + args
    if install:
        cfg.append(f"-DCMAKE_INSTALL_PREFIX={install}")
    run(cfg)
    b = ["cmake", "--build", build, "--config", "Release", "--parallel", JOBS]
    if target:
        b += ["--target", target]
    run(b)
    if install:
        run(["cmake", "--install", build, "--config", "Release"])


def find_file(base: Path, name: str) -> Path:
    for p in base.rglob(name):
        if p.is_file():
            return p
    raise FileNotFoundError(f"{name} não encontrado em {base}")


# ---------------------------------------------------------------- Tesseract

def build_tesseract():
    log("Leptonica + Tesseract")
    prefix = WORK / "prefix"
    lep = WORK / "leptonica"
    clone("DanBloomberg/leptonica", LEPTONICA_TAG, lep)
    off = [f"-D{o}=OFF" for o in ("ENABLE_ZLIB", "ENABLE_PNG", "ENABLE_GIF", "ENABLE_JPEG", "ENABLE_TIFF",
                                  "ENABLE_WEBP", "ENABLE_OPENJPEG", "BUILD_PROG", "SW_BUILD")]
    cmake_build(lep, WORK / "leptonica-build", off, install=prefix)

    tes = WORK / "tesseract"
    clone("tesseract-ocr/tesseract", TESSERACT_TAG, tes)
    lep_cfg = next(prefix.rglob("LeptonicaConfig.cmake")).parent
    args = [f"-DLeptonica_DIR={lep_cfg}", "-DBUILD_TRAINING_TOOLS=OFF", "-DBUILD_TESTS=OFF",
            "-DDISABLE_ARCHIVE=ON", "-DDISABLE_CURL=ON", "-DDISABLE_TIFF=ON", "-DGRAPHICS_DISABLED=ON",
            "-DOPENMP_BUILD=OFF", "-DENABLE_NATIVE=OFF", "-DINSTALL_CONFIGS=OFF", "-DENABLE_CCACHE=OFF",
            "-DSW_BUILD=OFF", f"-DCMAKE_PREFIX_PATH={prefix}"]
    cmake_build(tes, WORK / "tesseract-build", args, target="tesseract")
    exe = find_file(WORK / "tesseract-build", "tesseract" + EXE)
    put(exe, "tesseract" + EXE)


# ---------------------------------------------------------------- Whisper

def build_whisper():
    log("whisper.cpp")
    src = WORK / "whisper.cpp"
    clone("ggml-org/whisper.cpp", WHISPER_TAG, src)
    args = ["-DWHISPER_BUILD_TESTS=OFF", "-DWHISPER_BUILD_SERVER=OFF", "-DWHISPER_BUILD_EXAMPLES=ON",
            "-DWHISPER_SDL2=OFF", "-DWHISPER_CURL=OFF", "-DGGML_NATIVE=OFF", "-DGGML_OPENMP=OFF"]
    if IS_MAC:
        args += ["-DGGML_METAL=ON", "-DGGML_METAL_EMBED_LIBRARY=ON", "-DGGML_BLAS=ON"]
    cmake_build(src, WORK / "whisper-build", args, target="whisper-cli")
    put(find_file(WORK / "whisper-build", "whisper-cli" + EXE), "whisper-cli" + EXE)
    if IS_WIN:
        # placa de vídeo pelo Vulkan (pedido do JP, 22/10): um segundo executável; o de processador fica
        # como reserva para máquina sem Vulkan
        if not os.environ.get("VULKAN_SDK"):
            if os.environ.get("REVISOR_SEM_VULKAN") == "1":
                print("(sem Vulkan SDK: whisper-cli-vulkan não montado)")
                return
            raise SystemExit("Vulkan SDK não encontrado (VULKAN_SDK). Instale o SDK ou use REVISOR_SEM_VULKAN=1.")
        cmake_build(src, WORK / "whisper-build-vulkan", args + ["-DGGML_VULKAN=ON"], target="whisper-cli")
        put(find_file(WORK / "whisper-build-vulkan", "whisper-cli" + EXE), "whisper-cli-vulkan" + EXE)


# ---------------------------------------------------------------- FFmpeg

def build_ffmpeg():
    log("FFmpeg")
    if IS_WIN:
        return ffmpeg_windows()
    if not IS_MAC:
        for name in ("ffmpeg", "ffprobe"):
            p = shutil.which(name)
            if not p:
                raise SystemExit(f"{name} não está no sistema (Linux: só para testar)")
            put(Path(p), name)
        return
    src = WORK / f"ffmpeg-{FFMPEG_TAG}"
    if not (src / "configure").is_file():
        tgz = WORK / f"ffmpeg-{FFMPEG_TAG}.tar.gz"
        download(f"https://github.com/FFmpeg/FFmpeg/archive/refs/tags/{FFMPEG_TAG}.tar.gz", tgz)
        with tarfile.open(tgz) as t:
            t.extractall(WORK)
        extracted = WORK / f"FFmpeg-{FFMPEG_TAG}"
        if extracted.exists():
            extracted.rename(src)
    (src / "VERSION").write_text(FFMPEG_TAG.lstrip("n"))   # senão o FFmpeg pega o "git" do repositório
    flags = f"-mmacosx-version-min={MAC_MIN}"
    x264 = build_x264()
    env = dict(os.environ, PKG_CONFIG_PATH=str(x264 / "lib" / "pkgconfig"))
    run(["./configure", f"--prefix={WORK / 'ffmpeg-prefix'}", "--disable-shared", "--enable-static",
         "--disable-doc", "--disable-ffplay", "--disable-network", "--disable-debug",
         "--disable-autodetect", "--enable-videotoolbox", "--enable-audiotoolbox", "--enable-zlib",
         "--enable-pthreads", "--arch=arm64", "--enable-gpl", "--enable-libx264", "--pkg-config-flags=--static",
         f"--extra-cflags={flags} -I{x264 / 'include'}", f"--extra-ldflags={flags} -L{x264 / 'lib'}"],
        cwd=src, env=env)
    run(["make", f"-j{JOBS}", "ffmpeg", "ffprobe"], cwd=src)
    for name in ("ffmpeg", "ffprobe"):
        put(src / name, name)


def build_x264() -> Path:
    """libx264 estática (Mac): o VideoToolbox não funciona em máquina virtual e o libx264 dá o
    mesmo resultado nos dois sistemas. Fica dentro do FFmpeg (GPL, como o do Windows)."""
    prefix = WORK / "x264-prefix"
    if (prefix / "lib" / "libx264.a").is_file():
        return prefix
    src = WORK / "x264"
    if not (src / "configure").is_file():
        try:
            run(["git", "clone", "--depth", "1", "-b", X264_BRANCH, "https://code.videolan.org/videolan/x264.git", src])
        except subprocess.CalledProcessError:
            shutil.rmtree(src, ignore_errors=True)
            run(["git", "clone", "--depth", "1", "-b", X264_BRANCH, "https://github.com/mirror/x264", src])
    flags = f"-mmacosx-version-min={MAC_MIN}"
    run(["./configure", f"--prefix={prefix}", "--enable-static", "--disable-cli", "--enable-pic",
         f"--extra-cflags={flags}", f"--extra-ldflags={flags}"], cwd=src)
    run(["make", f"-j{JOBS}"], cwd=src)
    run(["make", "install"], cwd=src)
    return prefix


def ffmpeg_windows():
    api = "https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/latest"
    req = urllib.request.Request(api, headers={"User-Agent": "revisor-build"})
    tok = os.environ.get("GITHUB_TOKEN")
    if tok:
        req.add_header("Authorization", f"Bearer {tok}")
    with urllib.request.urlopen(req, timeout=60) as r:
        rel = json.load(r)
    # versão estável numerada (não a "master"), GPL (com libx264), compartilhada (DLLs uma vez só)
    cands = [a for a in rel["assets"] if a["name"].endswith(".zip") and "win64-gpl-shared-" in a["name"]
             and a["name"].startswith("ffmpeg-n")]
    if not cands:
        raise SystemExit("versão do FFmpeg para Windows não encontrada no BtbN")

    def ver(a):
        v = a["name"].rsplit("-", 1)[-1][:-4]
        return tuple(int(x) for x in v.split(".") if x.isdigit())
    asset = max(cands, key=ver)
    z = WORK / asset["name"]
    download(asset["browser_download_url"], z)
    out = WORK / "ffmpeg-win"
    if out.exists():
        shutil.rmtree(out)
    with zipfile.ZipFile(z) as zf:
        zf.extractall(out)
    binsrc = next(out.rglob("ffmpeg.exe")).parent
    for p in binsrc.iterdir():
        if p.suffix.lower() == ".dll" or p.name in ("ffmpeg.exe", "ffprobe.exe"):
            put(p, p.name)
    lic = next(out.rglob("LICENSE.txt"), None)
    if lic:
        put(lic, "LICENSE_FFmpeg.txt")
    print("FFmpeg:", asset["name"])


# ---------------------------------------------------------------- modelo

def get_model():
    log("Modelo do Whisper")
    MODELS.mkdir(exist_ok=True)
    dest = MODELS / MODEL_NAME
    download(MODEL_URL, dest)
    size = dest.stat().st_size
    if size < 150_000_000:
        dest.unlink()
        raise SystemExit(f"modelo incompleto ({size} bytes)")
    print(f"{MODEL_NAME}: {size / 1e6:.0f} MB")


# ---------------------------------------------------------------- comum

def put(src: Path, name: str):
    BIN.mkdir(exist_ok=True)
    dst = BIN / name
    shutil.copy2(src, dst)
    if not IS_WIN:
        dst.chmod(0o755)
    print(f"-> bin/{name} ({dst.stat().st_size / 1e6:.1f} MB)")


def check():
    """Confere que cada programa abre e não depende de bibliotecas de fora."""
    log("Conferindo bin/")
    for name in ("ffmpeg", "ffprobe", "tesseract", "whisper-cli"):
        p = BIN / (name + EXE)
        if not p.is_file():
            print(f"FALTA: {name}")
            continue
        arg = "--version" if name == "tesseract" else ("-h" if name == "whisper-cli" else "-version")
        r = subprocess.run([str(p), arg], capture_output=True, text=True, errors="replace")
        first = (r.stdout or r.stderr).strip().splitlines()[:1]
        print(f"{name}: {first[0] if first else '(sem saída)'}  [código {r.returncode}]")
        if IS_MAC:
            libs = subprocess.run(["otool", "-L", str(p)], capture_output=True, text=True).stdout
            bad = [ln.strip() for ln in libs.splitlines()[1:]
                   if ln.strip() and not ln.strip().startswith(("/usr/lib/", "/System/"))]
            if bad:
                raise SystemExit(f"{name} depende de bibliotecas de fora: {bad}")
        elif not IS_WIN and name in ("tesseract", "whisper-cli"):
            print(subprocess.run(["ldd", str(p)], capture_output=True, text=True).stdout)
    if IS_WIN:
        p = BIN / "whisper-cli-vulkan.exe"
        if not p.is_file():
            raise SystemExit("FALTA: whisper-cli-vulkan.exe")
        # a máquina do GitHub não tem placa de vídeo; só confere que o programa existe e abre
        dll = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "vulkan-1.dll"
        if dll.is_file():
            import ctypes
            ctypes.windll.kernel32.SetErrorMode(0x0001 | 0x0002 | 0x8000)   # sem janelas de erro do sistema
            r = subprocess.run([str(p), "-h"], capture_output=True, text=True, errors="replace", timeout=60)
            print(f"whisper-cli-vulkan: {p.stat().st_size / 1e6:.1f} MB  [código {r.returncode}]")
        else:
            print(f"whisper-cli-vulkan: {p.stat().st_size / 1e6:.1f} MB  (esta máquina não tem vulkan-1.dll)")
    if IS_MAC:
        enc = subprocess.run([str(BIN / "ffmpeg"), "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
        for e in ("libx264", "h264_videotoolbox"):
            if e not in enc:
                raise SystemExit(f"FFmpeg sem {e}")


STEPS = {"tesseract": build_tesseract, "whisper": build_whisper, "ffmpeg": build_ffmpeg, "model": get_model}


def main(argv: list[str]):
    WORK.mkdir(parents=True, exist_ok=True)
    wanted = argv or list(STEPS)
    for w in wanted:
        if w == "check":
            continue
        STEPS[w]()
    check()
    print(f"\npronto ({platform.system()} {platform.machine()})")


if __name__ == "__main__":
    main(sys.argv[1:])
