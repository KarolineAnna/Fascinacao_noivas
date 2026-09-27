"""Cópias de segurança do banco de dados."""
import os
import sqlite3
from datetime import datetime

from .db import gravar_config, ler_config

PREFIXO = "fascinacao-"
MANTER = 30


def pasta_padrao(banco):
    return os.path.join(os.path.dirname(banco), "backups")


def pasta_backup(banco):
    conn = sqlite3.connect(banco)
    try:
        return ler_config(conn, "pasta_backup") or pasta_padrao(banco)
    finally:
        conn.close()


def listar(pasta):
    if not os.path.isdir(pasta):
        return []
    arquivos = [os.path.join(pasta, n) for n in os.listdir(pasta)
                if n.startswith(PREFIXO) and n.endswith(".db")]
    return sorted(arquivos, key=os.path.getmtime, reverse=True)


def fazer_backup(banco, pasta=None):
    """Copia o banco (com segurança, mesmo em uso) e mantém apenas as últimas 30 cópias."""
    pasta = pasta or pasta_backup(banco)
    os.makedirs(pasta, exist_ok=True)
    base = os.path.join(pasta, f"{PREFIXO}{datetime.now():%Y-%m-%d_%H-%M-%S}")
    destino, n = base + ".db", 2
    while os.path.exists(destino):
        destino, n = f"{base}-{n}.db", n + 1

    origem = sqlite3.connect(banco)
    copia = sqlite3.connect(destino)
    try:
        origem.backup(copia)
    finally:
        copia.close()
        origem.close()

    for antigo in listar(pasta)[MANTER:]:
        try:
            os.remove(antigo)
        except OSError:
            pass
    return destino


def backup_na_abertura(banco):
    """Faz o backup ao abrir o sistema. Se a pasta escolhida estiver indisponível
    (ex.: pendrive desconectado), salva na pasta padrão e registra o aviso."""
    pasta = pasta_backup(banco)
    erro = ""
    try:
        destino = fazer_backup(banco, pasta)
    except OSError as e:
        erro = f"Não foi possível salvar em “{pasta}” ({e.strerror or e}). A cópia foi salva na pasta padrão."
        destino = fazer_backup(banco, pasta_padrao(banco))

    conn = sqlite3.connect(banco)
    try:
        gravar_config(conn, "ultimo_backup", destino)
        gravar_config(conn, "erro_backup", erro)
    finally:
        conn.close()
    return destino, erro
