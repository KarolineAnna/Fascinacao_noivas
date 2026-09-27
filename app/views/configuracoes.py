import os
import sqlite3
from datetime import datetime

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for

from .. import backup, contrato
from ..util import centavos_para_campo, reais_para_centavos
from ..db import categorias, get_db, gravar_config, ler_config

GRUPOS = {"financeiro": "Categorias do financeiro", "venda": "Marcas / categorias de produtos à venda"}

bp = Blueprint("configuracoes", __name__, url_prefix="/configuracoes")


def pasta_gravavel(pasta):
    """Cria a pasta se preciso e confere se é possível gravar nela."""
    try:
        os.makedirs(pasta, exist_ok=True)
        teste = os.path.join(pasta, ".teste-fascinacao")
        with open(teste, "w") as f:
            f.write("ok")
        os.remove(teste)
        return True
    except OSError:
        return False


def definir_pasta(pasta):
    pasta = os.path.abspath(os.path.expanduser(pasta.strip().strip('"')))
    if not pasta_gravavel(pasta):
        flash(f"Não foi possível usar a pasta “{pasta}”. Confira se ela existe e se há permissão de gravação.", "erro")
        return
    gravar_config(get_db(), "pasta_backup", pasta)
    flash(f"Os backups agora serão salvos em “{pasta}”.", "sucesso")


