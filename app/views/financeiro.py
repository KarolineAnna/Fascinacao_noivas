"""Financeiro: movimentações (fichas, vendas e lançamentos manuais), totais e fechamento de caixa."""
import calendar
from datetime import date

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from ..db import categorias, formas_de_pagamento, get_db
from ..util import MESES, centavos_para_campo, formatar_data, parse_data, reais_para_centavos

bp = Blueprint("financeiro", __name__, url_prefix="/financeiro")

ORIGENS = {"ficha": "Ficha", "venda": "Venda", "manual": "Lançamento"}
TIPOS = {"entrada": "Entrada", "saida": "Saída"}


def periodo_escolhido():
    """Retorna (modo, início, fim, descrição, valores dos filtros)."""
    args = request.args
    modo = args.get("modo", "mes")
    hoje = date.today()

    if modo == "dia":
        dia = parse_data(args.get("dia")) or hoje
        return modo, dia, dia, formatar_data(dia), {"dia": dia.isoformat()}

    if modo == "periodo":
        de = parse_data(args.get("de")) or hoje.replace(day=1)
        ate = parse_data(args.get("ate")) or hoje
        if ate < de:
            de, ate = ate, de
        return (modo, de, ate, f"{formatar_data(de)} a {formatar_data(ate)}",
                {"de": de.isoformat(), "ate": ate.isoformat()})

    try:
        ano, mes = (int(x) for x in args.get("mes", "").split("-"))
        inicio = date(ano, mes, 1)
    except ValueError:
        inicio = hoje.replace(day=1)
    fim = inicio.replace(day=calendar.monthrange(inicio.year, inicio.month)[1])
    return ("mes", inicio, fim, f"{MESES[inicio.month - 1]} de {inicio.year}",
            {"mes": inicio.strftime("%Y-%m")})


def movimentos(de, ate, tipo="", categoria="", forma=""):
    sql = "SELECT * FROM v_movimentos WHERE data BETWEEN ? AND ?"
    params = [de.isoformat(), ate.isoformat()]
    if tipo in TIPOS:
        sql += " AND tipo = ?"
        params.append(tipo)
    if categoria == "aluguel":
        sql += " AND origem = 'ficha'"
    elif categoria == "venda":
        sql += " AND origem = 'venda'"
    elif categoria.isdigit():
        sql += " AND categoria_id = ?"
        params.append(int(categoria))
    if forma:
        sql += " AND COALESCE(NULLIF(forma, ''), 'Não informada') = ?"
        params.append(forma)
    sql += " ORDER BY data, CASE origem WHEN 'ficha' THEN 0 WHEN 'venda' THEN 1 ELSE 2 END, ref_id"
    return get_db().execute(sql, params).fetchall()


def esperado_por_forma(dia):
    """Por forma de pagamento no dia: fichas, vendas, entradas e saídas manuais e o esperado no caixa."""
    linhas = {}
    for m in movimentos(dia, dia):
        forma = m["forma"] or "Não informada"
        r = linhas.setdefault(forma, {"forma": forma, "fichas": 0, "vendas": 0, "entradas": 0, "saidas": 0})
        if m["tipo"] == "saida":
            r["saidas"] += m["valor"]            # inclui devolução de caução
        elif m["origem"] == "ficha":
            r["fichas"] += m["valor"]            # entrada, restante, multa e caução recebida
        elif m["origem"] == "venda":
            r["vendas"] += m["valor"]
        else:
            r["entradas"] += m["valor"]
    ordem = formas_de_pagamento(get_db())
    resultado = []
    for forma in ordem + sorted(f for f in linhas if f not in ordem):
        r = linhas.get(forma, {"forma": forma, "fichas": 0, "vendas": 0, "entradas": 0, "saidas": 0})
        r["esperado"] = r["fichas"] + r["vendas"] + r["entradas"] - r["saidas"]
        resultado.append(r)
    return resultado


# --- Tela do Financeiro ------------------------------------------------------------

