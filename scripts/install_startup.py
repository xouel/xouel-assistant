import os
from pathlib import Path
import win32com.client


def install_startup_shortcut() -> Path:
    root_dir = Path(__file__).resolve().parent.parent
    pythonw_exe = root_dir / ".venv" / "Scripts" / "pythonw.exe"
    launcher_script = root_dir / "scripts" / "launcher.pyw"

    startup_dir = Path(
        os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup")
    )
    startup_dir.mkdir(parents=True, exist_ok=True)
    lnk_path = startup_dir / "X-Assistant.lnk"

    shell = win32com.client.Dispatch("WScript.Shell")
    shortcut = shell.CreateShortCut(str(lnk_path))
    shortcut.TargetPath = str(pythonw_exe)
    shortcut.Arguments = f'"{launcher_script}"'
    shortcut.WorkingDirectory = str(root_dir)
    shortcut.Description = "X-Assistant — Assistente Local de IA e Produtividade"

    edge_exe = os.path.expandvars(
        r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
    )
    if os.path.isfile(edge_exe):
        shortcut.IconLocation = f"{edge_exe},0"

    shortcut.Save()
    return lnk_path


if __name__ == "__main__":
    path = install_startup_shortcut()
    print(f"[+] Atalho de inicialização criado com sucesso em:\n    {path}")

