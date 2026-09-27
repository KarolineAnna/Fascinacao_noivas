"""Vendas de produtos (Natura, Avon, mel...), separadas do aluguel.

As vendas entram no Financeiro como entradas de origem "Venda" (view v_movimentos) e só
podem ser alteradas aqui."""
from datetime import date

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from ..db import categorias, formas_de_pagamento, get_db
from ..util import centavos_para_campo, formatar_cpf, parse_data, reais_para_centavos
from .financeiro import periodo_escolhido

bp = Blueprint("vendas", __name__, url_prefix="/vendas")


# --- Produtos à venda ----------------------------------------------------------------

def buscar_produto(produto_id):
    p = get_db().execute("SELECT * FROM produtos_venda WHERE id = ?", (produto_id,)).fetchone()
    if p is None:
        abort(404)
    return p


@bp.route("/produtos/")
def produtos():
    db = get_db()
    q = request.args.get("q", "").strip()
    categoria = request.args.get("categoria", "")
    inativos = request.args.get("inativos") == "1"
    sql = """SELECT p.*, c.nome AS categoria FROM produtos_venda p JOIN categorias c ON c.id = p.categoria_id
              WHERE 1 = 1"""
    params = []
    if not inativos:
        sql += " AND p.ativo = 1"
    if q:
        sql += " AND p.nome LIKE ?"
        params.append(f"%{q}%")
    if categoria.isdigit():
        sql += " AND p.categoria_id = ?"
        params.append(int(categoria))
    sql += " ORDER BY p.ativo DESC, c.ordem, p.nome COLLATE NOCASE"
    return render_template("vendas/produtos.html", produtos=db.execute(sql, params).fetchall(),
                           categorias=categorias(db, "venda"), q=q, categoria=categoria, inativos=inativos)


def formulario_produto(produto=None):
    db = get_db()
    if request.method == "POST":
        dados = {k: request.form.get(k, "").strip() for k in ("nome", "categoria_id", "preco")}
        erros = []
        if not dados["nome"]:
            erros.append("Informe o nome do produto.")
        if not db.execute("SELECT 1 FROM categorias WHERE grupo = 'venda' AND id = ?", (dados["categoria_id"] or 0,)).fetchone():
            erros.append("Escolha a marca/categoria.")
        preco = reais_para_centavos(dados["preco"])
        if preco is None:
            erros.append("Informe um preço de venda válido (ex.: 89,90).")
        if not erros:
            valores = (dados["nome"], int(dados["categoria_id"]), preco)
            if produto:
                db.execute("UPDATE produtos_venda SET nome = ?, categoria_id = ?, preco = ? WHERE id = ?",
                           (*valores, produto["id"]))
                flash("Produto atualizado.", "sucesso")
            else:
                db.execute("INSERT INTO produtos_venda (nome, categoria_id, preco) VALUES (?, ?, ?)", valores)
                flash(f"Produto “{dados['nome']}” cadastrado.", "sucesso")
            db.commit()
            return redirect(url_for("vendas.produtos"))
        for e in erros:
            flash(e, "erro")
    elif produto:
        dados = dict(produto, preco=centavos_para_campo(produto["preco"]), categoria_id=str(produto["categoria_id"]))
    else:
        dados = {"nome": "", "categoria_id": request.args.get("categoria", ""), "preco": ""}
    return render_template("vendas/produto_form.html", produto=produto, dados=dados,
                           categorias=categorias(db, "venda"))


@bp.route("/produtos/novo", methods=["GET", "POST"])
def novo_produto():
    return formulario_produto()


@bp.route("/produtos/<int:produto_id>/editar", methods=["GET", "POST"])
def editar_produto(produto_id):
    return formulario_produto(buscar_produto(produto_id))


@bp.route("/produtos/<int:produto_id>/excluir", methods=["POST"])
def excluir_produto(produto_id):
    p = buscar_produto(produto_id)
    db = get_db()
    if db.execute("SELECT 1 FROM venda_itens WHERE produto_id = ? LIMIT 1", (produto_id,)).fetchone():
        db.execute("UPDATE produtos_venda SET ativo = 0 WHERE id = ?", (produto_id,))
        flash(f"“{p['nome']}” já aparece em vendas, então foi arquivado (não aparece em novas vendas).", "info")
    else:
        db.execute("DELETE FROM produtos_venda WHERE id = ?", (produto_id,))
        flash(f"“{p['nome']}” foi excluído.", "sucesso")
    db.commit()
    return redirect(url_for("vendas.produtos"))