@bp.route("/")
def lista():
    modo, de, ate, descricao, filtros = periodo_escolhido()
    tipo = request.args.get("tipo", "")
    categoria = request.args.get("categoria", "")
    forma = request.args.get("forma", "")
    db = get_db()

    lista_mov = movimentos(de, ate, tipo, categoria, forma)
    entradas = sum(m["valor"] for m in lista_mov if m["tipo"] == "entrada")
    saidas = sum(m["valor"] for m in lista_mov if m["tipo"] == "saida")

    por_categoria = {}
    for m in lista_mov:
        c = por_categoria.setdefault(m["categoria"], {"nome": m["categoria"], "entradas": 0, "saidas": 0})
        c["entradas" if m["tipo"] == "entrada" else "saidas"] += m["valor"]
    por_categoria = sorted(por_categoria.values(), key=lambda c: -(c["entradas"] + c["saidas"]))

    por_forma = {}
    for m in lista_mov:
        nome = m["forma"] or "Não informada"
        por_forma[nome] = por_forma.get(nome, 0) + (m["valor"] if m["tipo"] == "entrada" else -m["valor"])
    por_forma = sorted(por_forma.items(), key=lambda kv: -abs(kv[1]))

    pendentes = db.execute(
        """SELECT * FROM v_fichas
            WHERE situacao != 'cancelada'
              AND ((status_financeiro != 'quitada' AND restante > 0) OR multa_pendente > 0)
            ORDER BY data_saida, id""").fetchall()

    usadas = [r[0] for r in db.execute("SELECT DISTINCT COALESCE(NULLIF(forma, ''), 'Não informada') FROM v_movimentos")]
    return render_template(
        "financeiro/lista.html", modo=modo, descricao=descricao, filtros=filtros,
        tipo=tipo, categoria=categoria, forma=forma, tipos=TIPOS, origens=ORIGENS,
        categorias=categorias(db, "financeiro"), formas=formas_de_pagamento(db),
        formas_filtro=formas_de_pagamento(db, usadas),
        movimentos=lista_mov, entradas=entradas, saidas=saidas, saldo=entradas - saidas,
        por_categoria=por_categoria, por_forma=por_forma,
        pendentes=pendentes,
        total_a_receber=sum((p["restante"] if p["status_financeiro"] != "quitada" else 0) + p["multa_pendente"]
                            for p in pendentes),
    )


# --- Lançamentos manuais ----------------------------------------------------------------

def buscar_lancamento(lancamento_id):
    lanc = get_db().execute("SELECT * FROM lancamentos WHERE id = ?", (lancamento_id,)).fetchone()
    if lanc is None:
        abort(404)
    return lanc


def ler_lancamento():
    f = request.form
    dados = {k: f.get(k, "").strip() for k in ("tipo", "data", "descricao", "categoria_id", "valor", "forma", "observacao")}
    erros = []
    if dados["tipo"] not in TIPOS:
        erros.append("Escolha se é uma entrada ou uma saída.")
    d = parse_data(dados["data"])
    if not d:
        erros.append("Informe a data.")
    if not dados["descricao"]:
        erros.append("Informe a descrição.")
    categoria = get_db().execute("SELECT id FROM categorias WHERE grupo = 'financeiro' AND id = ?",
                                 (dados["categoria_id"] or 0,)).fetchone()
    if not categoria:
        erros.append("Escolha a categoria.")
    valor = reais_para_centavos(dados["valor"])
    if not valor:
        erros.append("Informe um valor maior que zero (ex.: 80,00).")
    if not dados["forma"]:
        erros.append("Escolha a forma de pagamento.")
    limpo = (dados["tipo"], d.isoformat() if d else None, dados["descricao"],
             int(dados["categoria_id"] or 0), valor, dados["forma"], dados["observacao"])
    return dados, limpo, erros


