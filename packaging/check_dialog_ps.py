"""Montagem no Windows: escreve os scripts da janela de escolher pasta/arquivo para o PowerShell
conferir (sintaxe) e o pedaço que traz a janela para a frente (Add-Type) para ele compilar.
A janela em si não abre na máquina do GitHub (não tem ninguém para clicar)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from revisor import dialogs  # noqa: E402

out = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
bom = "utf-8-sig"            # o Windows PowerShell 5.1 precisa do BOM para ler acentos
(out / "dlg_pasta.ps1").write_text(dialogs.ps_folder_script("Escolha a pasta dos vídeos", "C:\\Users\\Ana's"), encoding=bom)
(out / "dlg_arquivo.ps1").write_text(dialogs.ps_file_script("Escolha a vinheta", None, "Vídeos|*.mp4;*.mov|Todos|*.*"),
                                     encoding=bom)
s = dialogs._PS_FRONT
a = s.index("Add-Type -Namespace")
b = s.index("'@", a) + 2
(out / "dlg_addtype.ps1").write_text(s[a:b] + "\n[RevisorVideos.Janela]::GetCurrentThreadId() | Out-Null\n"
                                     "Write-Output 'Add-Type ok'\n", encoding=bom)
print("scripts escritos em", out.resolve())
