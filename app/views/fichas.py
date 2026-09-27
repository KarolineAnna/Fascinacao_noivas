from datetime import date

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from ..db import formas_de_pagamento, get_db
from ..pecas import ao_mudar_situacao, situacao_das_pecas
from .produtos import TIPOS
from ..util import (SITUACOES, STATUS_FINANCEIRO, centavos_para_campo, cpf_valido, formatar_brl,
                    parse_data, reais_para_centavos, so_digitos)

bp = Blueprint("fichas", __name__, url_prefix="/fichas")


def voltar_para(padrao):
    """Volta para a tela de origem (só aceita caminhos internos do sistema)."""
    destino = request.form.get("voltar", "")
    return destino if destino.startswith("/") and not destino.startswith("//") else padrao


# --- Consultas ----------------------------------------------------------------

def buscar(ficha_id):
    ficha = get_db().execute("SELECT * FROM v_fichas WHERE id = ?", (ficha_id,)).fetchone()
    if ficha is None:
        abort(404)
    return ficha


def itens_da_ficha(ficha_id):
    return get_db().execute(
        """SELECT i.*, p.codigo, p.nome, p.tipo, p.tamanho, p.cor, p.ativo
             FROM aluguel_itens i JOIN produtos p ON p.id = i.produto_id
            WHERE i.aluguel_id = ? ORDER BY i.id""",
        (ficha_id,),
    ).fetchall()


def catalogo(ids_extras=()):
    """Peças disponíveis para escolher: as ativas e as que já estão na ficha."""
    ids_extras = [int(i) for i in ids_extras]
    sql = "SELECT * FROM produtos WHERE ativo = 1"
    if ids_extras:
        sql += f" OR id IN ({','.join('?' * len(ids_extras))})"
    sql += " ORDER BY nome COLLATE NOCASE"
    situacoes = situacao_das_pecas(get_db())
    return [
        {"id": p["id"], "codigo": p["codigo"], "nome": p["nome"], "tipo": p["tipo"],
         "tamanho": p["tamanho"], "cor": p["cor"],
         "valor": centavos_para_campo(p["valor_aluguel"]),
         "situacao": situacoes[p["id"]]["situacao"],
         "lavagem_desde": situacoes[p["id"]].get("lavagem_desde")}
        for p in get_db().execute(sql, ids_extras).fetchall()
    ]


def conflitos(produto_ids, saida, devolucao, ignorar_ficha=None):
    """Outras fichas não devolvidas que usam as mesmas peças em período que se sobrepõe.
    Uma ficha atrasada (devolução vencida e não marcada como devolvida) segura a peça até hoje."""
    if not produto_ids:
        return []
    marcadores = ",".join(f":p{i}" for i in range(len(produto_ids)))
    return get_db().execute(
        f"""SELECT f.id AS ficha_id, f.cliente_nome, f.data_saida, f.data_devolucao,
                   f.situacao, p.id AS produto_id, p.codigo, p.nome,
                   f.data_devolucao < :hoje AS atrasada
              FROM aluguel_itens i
              JOIN v_fichas f ON f.id = i.aluguel_id
              JOIN produtos p ON p.id = i.produto_id
             WHERE i.produto_id IN ({marcadores})
               AND f.id != :ignorar
               AND f.situacao NOT IN ('devolvida', 'cancelada')
               AND f.data_saida <= :devolucao
               AND MAX(f.data_devolucao, :hoje) >= :saida
             ORDER BY f.data_saida""",
        {**{f"p{i}": pid for i, pid in enumerate(produto_ids)},
         "ignorar": ignorar_ficha or 0, "devolucao": devolucao.isoformat(),
         "saida": saida.isoformat(), "hoje": date.today().isoformat()},
    ).fetchall()


def chave_conflitos(lista):
    return ",".join(sorted(f"{c['ficha_id']}-{c['produto_id']}" for c in lista))


# --- Formulário ---------------------------------------------------------------