@bp.route("/produtos/<int:produto_id>/reativar", methods=["POST"])
def reativar_produto(produto_id):
    p = buscar_produto(produto_id)
    db = get_db()
    db.execute("UPDATE produtos_venda SET ativo = 1 WHERE id = ?", (produto_id,))
    db.commit()
    flash(f"“{p['nome']}” foi reativado.", "sucesso")
    return redirect(url_for("vendas.produtos", inativos=1))


# --- Vendas -------------------------------------------------------------------------------

def buscar_venda(venda_id):
    v = get_db().execute("SELECT * FROM v_vendas WHERE id = ?", (venda_id,)).fetchone()
    if v is None:
        abort(404)
    return v


def itens_da_venda(venda_id):
    return get_db().execute(
        """SELECT i.*, p.nome, c.nome AS categoria, i.quantidade * i.preco_unitario AS subtotal
             FROM venda_itens i JOIN produtos_venda p ON p.id = i.produto_id
             JOIN categorias c ON c.id = p.categoria_id
            WHERE i.venda_id = ? ORDER BY i.id""", (venda_id,)).fetchall()


@bp.route("/")
def lista():
    modo, de, ate, descricao, filtros = periodo_escolhido()
    categoria = request.args.get("categoria", "")
    forma = request.args.get("forma", "")
    db = get_db()
    sql = "SELECT * FROM v_vendas v WHERE data BETWEEN ? AND ?"
    params = [de.isoformat(), ate.isoformat()]
    if forma:
        sql += " AND forma = ?"
        params.append(forma)
    if categoria.isdigit():
        sql += """ AND EXISTS (SELECT 1 FROM venda_itens i JOIN produtos_venda p ON p.id = i.produto_id
                               WHERE i.venda_id = v.id AND p.categoria_id = ?)"""
        params.append(int(categoria))
    sql += " ORDER BY data DESC, id DESC"
    vendas = db.execute(sql, params).fetchall()
    resumo = {}
    for v in vendas:
        resumo[v["id"]] = db.execute(
            """SELECT GROUP_CONCAT(i.quantidade || '× ' || p.nome, ', ') FROM venda_itens i
                 JOIN produtos_venda p ON p.id = i.produto_id WHERE i.venda_id = ?""", (v["id"],)).fetchone()[0]
    return render_template("vendas/lista.html", vendas=vendas, resumo=resumo, modo=modo, descricao=descricao,
                           filtros=filtros, categoria=categoria, forma=forma,
                           categorias=categorias(db, "venda"),
                           formas=formas_de_pagamento(db, [r[0] for r in db.execute("SELECT DISTINCT forma FROM vendas")]),
                           total=sum(v["total"] for v in vendas))


def catalogo(ids_extras=()):
    ids_extras = [int(i) for i in ids_extras]
    sql = """SELECT p.*, c.nome AS categoria FROM produtos_venda p JOIN categorias c ON c.id = p.categoria_id
              WHERE p.ativo = 1"""
    if ids_extras:
        sql += f" OR p.id IN ({','.join('?' * len(ids_extras))})"
    sql += " ORDER BY c.ordem, p.nome COLLATE NOCASE"
    return [{"id": p["id"], "nome": p["nome"], "categoria": p["categoria"], "preco": p["preco"]}
            for p in get_db().execute(sql, ids_extras).fetchall()]