def formulario_lancamento(lanc=None):
    db = get_db()
    if request.method == "POST":
        dados, limpo, erros = ler_lancamento()
        if not erros:
            if lanc:
                db.execute("""UPDATE lancamentos SET tipo = ?, data = ?, descricao = ?, categoria_id = ?,
                                  valor = ?, forma = ?, observacao = ? WHERE id = ?""", (*limpo, lanc["id"]))
                flash("Lançamento atualizado.", "sucesso")
            else:
                db.execute("""INSERT INTO lancamentos (tipo, data, descricao, categoria_id, valor, forma, observacao)
                              VALUES (?, ?, ?, ?, ?, ?, ?)""", limpo)
                flash(f"{TIPOS[limpo[0]]} “{limpo[2]}” registrada.", "sucesso")
            db.commit()
            return redirect(url_for("financeiro.lista", modo="dia", dia=limpo[1]))
        for e in erros:
            flash(e, "erro")
    elif lanc:
        dados = dict(lanc, valor=centavos_para_campo(lanc["valor"]), categoria_id=str(lanc["categoria_id"]))
    else:
        dados = {"tipo": request.args.get("tipo", "saida"), "data": date.today().isoformat(), "descricao": "",
                 "categoria_id": "", "valor": "", "forma": "", "observacao": ""}
    return render_template("financeiro/lancamento.html", lancamento=lanc, dados=dados, tipos=TIPOS,
                           categorias=categorias(db, "financeiro"),
                           formas=formas_de_pagamento(db, [dados.get("forma")]))


@bp.route("/lancamentos/novo", methods=["GET", "POST"])
def novo_lancamento():
    return formulario_lancamento()


@bp.route("/lancamentos/<int:lancamento_id>/editar", methods=["GET", "POST"])
def editar_lancamento(lancamento_id):
    return formulario_lancamento(buscar_lancamento(lancamento_id))


@bp.route("/lancamentos/<int:lancamento_id>/excluir", methods=["POST"])
def excluir_lancamento(lancamento_id):
    lanc = buscar_lancamento(lancamento_id)
    db = get_db()
    db.execute("DELETE FROM lancamentos WHERE id = ?", (lancamento_id,))
    db.commit()
    flash(f"Lançamento “{lanc['descricao']}” excluído.", "info")
    destino = request.form.get("voltar", "")
    return redirect(destino if destino.startswith("/") and not destino.startswith("//")
                    else url_for("financeiro.lista"))


# --- Fechamento de caixa -------------------------------------------------------------------

@bp.route("/fechamento", methods=["GET", "POST"])
def fechamento():
    dia = parse_data(request.values.get("data")) or date.today()
    db = get_db()
    linhas = esperado_por_forma(dia)

    if request.method == "POST":
        erros = []
        registros = []
        for r in linhas:
            texto = request.form.get(f"contado_{r['forma']}", "").strip()
            if not texto:
                continue
            contado = reais_para_centavos(texto)
            if contado is None:
                erros.append(f"Valor contado inválido em {r['forma']}.")
                continue
            registros.append((dia.isoformat(), r["forma"], r["esperado"], contado,
                              request.form.get("observacao", "").strip()))
        if not registros and not erros:
            erros.append("Informe o valor contado de pelo menos uma forma de pagamento.")
        if erros:
            for e in erros:
                flash(e, "erro")
        else:
            db.executemany("""INSERT INTO fechamentos (data, forma, esperado, contado, observacao)
                              VALUES (?, ?, ?, ?, ?)
                              ON CONFLICT(data, forma) DO UPDATE SET esperado = excluded.esperado,
                                  contado = excluded.contado, observacao = excluded.observacao,
                                  criado_em = datetime('now', 'localtime')""", registros)
            db.commit()
            flash(f"Caixa de {formatar_data(dia)} fechado.", "sucesso")
            return redirect(url_for("financeiro.fechamento", data=dia.isoformat()))

    fechados = {f["forma"]: f for f in db.execute("SELECT * FROM fechamentos WHERE data = ?", (dia.isoformat(),))}
    ultimos = db.execute("""SELECT data, SUM(esperado) AS esperado, SUM(contado) AS contado, MAX(criado_em) AS em
                              FROM fechamentos GROUP BY data ORDER BY data DESC LIMIT 10""").fetchall()
    return render_template("financeiro/fechamento.html", dia=dia, linhas=linhas, fechados=fechados,
                           total_esperado=sum(r["esperado"] for r in linhas), ultimos=ultimos,
                           observacao=next((f["observacao"] for f in fechados.values() if f["observacao"]), ""))