def dados_vazios():
    return {"cpf": "", "nome": "", "telefone": "", "endereco": "", "itens": [],
            "data_saida": "", "data_devolucao": "", "situacao": "reservada",
            "entrada_paga": False, "valor_entrada": "", "data_entrada": date.today().isoformat(),
            "forma_entrada": "", "restante_pago": False,
            "data_restante": date.today().isoformat(), "forma_restante": "", "observacoes": ""}


def dados_da_ficha(ficha):
    return {
        "cpf": ficha["cliente_cpf"], "nome": ficha["cliente_nome"],
        "telefone": ficha["cliente_telefone"], "endereco": ficha["cliente_endereco"],
        "itens": [{"produto_id": i["produto_id"], "valor": centavos_para_campo(i["valor_cobrado"])}
                  for i in itens_da_ficha(ficha["id"])],
        "data_saida": ficha["data_saida"], "data_devolucao": ficha["data_devolucao"],
        "situacao": ficha["situacao"],
        "entrada_paga": bool(ficha["entrada_paga"]),
        "valor_entrada": centavos_para_campo(ficha["valor_entrada"]) if ficha["entrada_paga"] else "",
        "data_entrada": ficha["data_entrada"] or date.today().isoformat(),
        "forma_entrada": ficha["forma_entrada"] or "",
        "restante_pago": bool(ficha["restante_pago"]),
        "data_restante": ficha["data_restante"] or date.today().isoformat(),
        "forma_restante": ficha["forma_restante"] or "",
        "observacoes": ficha["observacoes"],
    }


def ler_formulario():
    """Lê e valida o formulário. Retorna (dados para reexibir, valores limpos, erros)."""
    f = request.form
    dados = {
        "cpf": f.get("cpf", "").strip(), "nome": f.get("nome", "").strip(),
        "telefone": f.get("telefone", "").strip(), "endereco": f.get("endereco", "").strip(),
        "itens": [{"produto_id": pid, "valor": v}
                  for pid, v in zip(f.getlist("produto_id"), f.getlist("valor_cobrado"))],
        "data_saida": f.get("data_saida", ""), "data_devolucao": f.get("data_devolucao", ""),
        "situacao": f.get("situacao", "reservada"),
        "entrada_paga": f.get("entrada_paga") == "1",
        "valor_entrada": f.get("valor_entrada", "").strip(),
        "data_entrada": f.get("data_entrada", ""),
        "forma_entrada": f.get("forma_entrada", "").strip(),
        "restante_pago": f.get("restante_pago") == "1",
        "data_restante": f.get("data_restante", ""),
        "forma_restante": f.get("forma_restante", "").strip(),
        "observacoes": f.get("observacoes", "").strip(),
    }
    erros = []
    limpo = {}

    # Cliente
    if not dados["nome"]:
        erros.append("Informe o nome do cliente.")
    if not cpf_valido(dados["cpf"]):
        erros.append("CPF inválido. Confira os números digitados.")
    limpo["cpf"] = so_digitos(dados["cpf"])

    # Peças
    itens, vistos = [], set()
    db = get_db()
    for item in dados["itens"]:
        try:
            pid = int(item["produto_id"])
        except ValueError:
            continue
        if pid in vistos:
            erros.append("A mesma peça foi adicionada mais de uma vez.")
            continue
        vistos.add(pid)
        produto = db.execute("SELECT nome FROM produtos WHERE id = ?", (pid,)).fetchone()
        if produto is None:
            erros.append("Uma das peças escolhidas não existe mais.")
            continue
        valor = reais_para_centavos(item["valor"])
        if valor is None:
            erros.append(f"Valor inválido para a peça “{produto['nome']}”.")
            continue
        itens.append((pid, valor))
    if not dados["itens"]:
        erros.append("Adicione ao menos uma peça à ficha.")
    limpo["itens"] = itens
    total = sum(v for _, v in itens)

    # Datas
    saida, devolucao = parse_data(dados["data_saida"]), parse_data(dados["data_devolucao"])
    if not saida:
        erros.append("Informe a data de saída.")
    if not devolucao:
        erros.append("Informe a data de devolução.")
    if saida and devolucao and devolucao <= saida:
        erros.append("A data de devolução deve ser posterior à data de saída.")
    limpo["saida"], limpo["devolucao"] = saida, devolucao

    if dados["situacao"] not in SITUACOES:
        dados["situacao"] = "reservada"

    # Financeiro
    limpo["valor_entrada"], limpo["data_entrada"], limpo["forma_entrada"] = 0, None, None
    if dados["entrada_paga"]:
        valor = reais_para_centavos(dados["valor_entrada"])
        if not valor:
            erros.append("Informe o valor da entrada paga.")
        elif valor > total:
            erros.append("A entrada não pode ser maior que o valor do aluguel.")
        else:
            limpo["valor_entrada"] = valor
        d = parse_data(dados["data_entrada"])
        if not d:
            erros.append("Informe a data em que a entrada foi paga.")
        limpo["data_entrada"] = d.isoformat() if d else None
        if not dados["forma_entrada"]:
            erros.append("Informe a forma de pagamento da entrada.")
        limpo["forma_entrada"] = dados["forma_entrada"] or None

    limpo["data_restante"], limpo["forma_restante"] = None, None
    if dados["restante_pago"]:
        d = parse_data(dados["data_restante"])
        if not d:
            erros.append("Informe a data em que o restante foi pago.")
        limpo["data_restante"] = d.isoformat() if d else None
        if not dados["forma_restante"]:
            erros.append("Informe a forma de pagamento do restante.")
        limpo["forma_restante"] = dados["forma_restante"] or None

    return dados, limpo, erros


