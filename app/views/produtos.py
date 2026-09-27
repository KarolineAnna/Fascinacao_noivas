from datetime import date

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for

from ..db import get_db
from ..pecas import SITUACOES_PECA, alugadas_hoje, situacao_das_pecas
from ..util import centavos_para_campo, parse_data, reais_para_centavos

bp = Blueprint("produtos", __name__, url_prefix="/produtos")

TIPOS = ["Vestido de noiva", "Vestido de festa", "Terno", "Smoking", "Colete",
         "Camisa", "Gravata", "Gravata-borboleta", "Véu", "Acessório", "Outro"]


def buscar(produto_id):
    produto = get_db().execute("SELECT * FROM produtos WHERE id = ?", (produto_id,)).fetchone()
    if produto is None:
        abort(404)
    return produto


def proximo_codigo(db):
    """Código automático: o próximo número depois do maior código numérico já usado.

    Segue o número de dígitos dos códigos existentes (ex.: 05 -> 06); num acervo vazio começa em 001.
    Códigos antigos que não são só números (ex.: V01) são mantidos e simplesmente ignorados aqui."""
    numericos = [r[0] for r in db.execute("SELECT codigo FROM produtos") if r[0].isdigit()]
    largura = max((len(c) for c in numericos), default=3)
    numero = max((int(c) for c in numericos), default=0) + 1
    while True:
        codigo = str(numero).zfill(largura)
        if not db.execute("SELECT 1 FROM produtos WHERE codigo = ?", (codigo,)).fetchone():
            return codigo
        numero += 1


def ler_formulario():
    form = request.form
    dados = {
        "nome": form.get("nome", "").strip(),
        "tipo": form.get("tipo", "").strip(),
        "tamanho": form.get("tamanho", "").strip(),
        "cor": form.get("cor", "").strip(),
        "valor_texto": form.get("valor_aluguel", "").strip(),
    }
    erros = []
    if not dados["nome"]:
        erros.append("Informe o nome ou a descrição da peça.")
    valor = reais_para_centavos(dados["valor_texto"])
    if valor is None:
        erros.append("Informe um valor de aluguel válido (ex.: 350,00).")
    dados["valor_aluguel"] = valor
    return dados, erros


@bp.route("/")
def lista():
    q = request.args.get("q", "").strip()
    tipo = request.args.get("tipo", "").strip()
    inativos = request.args.get("inativos") == "1"
    situacao = request.args.get("situacao", "")

    sql = "SELECT * FROM produtos WHERE 1 = 1"
    params = []
    if not inativos:
        sql += " AND ativo = 1"
    if q:
        sql += " AND (nome LIKE ? OR codigo LIKE ? OR cor LIKE ?)"
        params += [f"%{q}%"] * 3
    if tipo:
        sql += " AND tipo = ?"
        params.append(tipo)
    sql += " ORDER BY ativo DESC, nome COLLATE NOCASE"

    produtos = get_db().execute(sql, params).fetchall()
    situacoes = situacao_das_pecas(get_db())
    if situacao in SITUACOES_PECA:
        produtos = [p for p in produtos if situacoes[p["id"]]["situacao"] == situacao]
    return render_template("produtos/lista.html", produtos=produtos, q=q, tipo=tipo,
                           inativos=inativos, tipos=TIPOS, situacao=situacao,
                           situacoes=situacoes)


def cadastrar():
    """Valida o formulário e cria a peça. Retorna (dados, id da peça ou None, erros)."""
    dados, erros = ler_formulario()
    if erros:
        return dados, None, erros
    db = get_db()
    dados["codigo"] = proximo_codigo(db)
    produto_id = db.execute(
        "INSERT INTO produtos (codigo, nome, tipo, tamanho, cor, valor_aluguel)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (dados["codigo"], dados["nome"], dados["tipo"], dados["tamanho"],
         dados["cor"], dados["valor_aluguel"]),
    ).lastrowid
    db.commit()
    return dados, produto_id, []


@bp.route("/novo", methods=["GET", "POST"])
def novo():
    dados = {}
    if request.method == "POST":
        dados, produto_id, erros = cadastrar()
        if produto_id:
            flash(f"Peça “{dados['nome']}” cadastrada com o código {dados['codigo']}.", "sucesso")
            return redirect(url_for("produtos.lista"))
        for e in erros:
            flash(e, "erro")
    return render_template("produtos/form.html", produto=None, dados=dados, tipos=TIPOS,
                           proximo=proximo_codigo(get_db()))


@bp.route("/api/novo", methods=["POST"])
def api_novo():
    """Cadastro rápido feito de dentro da ficha: devolve a peça no formato do catálogo."""
    dados, produto_id, erros = cadastrar()
    if not produto_id:
        return jsonify({"ok": False, "erros": erros}), 400
    return jsonify({"ok": True, "produto": {
        "id": produto_id, "codigo": dados["codigo"], "nome": dados["nome"], "tipo": dados["tipo"],
        "tamanho": dados["tamanho"], "cor": dados["cor"],
        "valor": centavos_para_campo(dados["valor_aluguel"]),
        "situacao": "disponivel", "lavagem_desde": None}})


@bp.route("/<int:produto_id>/editar", methods=["GET", "POST"])
def editar(produto_id):
    produto = buscar(produto_id)
    dados = dict(produto, valor_texto=centavos_para_campo(produto["valor_aluguel"]))
    if request.method == "POST":
        dados, erros = ler_formulario()
        dados["codigo"] = produto["codigo"]      # o código não muda (pode estar em etiquetas)
        if not erros:
            db = get_db()
            db.execute(
                "UPDATE produtos SET nome = ?, tipo = ?, tamanho = ?, cor = ?, valor_aluguel = ? WHERE id = ?",
                (dados["nome"], dados["tipo"], dados["tamanho"], dados["cor"], dados["valor_aluguel"], produto_id),
            )
            db.commit()
            flash("Peça atualizada.", "sucesso")
            return redirect(url_for("produtos.lista"))
        for e in erros:
            flash(e, "erro")
    return render_template("produtos/form.html", produto=produto, dados=dados, tipos=TIPOS)


