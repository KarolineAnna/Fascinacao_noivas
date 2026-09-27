from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for

from ..db import get_db
from ..util import cpf_valido, formatar_cpf, so_digitos

bp = Blueprint("clientes", __name__, url_prefix="/clientes")

SQL_ALUGUEIS_DO_CLIENTE = """
    SELECT f.*,
           (SELECT GROUP_CONCAT(p.nome, ', ')
              FROM aluguel_itens i JOIN produtos p ON p.id = i.produto_id
             WHERE i.aluguel_id = f.id) AS pecas
      FROM v_fichas f
     WHERE f.cliente_id = ?
     ORDER BY f.data_saida DESC
"""


def buscar(cliente_id):
    cliente = get_db().execute("SELECT * FROM clientes WHERE id = ?", (cliente_id,)).fetchone()
    if cliente is None:
        abort(404)
    return cliente


def validar_cliente(nome, cpf, ignorar_id=None):
    """Retorna a lista de erros para os dados de um cliente."""
    erros = []
    if not nome:
        erros.append("Informe o nome do cliente.")
    if not cpf_valido(cpf):
        erros.append("CPF inválido. Confira os números digitados.")
    else:
        existente = get_db().execute("SELECT id, nome FROM clientes WHERE cpf = ?",
                                     (so_digitos(cpf),)).fetchone()
        if existente and existente["id"] != ignorar_id:
            erros.append(f"O CPF {formatar_cpf(cpf)} já pertence a {existente['nome']}.")
    return erros


@bp.route("/")
def lista():
    q = request.args.get("q", "").strip()
    sql = """
        SELECT c.*, COUNT(a.id) AS qtd_alugueis
          FROM clientes c LEFT JOIN alugueis a ON a.cliente_id = c.id
    """
    params = []
    if q:
        digitos = so_digitos(q)
        if digitos:
            sql += " WHERE c.nome LIKE ? OR c.cpf LIKE ?"
            params = [f"%{q}%", f"%{digitos}%"]
        else:
            sql += " WHERE c.nome LIKE ?"
            params = [f"%{q}%"]
    sql += " GROUP BY c.id ORDER BY c.nome COLLATE NOCASE"
    clientes = get_db().execute(sql, params).fetchall()
    return render_template("clientes/lista.html", clientes=clientes, q=q)


@bp.route("/<int:cliente_id>", methods=["GET", "POST"])
def ver(cliente_id):
    cliente = buscar(cliente_id)
    dados = dict(cliente)
    if request.method == "POST":
        dados = {
            "nome": request.form.get("nome", "").strip(),
            "cpf": request.form.get("cpf", "").strip(),
            "telefone": request.form.get("telefone", "").strip(),
            "endereco": request.form.get("endereco", "").strip(),
        }
        erros = validar_cliente(dados["nome"], dados["cpf"], ignorar_id=cliente_id)
        if erros:
            for e in erros:
                flash(e, "erro")
        else:
            db = get_db()
            db.execute("UPDATE clientes SET nome = ?, cpf = ?, telefone = ?, endereco = ?"
                       " WHERE id = ?",
                       (dados["nome"], so_digitos(dados["cpf"]), dados["telefone"],
                        dados["endereco"], cliente_id))
            db.commit()
            flash("Dados do cliente atualizados.", "sucesso")
            return redirect(url_for("clientes.ver", cliente_id=cliente_id))

    alugueis = get_db().execute(SQL_ALUGUEIS_DO_CLIENTE, (cliente_id,)).fetchall()
    return render_template("clientes/ver.html", cliente=cliente, dados=dados, alugueis=alugueis)


@bp.route("/api/cpf/<cpf>")
def api_por_cpf(cpf):
    """Usado pela ficha para reaproveitar o cadastro quando o CPF já existe."""
    digitos = so_digitos(cpf)
    resposta = {"valido": cpf_valido(digitos), "cliente": None}
    if resposta["valido"]:
        c = get_db().execute("SELECT * FROM clientes WHERE cpf = ?", (digitos,)).fetchone()
        if c:
            resposta["cliente"] = {"id": c["id"], "nome": c["nome"], "telefone": c["telefone"],
                                   "endereco": c["endereco"]}
    return jsonify(resposta)