def salvar(dados, limpo, ficha_id=None, situacao_anterior=None):
    db = get_db()
    # Reaproveita o cadastro quando o CPF já existe (e atualiza os dados de contato).
    cliente = db.execute("SELECT id FROM clientes WHERE cpf = ?", (limpo["cpf"],)).fetchone()
    if cliente:
        cliente_id = cliente["id"]
        db.execute("UPDATE clientes SET nome = ?, telefone = ?, endereco = ? WHERE id = ?",
                   (dados["nome"], dados["telefone"], dados["endereco"], cliente_id))
    else:
        cliente_id = db.execute(
            "INSERT INTO clientes (nome, cpf, telefone, endereco) VALUES (?, ?, ?, ?)",
            (dados["nome"], limpo["cpf"], dados["telefone"], dados["endereco"]),
        ).lastrowid

    valores = (cliente_id, limpo["saida"].isoformat(), limpo["devolucao"].isoformat(),
               int(dados["entrada_paga"]), limpo["valor_entrada"], limpo["data_entrada"],
               limpo["forma_entrada"], int(dados["restante_pago"]), limpo["data_restante"],
               limpo["forma_restante"], dados["situacao"], dados["observacoes"])
    if ficha_id is None:
        ficha_id = db.execute(
            """INSERT INTO alugueis (cliente_id, data_saida, data_devolucao, entrada_paga,
                   valor_entrada, data_entrada, forma_entrada, restante_pago, data_restante,
                   forma_restante, situacao, observacoes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", valores).lastrowid
    else:
        db.execute(
            """UPDATE alugueis SET cliente_id = ?, data_saida = ?, data_devolucao = ?,
                   entrada_paga = ?, valor_entrada = ?, data_entrada = ?, forma_entrada = ?,
                   restante_pago = ?, data_restante = ?, forma_restante = ?, situacao = ?,
                   observacoes = ?
             WHERE id = ?""", (*valores, ficha_id))
        db.execute("DELETE FROM aluguel_itens WHERE aluguel_id = ?", (ficha_id,))
    db.executemany("INSERT INTO aluguel_itens (aluguel_id, produto_id, valor_cobrado)"
                   " VALUES (?, ?, ?)", [(ficha_id, pid, v) for pid, v in limpo["itens"]])
    ao_mudar_situacao(db, ficha_id, situacao_anterior, dados["situacao"])
    db.commit()
    return ficha_id


def avisar_lavagem(produto_ids, ficha_id):
    """Aviso (sem bloquear) quando a ficha usa peças que estão em lavagem hoje."""
    situacoes = situacao_das_pecas(get_db())
    em_lavagem = [pid for pid in produto_ids if situacoes.get(pid, {}).get("situacao") == "lavagem"]
    if not em_lavagem:
        return
    nomes = get_db().execute(
        f"SELECT codigo, nome FROM produtos WHERE id IN ({','.join('?' * len(em_lavagem))})",
        em_lavagem).fetchall()
    lista = ", ".join(f"{n['codigo']} {n['nome']}" for n in nomes)
    flash(f"Atenção: {lista} {'está' if len(nomes) == 1 else 'estão'} em lavagem hoje. "
          "Confira se ficará pronta até a data de saída.", "info")


def processar_formulario(ficha=None):
    ficha_id = ficha["id"] if ficha else None
    lista_conflitos, chave = [], ""

    if request.method == "POST":
        dados, limpo, erros = ler_formulario()
        if not erros:
            lista_conflitos = conflitos([pid for pid, _ in limpo["itens"]],
                                        limpo["saida"], limpo["devolucao"], ficha_id)
            chave = chave_conflitos(lista_conflitos)
            if not lista_conflitos or request.form.get("confirmar_conflito") == chave:
                novo_id = salvar(dados, limpo, ficha_id, ficha["situacao"] if ficha else None)
                flash("Ficha salva." if ficha else f"Ficha nº {novo_id} criada.", "sucesso")
                avisar_lavagem([pid for pid, _ in limpo["itens"]], novo_id)
                return redirect(url_for("fichas.ver", ficha_id=novo_id))
        for e in erros:
            flash(e, "erro")
    elif ficha:
        dados = dados_da_ficha(ficha)
    else:
        dados = dados_vazios()
        # "Nova ficha" a partir da tela do cliente já chega com o cadastro preenchido.
        cliente = get_db().execute("SELECT * FROM clientes WHERE cpf = ?",
                                   (so_digitos(request.args.get("cpf")),)).fetchone()
        if cliente:
            dados.update(cpf=cliente["cpf"], nome=cliente["nome"],
                         telefone=cliente["telefone"], endereco=cliente["endereco"])

    ids = [i["produto_id"] for i in dados["itens"] if str(i["produto_id"]).isdigit()]
    formas = formas_de_pagamento(get_db(), (dados["forma_entrada"], dados["forma_restante"]))
    return render_template("fichas/form.html", ficha=ficha, dados=dados,
                           catalogo=catalogo(ids), conflitos=lista_conflitos,
                           chave_conflitos=chave, formas=formas, tipos=TIPOS)


# --- Rotas ----------------------------------------------------------------------

@bp.route("/")
def lista():
    q = request.args.get("q", "").strip()
    situacao = request.args.get("situacao", "")
    status = request.args.get("status", "")

    sql = "SELECT * FROM v_fichas WHERE 1 = 1"
    params = []
    if q:
        digitos = so_digitos(q)
        sql += " AND (cliente_nome LIKE ?" + (" OR cliente_cpf LIKE ?" if digitos else "")
        sql += " OR CAST(id AS TEXT) = ?)"
        params += [f"%{q}%"] + ([f"%{digitos}%"] if digitos else []) + [q.lstrip("#nº ")]
    if situacao in SITUACOES:
        sql += " AND situacao = ?"
        params.append(situacao)
    if status in STATUS_FINANCEIRO:
        sql += " AND status_financeiro = ?"
        params.append(status)
    sql += " ORDER BY data_saida DESC, id DESC"

    fichas = get_db().execute(sql, params).fetchall()
    return render_template("fichas/lista.html", fichas=fichas, q=q, situacao=situacao,
                           status=status)


@bp.route("/nova", methods=["GET", "POST"])
def nova():
    return processar_formulario()


@bp.route("/<int:ficha_id>")
def ver(ficha_id):
    ficha = buscar(ficha_id)
    return render_template("fichas/ver.html", ficha=ficha, itens=itens_da_ficha(ficha_id),
                           formas=formas_de_pagamento(get_db()))


@bp.route("/<int:ficha_id>/imprimir")
def imprimir(ficha_id):
    ficha = buscar(ficha_id)
    return render_template("fichas/imprimir.html", ficha=ficha, itens=itens_da_ficha(ficha_id))


@bp.route("/<int:ficha_id>/editar", methods=["GET", "POST"])
def editar(ficha_id):
    return processar_formulario(buscar(ficha_id))


@bp.route("/<int:ficha_id>/situacao", methods=["POST"])
def mudar_situacao(ficha_id):
    anterior = buscar(ficha_id)["situacao"]
    situacao = request.form.get("situacao")
    if situacao in SITUACOES:
        db = get_db()
        db.execute("UPDATE alugueis SET situacao = ? WHERE id = ?", (situacao, ficha_id))
        ao_mudar_situacao(db, ficha_id, anterior, situacao)
        db.commit()
        flash(f"Ficha nº {ficha_id} marcada como {SITUACOES[situacao].lower()}."
              + (" As peças foram para a lavagem." if situacao == "devolvida" and anterior != situacao else ""),
              "sucesso")
    return redirect(voltar_para(url_for("fichas.ver", ficha_id=ficha_id)))


@bp.route("/<int:ficha_id>/controle", methods=["POST"])
def controle(ficha_id):
    """Interruptores da ficha: entrada paga, retirada, restante pago e devolvida.
    Cada um é confirmado numa janela antes de chegar aqui."""
    ficha = buscar(ficha_id)
    voltar = voltar_para(url_for("fichas.ver", ficha_id=ficha_id))
    campo = request.form.get("campo")
    ligar = request.form.get("ligar") == "1"
    db = get_db()

    if ficha["situacao"] == "cancelada":
        flash("Esta ficha está cancelada. Reative-a antes de alterar os controles.", "erro")
        return redirect(voltar)

    def ler_pagamento(rotulo):
        d = parse_data(request.form.get("data"))
        forma = request.form.get("forma", "").strip()
        erros = []
        if not d:
            erros.append(f"Informe a data do pagamento {rotulo}.")
        if not forma:
            erros.append(f"Escolha a forma de pagamento {rotulo}.")
        return d, forma, erros

    if campo == "entrada":
        if ligar:
            valor = reais_para_centavos(request.form.get("valor"))
            d, forma, erros = ler_pagamento("da entrada")
            if not valor:
                erros.insert(0, "Informe o valor da entrada.")
            elif valor > ficha["total"]:
                erros.insert(0, "A entrada não pode ser maior que o valor do aluguel.")
            if erros:
                for e in erros:
                    flash(e, "erro")
                return redirect(voltar)
            db.execute("UPDATE alugueis SET entrada_paga = 1, valor_entrada = ?, data_entrada = ?,"
                       " forma_entrada = ? WHERE id = ?", (valor, d.isoformat(), forma, ficha_id))
            mensagem = "Entrada registrada."
        else:
            db.execute("UPDATE alugueis SET entrada_paga = 0, valor_entrada = 0, data_entrada = NULL,"
                       " forma_entrada = NULL WHERE id = ?", (ficha_id,))
            mensagem = "Entrada desmarcada e retirada do financeiro."

    elif campo == "restante":
        if ligar:
            d, forma, erros = ler_pagamento("do restante")
            if erros:
                for e in erros:
                    flash(e, "erro")
                return redirect(voltar)
            db.execute("UPDATE alugueis SET restante_pago = 1, data_restante = ?, forma_restante = ?"
                       " WHERE id = ?", (d.isoformat(), forma, ficha_id))
            mensagem = "Restante registrado como pago."
        else:
            db.execute("UPDATE alugueis SET restante_pago = 0, data_restante = NULL,"
                       " forma_restante = NULL WHERE id = ?", (ficha_id,))
            mensagem = "Restante desmarcado e retirado do financeiro."

    elif campo == "retirada":
        if ficha["situacao"] == "devolvida":
            flash("Desmarque “Devolvida” antes de alterar a retirada.", "erro")
            return redirect(voltar)
        nova = "retirada" if ligar else "reservada"
        mensagem = "Ficha marcada como retirada." if ligar else "Retirada desmarcada: a ficha voltou para reservada."
        if ligar and request.form.get("restante_agora") == "1":
            d, forma, erros = ler_pagamento("do restante")
            if erros:
                for e in erros:
                    flash(e, "erro")
                return redirect(voltar)
            db.execute("UPDATE alugueis SET restante_pago = 1, data_restante = ?, forma_restante = ?"
                       " WHERE id = ?", (d.isoformat(), forma, ficha_id))
            mensagem = "Ficha marcada como retirada e restante registrado como pago."
        db.execute("UPDATE alugueis SET situacao = ? WHERE id = ?", (nova, ficha_id))
        ao_mudar_situacao(db, ficha_id, ficha["situacao"], nova)

    elif campo == "devolvida":
        nova = "devolvida" if ligar else "retirada"
        erros = []
        if ligar:
            # valores escolhidos na janela (multa ajustável / paga na hora, caução devolvida na hora)
            multa = reais_para_centavos(request.form.get("multa_valor")) if request.form.get("multa_valor", "").strip() else None
            multa_agora = request.form.get("multa_agora") == "1"
            caucao_agora = request.form.get("caucao_agora") == "1"
            if multa_agora:
                dm, fm = parse_data(request.form.get("multa_data")), request.form.get("multa_forma", "").strip()
                if not fm:
                    erros.append("Escolha a forma de pagamento da multa.")
                if not dm:
                    erros.append("Informe a data do pagamento da multa.")
            if caucao_agora:
                dc, fc = parse_data(request.form.get("caucao_data")), request.form.get("caucao_forma", "").strip()
                devolvido = reais_para_centavos(request.form.get("caucao_devolvido")) if request.form.get("caucao_devolvido", "").strip() else ficha["caucao_valor"]
                if not fc:
                    erros.append("Escolha a forma de devolução da caução.")
                if not dc:
                    erros.append("Informe a data da devolução da caução.")
                if devolvido is None or devolvido > ficha["caucao_valor"]:
                    erros.append("O valor devolvido não pode ser maior que a caução.")
        if erros:
            for e in erros:
                flash(e, "erro")
            return redirect(voltar)
        db.execute("UPDATE alugueis SET situacao = ? WHERE id = ?", (nova, ficha_id))
        ao_mudar_situacao(db, ficha_id, ficha["situacao"], nova)
        mensagem = ("Ficha marcada como devolvida. As peças foram para a lavagem." if ligar else
                    "Devolução desmarcada: a ficha voltou para retirada e as peças saíram da lavagem.")
        if ligar:
            if multa is not None:
                db.execute("UPDATE alugueis SET multa_valor = ? WHERE id = ? AND multa_paga = 0", (multa, ficha_id))
            atual = db.execute("SELECT multa_valor FROM alugueis WHERE id = ?", (ficha_id,)).fetchone()[0]
            if multa_agora and atual:
                db.execute("UPDATE alugueis SET multa_paga = 1, multa_data = ?, multa_forma = ? WHERE id = ?",
                           (dm.isoformat(), fm, ficha_id))
                mensagem += f" Multa de {formatar_brl(atual)} registrada como paga."
            elif atual:
                mensagem += f" Multa por atraso de {formatar_brl(atual)} a receber."
            if caucao_agora:
                db.execute("""UPDATE alugueis SET caucao_devolvida = 1, caucao_devolvido_valor = ?,
                                  caucao_devolucao_data = ?, caucao_devolucao_forma = ? WHERE id = ?""",
                           (devolvido, dc.isoformat(), fc, ficha_id))
                mensagem += f" Caução devolvida: {formatar_brl(devolvido)}."

    elif campo == "caucao":
        if ligar:
            valor = reais_para_centavos(request.form.get("valor"))
            d, forma, erros = ler_pagamento("da caução")
            if not valor:
                erros.insert(0, "Informe o valor da caução.")
            if erros:
                for e in erros:
                    flash(e, "erro")
                return redirect(voltar)
            db.execute("UPDATE alugueis SET caucao_valor = ?, caucao_data = ?, caucao_forma = ? WHERE id = ?",
                       (valor, d.isoformat(), forma, ficha_id))
            mensagem = f"Caução de {formatar_brl(valor)} registrada."
        else:
            if ficha["caucao_devolvida"]:
                flash("Desmarque “Caução devolvida” antes de remover a caução.", "erro")
                return redirect(voltar)
            db.execute("UPDATE alugueis SET caucao_valor = 0, caucao_data = NULL, caucao_forma = NULL WHERE id = ?",
                       (ficha_id,))
            mensagem = "Caução removida (e retirada do financeiro)."

    elif campo == "caucao_devolvida":
        if ligar:
            if not ficha["caucao_valor"]:
                flash("Esta ficha não tem caução registrada.", "erro")
                return redirect(voltar)
            texto = request.form.get("valor", "").strip()
            devolvido = reais_para_centavos(texto) if texto else ficha["caucao_valor"]
            d, forma, erros = ler_pagamento("da devolução da caução")
            if devolvido is None or devolvido > ficha["caucao_valor"]:
                erros.insert(0, "O valor devolvido não pode ser maior que a caução.")
            if erros:
                for e in erros:
                    flash(e, "erro")
                return redirect(voltar)
            db.execute("""UPDATE alugueis SET caucao_devolvida = 1, caucao_devolvido_valor = ?,
                              caucao_devolucao_data = ?, caucao_devolucao_forma = ? WHERE id = ?""",
                       (devolvido, d.isoformat(), forma, ficha_id))
            retido = ficha["caucao_valor"] - devolvido
            mensagem = f"Caução devolvida: {formatar_brl(devolvido)}" + (f" (retidos {formatar_brl(retido)})." if retido else ".")
        else:
            db.execute("""UPDATE alugueis SET caucao_devolvida = 0, caucao_devolvido_valor = 0,
                              caucao_devolucao_data = NULL, caucao_devolucao_forma = NULL WHERE id = ?""", (ficha_id,))
            mensagem = "Devolução da caução desmarcada (e retirada do financeiro)."

    elif campo == "multa":
        if ligar:
            texto = request.form.get("valor", "").strip()
            valor = reais_para_centavos(texto) if texto else ficha["multa_valor"]
            d, forma, erros = ler_pagamento("da multa")
            if not valor:
                erros.insert(0, "Informe o valor da multa.")
            if erros:
                for e in erros:
                    flash(e, "erro")
                return redirect(voltar)
            db.execute("UPDATE alugueis SET multa_valor = ?, multa_paga = 1, multa_data = ?, multa_forma = ? WHERE id = ?",
                       (valor, d.isoformat(), forma, ficha_id))
            mensagem = f"Multa de {formatar_brl(valor)} registrada como paga."
        else:
            db.execute("UPDATE alugueis SET multa_paga = 0, multa_data = NULL, multa_forma = NULL WHERE id = ?", (ficha_id,))
            mensagem = "Pagamento da multa desmarcado (e retirado do financeiro)."

    elif campo == "isentar_multa":
        db.execute("UPDATE alugueis SET multa_valor = 0, multa_paga = 0, multa_data = NULL, multa_forma = NULL WHERE id = ?",
                   (ficha_id,))
        mensagem = "Multa por atraso isentada."
    else:
        abort(400)

    db.commit()
    flash(f"Ficha nº {ficha_id}: {mensagem}", "sucesso")
    return redirect(voltar)


@bp.route("/<int:ficha_id>/quitar", methods=["POST"])
def quitar(ficha_id):
    """Marca o restante como pago na data informada (ou hoje) e na forma escolhida."""
    buscar(ficha_id)
    d = parse_data(request.form.get("data")) or date.today()
    forma = request.form.get("forma", "").strip()
    if not forma:
        flash("Escolha a forma de pagamento do restante.", "erro")
        return redirect(voltar_para(url_for("fichas.ver", ficha_id=ficha_id)))
    db = get_db()
    db.execute("UPDATE alugueis SET restante_pago = 1, data_restante = ?, forma_restante = ?"
               " WHERE id = ?", (d.isoformat(), forma, ficha_id))
    db.commit()
    flash(f"Restante da ficha nº {ficha_id} registrado como pago.", "sucesso")
    return redirect(voltar_para(url_for("fichas.ver", ficha_id=ficha_id)))
