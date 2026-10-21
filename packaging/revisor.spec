# PyInstaller: monta o "Revisor de Videos" (Mac: .app; Windows: pasta com o .exe).
#   python packaging/build_deps.py        (antes: bin/ e models/)
#   pyinstaller --noconfirm packaging/revisor.spec
# Resultado em dist/.
import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).resolve().parent
sys.path.insert(0, str(ROOT))
from revisor import __version__  # noqa: E402

IS_MAC = sys.platform == "darwin"
IS_WIN = os.name == "nt"
NAME = "Revisor de Videos"

datas = [
    (str(ROOT / "revisor" / "ui"), "revisor/ui"),
    (str(ROOT / "revisor" / "data" / "tessdata"), "revisor/data/tessdata"),
    (str(ROOT / "revisor" / "data" / "dict"), "revisor/data/dict"),
]
datas += collect_data_files("spylls")
model = ROOT / "models" / "ggml-small-q5_1.bin"
if model.is_file():
    datas.append((str(model), "models"))
else:
    print("AVISO: sem o modelo do Whisper (a fala fica desligada neste pacote)")

binaries = []
for p in sorted((ROOT / "bin").glob("*")):
    if p.is_file() and not p.name.startswith("."):
        if p.suffix.lower() == ".txt":
            datas.append((str(p), "bin"))
        else:
            binaries.append((str(p), "bin"))

a = Analysis(
    [str(ROOT / "packaging" / "app_main.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=collect_submodules("revisor") + collect_submodules("spylls"),
    excludes=["tkinter", "matplotlib", "cv2", "pytest", "playwright", "IPython"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name=NAME,
    console=False,
    icon=str(ROOT / "packaging" / "icon" / ("icon.icns" if IS_MAC else "icon.ico")),
    upx=False,
)
extra = []
if IS_WIN:
    # mesma coisa com janela de terminal: para "revisor-terminal.exe diagnostico" e testes
    extra.append(EXE(pyz, a.scripts, [], exclude_binaries=True, name="revisor-terminal", console=True,
                     icon=str(ROOT / "packaging" / "icon" / "icon.ico"), upx=False))

coll = COLLECT(exe, *extra, a.binaries, a.datas, name=NAME, upx=False)

if IS_MAC:
    app = BUNDLE(
        coll,
        name=NAME + ".app",
        icon=str(ROOT / "packaging" / "icon" / "icon.icns"),
        bundle_identifier="br.pucminas.npd.revisor",
        version=__version__,
        info_plist={
            "CFBundleDisplayName": "Revisor de Vídeos",
            "CFBundleName": "Revisor de Vídeos",
            "CFBundleShortVersionString": __version__,
            "CFBundleVersion": __version__,
            "LSMinimumSystemVersion": "11.0",
            "LSUIElement": True,              # sem ícone no Dock: o app é a página no navegador
            "NSHighResolutionCapable": True,
            "NSDesktopFolderUsageDescription": "O Revisor de Vídeos lê as aulas da pasta que você escolher.",
            "NSDocumentsFolderUsageDescription": "O Revisor de Vídeos lê as aulas da pasta que você escolher.",
            "NSDownloadsFolderUsageDescription": "O Revisor de Vídeos lê as aulas e salva SRT e pacotes onde você escolher.",
            "NSRemovableVolumesUsageDescription": "O Revisor de Vídeos lê as aulas do disco externo que você escolher.",
            "NSNetworkVolumesUsageDescription": "O Revisor de Vídeos lê as aulas da pasta de rede que você escolher.",
            "NSAppleEventsUsageDescription": "O Revisor de Vídeos abre a janela para escolher a pasta das aulas.",
        },
    )