@bp.route("/<int:produto_id>/excluir", methods=["POST"])
def excluir(produto_id):
    produto = buscar(produto_id)
    db = get_db()
    usado = db.execute("SELECT 1 FROM aluguel_itens WHERE produto_id = ? LIMIT 1",
                       (produto_id,)).fetchone()
    if usado:
        # Mantém o histórico das fichas: a peça só deixa de aparecer para novos aluguéis.
        db.execute("UPDATE produtos SET ativo = 0 WHERE id = ?", (produto_id,))
        flash(f"“{produto['nome']}” aparece em fichas já salvas, então foi arquivada "
              "(não aparece mais para novos aluguéis).", "info")
    else:
        db.execute("DELETE FROM produtos WHERE id = ?", (produto_id,))
        flash(f"“{produto['nome']}” foi excluída.", "sucesso")
    db.commit()
    return redirect(url_for("produtos.lista"))


@bp.route("/lavagem")
def lavagem():
    db = get_db()
    pecas = db.execute(
        """SELECT p.*, f.cliente_nome, f.id AS ficha_id
             FROM produtos p LEFT JOIN v_fichas f ON f.id = p.lavagem_ficha_id
            WHERE p.em_lavagem = 1
            ORDER BY p.lavagem_desde, p.nome COLLATE NOCASE""").fetchall()
    # Próxima saída marcada para cada peça, para priorizar a lavagem.
    proximas = {}
    for p in pecas:
        proximas[p["id"]] = db.execute(
            """SELECT f.id, f.data_saida, f.cliente_nome
                 FROM aluguel_itens i JOIN v_fichas f ON f.id = i.aluguel_id
                WHERE i.produto_id = ? AND f.situacao = 'reservada' AND f.data_saida >= ?
                ORDER BY f.data_saida LIMIT 1""", (p["id"], date.today().isoformat())).fetchone()
    return render_template("produtos/lavagem.html", pecas=pecas, proximas=proximas)


@bp.route("/<int:produto_id>/disponibilizar", methods=["POST"])
def disponibilizar(produto_id):
    produto = buscar(produto_id)
    db = get_db()
    db.execute("UPDATE produtos SET em_lavagem = 0, lavagem_desde = NULL, lavagem_ficha_id = NULL"
               " WHERE id = ?", (produto_id,))
    db.commit()
    flash(f"“{produto['nome']}” está disponível novamente.", "sucesso")
    return redirect(url_for("produtos.lavagem"))


@bp.route("/<int:produto_id>/reativar", methods=["POST"])
def reativar(produto_id):
    produto = buscar(produto_id)
    db = get_db()
    db.execute("UPDATE produtos SET ativo = 1 WHERE id = ?", (produto_id,))
    db.commit()
    flash(f"“{produto['nome']}” foi reativada.", "sucesso")
    return redirect(url_for("produtos.lista", inativos=1))


@bp.route("/disponibilidade")
def disponibilidade():
    """Peças livres num período, pelo mesmo critério da ficha: fichas não canceladas e ainda não
    devolvidas ocupam a peça da saída até a devolução (ou até hoje, se a devolução estiver atrasada)."""
    hoje = date.today()
    de = parse_data(request.args.get("de")) or hoje
    ate = parse_data(request.args.get("ate")) or de
    if ate < de:
        de, ate = ate, de
    q = request.args.get("q", "").strip()
    so_livres = request.args.get("livres") == "1"
    db = get_db()

    sql = "SELECT * FROM produtos WHERE ativo = 1"
    params = []
    if q:
        sql += " AND (nome LIKE ? OR codigo LIKE ? OR cor LIKE ? OR tipo LIKE ? OR tamanho LIKE ?)"
        params += [f"%{q}%"] * 5
    sql += " ORDER BY tipo, nome COLLATE NOCASE"
    pecas = db.execute(sql, params).fetchall()

    ocupacoes = {}
    for o in db.execute(
            """SELECT i.produto_id, f.id AS ficha_id, f.cliente_nome, f.data_saida, f.data_devolucao, f.situacao,
                      f.data_devolucao < :hoje AS atrasada
                 FROM aluguel_itens i JOIN v_fichas f ON f.id = i.aluguel_id
                WHERE f.situacao NOT IN ('devolvida', 'cancelada')
                  AND f.data_saida <= :ate AND MAX(f.data_devolucao, :hoje) >= :de
                ORDER BY f.data_saida""", {"de": de.isoformat(), "ate": ate.isoformat(), "hoje": hoje.isoformat()}):
        ocupacoes.setdefault(o["produto_id"], []).append(o)

    fora = alugadas_hoje(db)
    linhas = [{"peca": p, "ocupacoes": ocupacoes.get(p["id"], []), "lavagem": bool(p["em_lavagem"]),
               "fora_agora": fora.get(p["id"])} for p in pecas]
    livres = sum(1 for l in linhas if not l["ocupacoes"])
    if so_livres:
        linhas = [l for l in linhas if not l["ocupacoes"]]
    return render_template("produtos/disponibilidade.html", linhas=linhas, de=de, ate=ate, q=q,
                           so_livres=so_livres, livres=livres, total=len(pecas))
