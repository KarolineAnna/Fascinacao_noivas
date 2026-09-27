import os
import sys
from datetime import date

from flask import Flask, request, url_for

from . import contrato, db, pecas, util

NOME_LOJA = "Fascinação Noivas"


# No computador da loja os dados ficam FORA da pasta do programa, para que atualizar o
# programa (trocar o .exe) nunca mexa no banco nem nos backups.
PASTA_DADOS_LOJA = r"C:\Fascinação Noivas Dados"


def pasta_de_dados():
    """Pasta do banco e dos backups.

    - Executável: C:\\Fascinação Noivas Dados (ou a variável FASCINACAO_DADOS, se definida).
    - Desenvolvimento (python iniciar.py): pasta "dados" na raiz do projeto.
    """
    if os.environ.get("FASCINACAO_DADOS"):
        pasta = os.environ["FASCINACAO_DADOS"]
    elif getattr(sys, "frozen", False):
        pasta = PASTA_DADOS_LOJA
    else:
        pasta = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dados")
    os.makedirs(pasta, exist_ok=True)
    trazer_dados_antigos(pasta)
    return pasta


def trazer_dados_antigos(pasta):
    """Versões anteriores do executável guardavam os dados em "dados" ao lado do .exe.
    Se o banco novo ainda não existe e o antigo existe, copia (sem apagar o antigo)."""
    if not getattr(sys, "frozen", False):
        return
    novo = os.path.join(pasta, "fascinacao.db")
    antigo = os.path.join(os.path.dirname(sys.executable), "dados", "fascinacao.db")
    if not os.path.exists(novo) and os.path.exists(antigo):
        import shutil
        shutil.copy2(antigo, novo)


def create_app(database=None):
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.urandom(24)
    app.config["DATABASE"] = database or os.path.join(pasta_de_dados(), "fascinacao.db")

    db.init_db(app.config["DATABASE"])
    app.teardown_appcontext(db.close_db)

    app.jinja_env.filters["brl"] = util.formatar_brl
    app.jinja_env.filters["cpf"] = util.formatar_cpf
    app.jinja_env.filters["data"] = util.formatar_data
    app.jinja_env.filters["data_iso"] = lambda v: util.parse_data(v) or date.today()
    app.jinja_env.filters["campo_valor"] = util.centavos_para_campo

    @app.context_processor
    def globais():
        return {"NOME_LOJA": NOME_LOJA, "SITUACOES": util.SITUACOES,
                "STATUS_FIN": util.STATUS_FINANCEIRO, "SITUACOES_PECA": pecas.SITUACOES_PECA,
                "hoje": date.today(),
                "formas_pagamento": lambda: db.formas_de_pagamento(db.get_db()),
                # contrato: multa que a ficha teria se voltasse hoje, e o texto da multa por dia
                "previa_multa": lambda f: contrato.previa(db.get_db(), f),
                "texto_multa": lambda total: contrato.texto_multa(db.get_db(), total),
                "termo_contrato": lambda f: contrato.termo(db.get_db(), f)}

    PAIS = {
        "fichas.ver": "fichas.lista", "clientes.ver": "clientes.lista",
        "produtos.novo": "produtos.lista", "produtos.editar": "produtos.lista",
        "vendas.ver": "vendas.lista", "vendas.editar": "vendas.lista",
        "vendas.novo_produto": "vendas.produtos", "vendas.editar_produto": "vendas.produtos",
        "financeiro.novo_lancamento": "financeiro.lista", "financeiro.editar_lancamento": "financeiro.lista",
    }

    @app.context_processor
    def navegacao():
        def voltar_padrao():
            ep = request.endpoint or ""
            if ep == "fichas.editar":
                return url_for("fichas.ver", **request.view_args)
            return url_for(PAIS.get(ep, "agenda.inicio"))
        return {"voltar_padrao": voltar_padrao}

    @app.route("/saude")
    def saude():
        # Usado pelo inicializador para saber se o sistema já está aberto.
        return "fascinacao-noivas", 200, {"Content-Type": "text/plain"}

    @app.route("/caixa/")
    def caixa_antigo():
        # O antigo "Fluxo de caixa" agora é o Financeiro.
        from flask import redirect
        return redirect(url_for("financeiro.lista", **request.args))

    from .views import agenda, clientes, configuracoes, financeiro, fichas, produtos, relatorios, vendas
    app.register_blueprint(configuracoes.bp)
    app.register_blueprint(agenda.bp)
    app.register_blueprint(financeiro.bp)
    app.register_blueprint(vendas.bp)
    app.register_blueprint(relatorios.bp)
    app.register_blueprint(produtos.bp)
    app.register_blueprint(clientes.bp)
    app.register_blueprint(fichas.bp)

    return app