@bp.route("/")
def pagina():
    db = get_db()
    banco = current_app.config["DATABASE"]
    pasta = ler_config(db, "pasta_backup") or backup.pasta_padrao(banco)
    copias = [{"nome": os.path.basename(p),
               "data": datetime.fromtimestamp(os.path.getmtime(p)),
               "tamanho_kb": max(1, os.path.getsize(p) // 1024)}
              for p in backup.listar(pasta)]
    formas = db.execute("SELECT * FROM formas_pagamento ORDER BY ordem, id").fetchall()
    return render_template(
        "configuracoes.html", pasta=pasta, pasta_padrao=backup.pasta_padrao(banco),
        personalizada=bool(ler_config(db, "pasta_backup")), copias=copias, manter=backup.MANTER,
        erro_backup=ler_config(db, "erro_backup", ""), formas=formas, banco=banco,
        pode_encerrar=bool(current_app.config.get("ENCERRAR")),
        grupos={g: categorias(db, g) for g in GRUPOS}, nomes_grupos=GRUPOS,
        **dados_contrato(db),
    )


@bp.route("/pasta", methods=["POST"])
def salvar_pasta():
    if request.form.get("acao") == "padrao":
        db = get_db()
        db.execute("DELETE FROM configuracoes WHERE chave = 'pasta_backup'")
        db.commit()
        flash("Os backups voltaram a ser salvos na pasta padrão.", "sucesso")
    elif request.form.get("pasta", "").strip():
        definir_pasta(request.form["pasta"])
    else:
        flash("Informe o caminho da pasta.", "erro")
    return redirect(url_for("configuracoes.pagina"))


@bp.route("/pasta/escolher", methods=["POST"])
def escolher_pasta():
    """Abre a janela do Windows para escolher a pasta (o sistema roda no próprio computador)."""
    try:
        import tkinter
        from tkinter import filedialog

        raiz = tkinter.Tk()
        raiz.withdraw()
        raiz.attributes("-topmost", True)
        pasta = filedialog.askdirectory(parent=raiz, title="Escolha a pasta dos backups")
        raiz.destroy()
    except Exception:
        flash("Não foi possível abrir a janela de seleção. Digite o caminho da pasta no campo.", "erro")
        return redirect(url_for("configuracoes.pagina"))
    if pasta:
        definir_pasta(pasta)
    return redirect(url_for("configuracoes.pagina"))


@bp.route("/backup", methods=["POST"])
def backup_agora():
    banco = current_app.config["DATABASE"]
    try:
        destino = backup.fazer_backup(banco)
        gravar_config(get_db(), "erro_backup", "")
        flash(f"Backup criado: {os.path.basename(destino)}", "sucesso")
    except OSError as e:
        flash(f"Não foi possível criar o backup: {e.strerror or e}", "erro")
    return redirect(url_for("configuracoes.pagina"))


@bp.route("/encerrar", methods=["POST"])
def encerrar():
    """Encerra o servidor (o executável roda sem janela, então não há outra forma de fechá-lo)."""
    encerrar_servidor = current_app.config.get("ENCERRAR")
    if not encerrar_servidor:
        flash("Em desenvolvimento, encerre o sistema fechando a janela do terminal.", "info")
        return redirect(url_for("configuracoes.pagina"))
    encerrar_servidor()
    return render_template("encerrado.html")


def dados_contrato(db):
    tipo, valor = contrato.config_multa(db)
    campo = (f"{valor / 100:.2f}".rstrip("0").rstrip(".").replace(".", ",") if tipo == "percentual"
             else centavos_para_campo(valor))
    return {"multa_tipos": contrato.MULTA_TIPOS, "multa_tipo": tipo, "multa_valor_campo": campo,
            "termo_texto": ler_config(db, "termo_texto") or contrato.TERMO_PADRAO}


@bp.route("/contrato", methods=["POST"])
def salvar_contrato():
    db = get_db()
    if request.form.get("acao") == "padrao":
        db.execute("DELETE FROM configuracoes WHERE chave = 'termo_texto'")
        db.commit()
        flash("Texto do termo restaurado para o padrão.", "sucesso")
        return redirect(url_for("configuracoes.pagina") + "#contrato")
    tipo = request.form.get("multa_tipo", "percentual")
    valor = reais_para_centavos(request.form.get("multa_valor", ""))   # 10 -> 1000 = 10% ou R$ 10,00
    if tipo not in contrato.MULTA_TIPOS or valor is None:
        flash("Informe um valor de multa válido (ex.: 10 ou 50,00).", "erro")
        return redirect(url_for("configuracoes.pagina") + "#contrato")
    if tipo == "percentual" and valor > 10000:
        flash("O percentual da multa não pode passar de 100% por dia.", "erro")
        return redirect(url_for("configuracoes.pagina") + "#contrato")
    gravar_config(db, "multa_tipo", tipo)
    gravar_config(db, "multa_valor", str(valor))
    texto = request.form.get("termo_texto", "").strip()
    if texto and texto != contrato.TERMO_PADRAO.strip():
        gravar_config(db, "termo_texto", texto)
    else:
        db.execute("DELETE FROM configuracoes WHERE chave = 'termo_texto'")
        db.commit()
    flash("Contrato e multa salvos.", "sucesso")
    return redirect(url_for("configuracoes.pagina") + "#contrato")


@bp.route("/categorias", methods=["POST"])
def adicionar_categoria():
    grupo = request.form.get("grupo", "")
    nome = request.form.get("nome", "").strip()
    if grupo not in GRUPOS or not nome:
        flash("Informe o nome da categoria.", "erro")
    else:
        db = get_db()
        try:
            ordem = db.execute("SELECT COALESCE(MAX(ordem), 0) + 1 FROM categorias WHERE grupo = ?", (grupo,)).fetchone()[0]
            db.execute("INSERT INTO categorias (grupo, nome, ordem) VALUES (?, ?, ?)", (grupo, nome, ordem))
            db.commit()
            flash(f"Categoria “{nome}” adicionada.", "sucesso")
        except sqlite3.IntegrityError:
            flash(f"A categoria “{nome}” já existe.", "erro")
    return redirect(url_for("configuracoes.pagina") + f"#categorias-{grupo}")


@bp.route("/categorias/<int:categoria_id>/renomear", methods=["POST"])
def renomear_categoria(categoria_id):
    db = get_db()
    cat = db.execute("SELECT * FROM categorias WHERE id = ?", (categoria_id,)).fetchone()
    nome = request.form.get("nome", "").strip()
    if cat and nome and nome != cat["nome"]:
        try:
            db.execute("UPDATE categorias SET nome = ? WHERE id = ?", (nome, categoria_id))
            db.commit()
            flash(f"“{cat['nome']}” agora se chama “{nome}”.", "sucesso")
        except sqlite3.IntegrityError:
            flash(f"A categoria “{nome}” já existe.", "erro")
    return redirect(url_for("configuracoes.pagina") + (f"#categorias-{cat['grupo']}" if cat else ""))


@bp.route("/categorias/<int:categoria_id>/remover", methods=["POST"])
def remover_categoria(categoria_id):
    db = get_db()
    cat = db.execute("SELECT * FROM categorias WHERE id = ?", (categoria_id,)).fetchone()
    if cat:
        tabela = "lancamentos" if cat["grupo"] == "financeiro" else "produtos_venda"
        usos = db.execute(f"SELECT COUNT(*) FROM {tabela} WHERE categoria_id = ?", (categoria_id,)).fetchone()[0]
        if usos:
            coisa = "lançamento" if tabela == "lancamentos" else "produto"
            flash(f"“{cat['nome']}” está em uso em {usos} {coisa}{'s' if usos != 1 else ''}. "
                  "Renomeie a categoria ou troque a categoria desses itens antes de remover.", "erro")
        else:
            db.execute("DELETE FROM categorias WHERE id = ?", (categoria_id,))
            db.commit()
            flash(f"Categoria “{cat['nome']}” removida.", "info")
    return redirect(url_for("configuracoes.pagina") + (f"#categorias-{cat['grupo']}" if cat else ""))


@bp.route("/formas", methods=["POST"])
def adicionar_forma():
    nome = request.form.get("nome", "").strip()
    if not nome:
        flash("Informe o nome da forma de pagamento.", "erro")
    else:
        db = get_db()
        try:
            ordem = db.execute("SELECT COALESCE(MAX(ordem), 0) + 1 FROM formas_pagamento").fetchone()[0]
            db.execute("INSERT INTO formas_pagamento (nome, ordem) VALUES (?, ?)", (nome, ordem))
            db.commit()
            flash(f"Forma de pagamento “{nome}” adicionada.", "sucesso")
        except sqlite3.IntegrityError:
            flash(f"A forma de pagamento “{nome}” já existe.", "erro")
    return redirect(url_for("configuracoes.pagina") + "#formas")


@bp.route("/formas/<int:forma_id>/remover", methods=["POST"])
def remover_forma(forma_id):
    db = get_db()
    forma = db.execute("SELECT nome FROM formas_pagamento WHERE id = ?", (forma_id,)).fetchone()
    if forma:
        # As fichas guardam o nome, então o histórico e o financeiro continuam intactos.
        db.execute("DELETE FROM formas_pagamento WHERE id = ?", (forma_id,))
        db.commit()
        flash(f"“{forma['nome']}” removida. Fichas antigas mantêm essa forma registrada.", "info")
    return redirect(url_for("configuracoes.pagina") + "#formas")
