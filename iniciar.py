"""Inicia o sistema da Fascinação Noivas e abre o navegador.

É o ponto de entrada tanto em desenvolvimento (python iniciar.py) quanto no executável
FascinacaoNoivas.exe gerado pelo PyInstaller. No executável não há janela de terminal:
o sistema fica rodando em segundo plano e é encerrado pelo botão "Encerrar o sistema"
em Configurações (ou ao desligar o computador).

Opções:
  --criar-atalho   cria o atalho "Fascinação Noivas" na área de trabalho e sai (usado pelo instalar.bat)
"""
import os
import socket
import subprocess
import sys
import threading
import traceback
import urllib.request
import webbrowser

HOST = "127.0.0.1"
PORTA_PADRAO = int(os.environ.get("FASCINACAO_PORTA", "5780"))
MARCADOR = b"fascinacao-noivas"
EXECUTAVEL = getattr(sys, "frozen", False)
TITULO = "Fascinação Noivas"


def aviso_windows(mensagem, erro=False):
    """Janela de mensagem do Windows (o executável não tem terminal para mostrar erros)."""
    if os.name == "nt":
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, mensagem, TITULO, 0x10 if erro else 0x40)
    else:
        print(mensagem)


def preparar_log(pasta_dados):
    """Sem terminal, a saída vai para dados\\sistema.log (reiniciado se passar de 2 MB)."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    caminho = os.path.join(pasta_dados, "sistema.log")
    modo = "w" if os.path.exists(caminho) and os.path.getsize(caminho) > 2 * 1024 * 1024 else "a"
    arquivo = open(caminho, modo, encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = arquivo


def criar_atalho():
    """Atalho "Fascinação Noivas" na área de trabalho apontando para este executável."""
    exe = sys.executable.replace("'", "''")
    pasta = os.path.dirname(sys.executable).replace("'", "''")
    comando = (
        "$d=[Environment]::GetFolderPath('Desktop');"
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $d 'Fascinação Noivas.lnk'));"
        f"$s.TargetPath='{exe}';$s.WorkingDirectory='{pasta}';$s.IconLocation='{exe},0';"
        "$s.Description='Sistema de aluguel da Fascinação Noivas';$s.Save()"
    )
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", comando],
                   check=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def ja_esta_rodando(porta):
    try:
        with urllib.request.urlopen(f"http://{HOST}:{porta}/saude", timeout=1) as r:
            return r.read() == MARCADOR
    except OSError:
        return False


def porta_disponivel(porta):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((HOST, porta))
            return True
        except OSError:
            return False


def main():
    if "--criar-atalho" in sys.argv:
        criar_atalho()
        return

    if ja_esta_rodando(PORTA_PADRAO):
        # O sistema já está aberto: só abre o navegador nele.
        webbrowser.open(f"http://{HOST}:{PORTA_PADRAO}/")
        return

    from werkzeug.serving import make_server

    from app import NOME_LOJA, create_app, pasta_de_dados
    from app.backup import backup_na_abertura

    preparar_log(pasta_de_dados())

    porta = next(p for p in range(PORTA_PADRAO, PORTA_PADRAO + 50) if porta_disponivel(p))
    app = create_app()
    try:
        copia, aviso = backup_na_abertura(app.config["DATABASE"])
    except Exception as e:  # o sistema abre mesmo que o backup falhe
        copia, aviso = None, f"Backup não realizado: {e}"

    servidor = make_server(HOST, porta, app, threaded=True)
    # Permite o botão "Encerrar o sistema" em Configurações.
    app.config["ENCERRAR"] = lambda: threading.Timer(0.8, servidor.shutdown).start()
    endereco = f"http://{HOST}:{porta}/"

    print("=" * 60)
    print(f"  {NOME_LOJA}")
    print("=" * 60)
    print(f"  Sistema no ar em {endereco}")
    print(f"  Banco de dados: {app.config['DATABASE']}")
    if copia:
        print(f"  Backup salvo em: {copia}")
    if aviso:
        print(f"  ATENÇÃO: {aviso}")
    if not EXECUTAVEL:
        print()
        print("  Para encerrar, feche esta janela (ou pressione Ctrl+C).")
    print("=" * 60, flush=True)

    if not os.environ.get("FASCINACAO_SEM_NAVEGADOR"):
        threading.Timer(1.0, webbrowser.open, args=(endereco,)).start()
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        servidor.server_close()
        print("  Sistema encerrado.", flush=True)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        detalhe = traceback.format_exc()
        try:
            print(detalhe, flush=True)
        except Exception:
            pass
        aviso_windows("Não foi possível abrir o sistema.\n\n" + detalhe.strip().splitlines()[-1] +
                      "\n\nSe o problema continuar, veja o arquivo sistema.log na pasta de dados.", erro=True)
        sys.exit(1)