def formulario_venda(venda=None):
    db = get_db()
    if request.method == "POST":
        f = request.form
        dados = {"data": f.get("data", ""), "forma": f.get("forma", "").strip(),
                 "cliente_id": f.get("cliente_id", "").strip(), "cliente_nome": f.get("cliente_nome", "").strip(),
                 "observacao": f.get("observacao", "").strip(),
                 "itens": [{"produto_id": p, "quantidade": q}
                           for p, q in zip(f.getlist("produto_id"), f.getlist("quantidade"))]}
        erros, itens = [], []
        d = parse_data(dados["data"])
        if not d:
            erros.append("Informe a data da venda.")
        if not dados["forma"]:
            erros.append("Escolha a forma de pagamento.")
        vistos = set()
        for item in dados["itens"]:
            produto = db.execute("SELECT * FROM produtos_venda WHERE id = ?", (item["produto_id"] or 0,)).fetchone()
            if produto is None:
                erros.append("Um dos produtos escolhidos não existe mais.")
                continue
            try:
                qtd = int(item["quantidade"])
            except ValueError:
                qtd = 0
            if qtd < 1:
                erros.append(f"Quantidade inválida para “{produto['nome']}”.")
                continue
            if produto["id"] in vistos:
                erros.append(f"“{produto['nome']}” foi adicionado mais de uma vez.")
                continue
            vistos.add(produto["id"])
            # Na edição, mantém o preço da venda original; produto novo usa o preço atual.
            preco = produto["preco"]
            if venda:
                antigo = db.execute("SELECT preco_unitario FROM venda_itens WHERE venda_id = ? AND produto_id = ?",
                                    (venda["id"], produto["id"])).fetchone()
                if antigo:
                    preco = antigo[0]
            itens.append((produto["id"], qtd, preco))
        if not dados["itens"]:
            erros.append("Adicione ao menos um produto.")
        cliente_id = None
        if dados["cliente_id"].isdigit():
            if db.execute("SELECT 1 FROM clientes WHERE id = ?", (int(dados["cliente_id"]),)).fetchone():
                cliente_id = int(dados["cliente_id"])
        if not erros:
            valores = (d.isoformat(), cliente_id, "" if cliente_id else dados["cliente_nome"],
                       dados["forma"], dados["observacao"])
            if venda:
                venda_id = venda["id"]
                db.execute("""UPDATE vendas SET data = ?, cliente_id = ?, cliente_nome = ?, forma = ?,
                                  observacao = ? WHERE id = ?""", (*valores, venda_id))
                db.execute("DELETE FROM venda_itens WHERE venda_id = ?", (venda_id,))
            else:
                venda_id = db.execute("""INSERT INTO vendas (data, cliente_id, cliente_nome, forma, observacao)
                                         VALUES (?, ?, ?, ?, ?)""", valores).lastrowid
            db.executemany("INSERT INTO venda_itens (venda_id, produto_id, quantidade, preco_unitario) VALUES (?, ?, ?, ?)",
                           [(venda_id, *i) for i in itens])
            db.commit()
            flash("Venda atualizada." if venda else f"Venda nº {venda_id} registrada.", "sucesso")
            return redirect(url_for("vendas.ver", venda_id=venda_id))
        for e in erros:
            flash(e, "erro")
    elif venda:
        dados = {"data": venda["data"], "forma": venda["forma"], "cliente_id": str(venda["cliente_id"] or ""),
                 "cliente_nome": venda["cliente"], "observacao": venda["observacao"],
                 "itens": [{"produto_id": i["produto_id"], "quantidade": i["quantidade"]} for i in itens_da_venda(venda["id"])]}
    else:
        dados = {"data": date.today().isoformat(), "forma": "", "cliente_id": "", "cliente_nome": "",
                 "observacao": "", "itens": []}

    ids = [i["produto_id"] for i in dados["itens"] if str(i["produto_id"]).isdigit()]
    clientes = [{"id": c["id"], "nome": c["nome"], "cpf": formatar_cpf(c["cpf"])}
                for c in db.execute("SELECT id, nome, cpf FROM clientes ORDER BY nome COLLATE NOCASE")]
    return render_template("vendas/form.html", venda=venda, dados=dados, catalogo=catalogo(ids), clientes=clientes,
                           formas=formas_de_pagamento(db, [dados["forma"]]))


@bp.route("/nova", methods=["GET", "POST"])
def nova():
    return formulario_venda()


@bp.route("/<int:venda_id>")
def ver(venda_id):
    return render_template("vendas/ver.html", venda=buscar_venda(venda_id), itens=itens_da_venda(venda_id))


@bp.route("/<int:venda_id>/editar", methods=["GET", "POST"])
def editar(venda_id):
    return formulario_venda(buscar_venda(venda_id))


@bp.route("/<int:venda_id>/excluir", methods=["POST"])
def excluir(venda_id):
    buscar_venda(venda_id)
    db = get_db()
    db.execute("DELETE FROM vendas WHERE id = ?", (venda_id,))
    db.commit()
    flash(f"Venda nº {venda_id} excluída (também saiu do financeiro).", "info")
    return redirect(url_for("vendas.lista"))
