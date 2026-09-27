"""Testes de Financeiro, fechamento de caixa, Vendas, categorias, Disponibilidade e menu lateral."""
import os
import sqlite3
import sys
from datetime import timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402
from test_fluxos import HOJE, criar_produto, dados_ficha  # noqa: E402


@pytest.fixture
def app(tmp_path):
    return create_app(str(tmp_path / "teste.db"))


@pytest.fixture
def cliente(app):
    return app.test_client()


def categoria_id(app, grupo, nome):
    con = sqlite3.connect(app.config["DATABASE"])
    return con.execute("SELECT id FROM categorias WHERE grupo = ? AND nome = ?", (grupo, nome)).fetchone()[0]


def dia(url):
    return f"{url}?modo=dia&dia={HOJE.isoformat()}"


def test_lancamentos_manuais(app):
    c = app.test_client()
    lav = categoria_id(app, "financeiro", "Lavanderia")
    r = c.post("/financeiro/lancamentos/novo", data={"tipo": "saida", "data": HOJE.isoformat()})
    html = r.data.decode()
    assert "Informe a descrição" in html and "Escolha a categoria" in html and "valor maior que zero" in html

    c.post("/financeiro/lancamentos/novo", data={"tipo": "saida", "data": HOJE.isoformat(), "descricao": "Pagamento da lavanderia",
                                                 "categoria_id": lav, "valor": "80,00", "forma": "Dinheiro"})
    c.post("/financeiro/lancamentos/novo", data={"tipo": "entrada", "data": HOJE.isoformat(), "descricao": "Troco inicial",
                                                 "categoria_id": categoria_id(app, "financeiro", "Outros"), "valor": "50",
                                                 "forma": "Dinheiro", "observacao": "fundo de caixa"})
    html = c.get(dia("/financeiro/")).data.decode()
    assert "Pagamento da lavanderia" in html and "fundo de caixa" in html
    assert "R$ 50,00" in html and "R$ 80,00" in html and "-R$ 30,00" in html      # saldo = 50 - 80

    so_saidas = c.get(dia("/financeiro/") + "&tipo=saida").data.decode()
    assert "Pagamento da lavanderia" in so_saidas and "Troco inicial" not in so_saidas
    assert "Troco inicial" not in c.get(dia("/financeiro/") + f"&categoria={lav}").data.decode()

    r = c.post("/financeiro/lancamentos/1/editar", data={"tipo": "saida", "data": HOJE.isoformat(), "descricao": "Lavanderia (ajuste)",
                                                          "categoria_id": lav, "valor": "90", "forma": "Pix"}, follow_redirects=True)
    assert "Lavanderia (ajuste)" in r.data.decode() and "R$ 90,00" in r.data.decode()
    r = c.post("/financeiro/lancamentos/1/excluir", follow_redirects=True)
    assert "excluído" in r.data.decode()
    assert "Lavanderia (ajuste)" not in c.get(dia("/financeiro/")).data.decode()


def test_vendas_e_integracao_com_financeiro(app):
    c = app.test_client()
    natura, mel = categoria_id(app, "venda", "Natura"), categoria_id(app, "venda", "Mel e própolis")
    c.post("/vendas/produtos/novo", data={"nome": "Kaiak 100 ml", "categoria_id": natura, "preco": "129,90"})
    c.post("/vendas/produtos/novo", data={"nome": "Mel 500 g", "categoria_id": mel, "preco": "35"})
    r = c.post("/vendas/produtos/novo", data={"nome": "", "categoria_id": "", "preco": "x"})
    assert "Informe o nome" in r.data.decode() and "Escolha a marca" in r.data.decode()

    # venda sem cliente, com quantidades
    r = c.post("/vendas/nova", data={"produto_id": ["1", "2"], "quantidade": ["2", "3"], "forma": "Pix",
                                     "data": HOJE.isoformat(), "cliente_nome": "", "cliente_id": ""})
    assert r.status_code == 302 and r.headers["Location"].endswith("/vendas/1")
    assert "R$ 364,80" in c.get("/vendas/1").data.decode()           # 2 x 129,90 + 3 x 35,00
    r = c.post("/vendas/nova", data={"produto_id": ["1"], "quantidade": ["0"], "forma": "", "data": HOJE.isoformat()})
    assert "Quantidade inválida" in r.data.decode() and "forma de pagamento" in r.data.decode()

    # venda com cliente cadastrado
    criar_produto(c, "T01", "Terno", "100")
    c.post("/fichas/nova", data=dados_ficha(valor_cobrado=["100"]))
    c.post("/vendas/nova", data={"produto_id": ["2"], "quantidade": ["1"], "forma": "Dinheiro",
                                 "data": HOJE.isoformat(), "cliente_nome": "Maria Souza", "cliente_id": "1"})
    assert 'href="/clientes/1"' in c.get("/vendas/2").data.decode()

    # lista com filtros e total
    assert "R$ 399,80" in c.get(dia("/vendas/")).data.decode()      # 364,80 + 35,00
    so_natura = c.get(dia("/vendas/") + f"&categoria={natura}").data.decode()
    assert "R$ 364,80" in so_natura and "Maria Souza" not in so_natura
    assert "R$ 35,00" in c.get(dia("/vendas/") + "&forma=Dinheiro").data.decode()

    # entra no financeiro como "Venda", sem editar/excluir por lá
    fin = c.get(dia("/financeiro/")).data.decode()
    assert "Venda nº 1" in fin and "Venda nº 2 · Maria Souza" in fin and "Abrir venda" in fin
    trecho = fin.split("Venda nº 1")[1].split("</tr>")[0]
    assert "Editar" not in trecho and "Excluir" not in trecho
    assert "Venda nº 1" in c.get(dia("/financeiro/") + "&categoria=venda").data.decode()

    # editar a venda muda o financeiro; excluir tira de lá
    c.post("/vendas/2/editar", data={"produto_id": ["2"], "quantidade": ["2"], "forma": "Dinheiro",
                                     "data": HOJE.isoformat(), "cliente_nome": "", "cliente_id": ""})
    assert "R$ 70,00" in c.get("/vendas/2").data.decode()
    r = c.post("/vendas/2/excluir", follow_redirects=True)
    assert "também saiu do financeiro" in r.data.decode()
    assert "Venda nº 2" not in c.get(dia("/financeiro/")).data.decode()
    # produto já vendido é arquivado, não apagado
    r = c.post("/vendas/produtos/1/excluir", follow_redirects=True)
    assert "foi arquivado" in r.data.decode()
    assert "Kaiak" not in c.get("/vendas/produtos/").data.decode()
    assert "Arquivado" in c.get("/vendas/produtos/?inativos=1").data.decode()


def test_fechamento_de_caixa(app):
    c = app.test_client()
    criar_produto(c, "T01", "Terno", "500")
    # R$ 500 em dinheiro da ficha - R$ 80 em dinheiro para a lavanderia = R$ 420 esperado em dinheiro
    c.post("/fichas/nova", data=dados_ficha(valor_cobrado=["500"], entrada_paga="1", valor_entrada="500",
                                            data_entrada=HOJE.isoformat(), forma_entrada="Dinheiro"))
    c.post("/financeiro/lancamentos/novo", data={"tipo": "saida", "data": HOJE.isoformat(), "descricao": "Lavanderia",
                                                 "categoria_id": categoria_id(app, "financeiro", "Lavanderia"),
                                                 "valor": "80", "forma": "Dinheiro"})
    c.post("/vendas/produtos/novo", data={"nome": "Mel", "categoria_id": categoria_id(app, "venda", "Mel e própolis"), "preco": "30"})
    c.post("/vendas/nova", data={"produto_id": ["1"], "quantidade": ["1"], "forma": "Pix", "data": HOJE.isoformat()})

    from app.views.financeiro import esperado_por_forma
    with app.test_request_context():
        linhas = {r["forma"]: r for r in esperado_por_forma(HOJE)}
    assert linhas["Dinheiro"]["esperado"] == 42000 and linhas["Dinheiro"]["saidas"] == 8000
    assert linhas["Pix"]["esperado"] == 3000 and linhas["Pix"]["vendas"] == 3000

    html = c.get(f"/financeiro/fechamento?data={HOJE.isoformat()}").data.decode()
    assert "R$ 420,00" in html and "R$ 450,00" in html              # total esperado = 420 + 30
    r = c.post("/financeiro/fechamento", data={"data": HOJE.isoformat(), "contado_Dinheiro": "410,00",
                                               "contado_Pix": "30", "observacao": "faltou troco"}, follow_redirects=True)
    html = r.data.decode()
    assert "fechado" in html and "Caixa fechado" in html and 'value="410,00"' in html and "faltou troco" in html
    assert "-R$ 10,00" in html                                       # últimos fechamentos: diferença


def test_categorias_nas_configuracoes(app):
    c = app.test_client()
    html = c.get("/configuracoes/").data.decode()
    for nome in ["Lavanderia", "Costureira", "Aluguel do imóvel", "Contas", "Compra de peças", "Outros",
                 "Natura", "Avon", "Mel e própolis"]:
        assert f'value="{nome}"' in html, nome
    c.post("/configuracoes/categorias", data={"grupo": "venda", "nome": "O Boticário"})
    assert 'value="O Boticário"' in c.get("/configuracoes/").data.decode()
    r = c.post("/configuracoes/categorias", data={"grupo": "venda", "nome": "natura"}, follow_redirects=True)
    assert "já existe" in r.data.decode()
    lav = categoria_id(app, "financeiro", "Lavanderia")
    c.post(f"/configuracoes/categorias/{lav}/renomear", data={"nome": "Lavanderia Bolha"})
    c.post("/financeiro/lancamentos/novo", data={"tipo": "saida", "data": HOJE.isoformat(), "descricao": "x",
                                                 "categoria_id": lav, "valor": "1", "forma": "Pix"})
    assert "Lavanderia Bolha" in c.get(dia("/financeiro/")).data.decode()
    r = c.post(f"/configuracoes/categorias/{lav}/remover", follow_redirects=True)
    assert "está em uso" in r.data.decode()
    avon = categoria_id(app, "venda", "Avon")
    c.post(f"/configuracoes/categorias/{avon}/remover")
    assert 'value="Avon"' not in c.get("/configuracoes/").data.decode()


def test_disponibilidade(cliente):
    c = cliente
    for cod in ("V01", "V02", "V03"):
        criar_produto(c, cod, f"Vestido {cod}", "100")
    d = lambda n: (HOJE + timedelta(days=n)).isoformat()
    c.post("/fichas/nova", data=dados_ficha(produto_id=["1"], valor_cobrado=["100"], data_saida=d(5), data_devolucao=d(8)))
    c.post("/fichas/nova", data=dados_ficha(produto_id=["2"], valor_cobrado=["100"], data_saida=d(-6), data_devolucao=d(-2),
                                            situacao="retirada"))              # atrasada
    c.post("/fichas/nova", data=dados_ficha(produto_id=["3"], valor_cobrado=["100"], data_saida=d(5), data_devolucao=d(8),
                                            situacao="cancelada"))
    html = c.get(f"/produtos/disponibilidade?de={d(6)}&ate={d(7)}").data.decode()
    linha = lambda cod: html.split(f'<span class="codigo">{cod}</span>')[1].split("</tr>")[0]
    assert "Ocupada" in linha("001") and "Ficha nº 1" in linha("001")
    # datas futuras seguem as datas das fichas; a peça atrasada ganha um aviso de que ainda não voltou
    assert "Disponível" in linha("002") and "ainda não foi devolvida" in linha("002")
    assert "Disponível" in linha("003") and "ainda não" not in linha("003")   # ficha cancelada não conta
    hoje = c.get(f"/produtos/disponibilidade?de={d(0)}&ate={d(1)}").data.decode()
    trecho = hoje.split('<span class="codigo">002</span>')[1].split("</tr>")[0]
    assert "Ocupada" in trecho and "atrasada" in trecho                      # hoje: continua ocupada
    livres = c.get(f"/produtos/disponibilidade?de={d(6)}&ate={d(7)}&livres=1").data.decode()
    assert "Vestido V03" in livres and "Vestido V01" not in livres


def menu_ativo(html):
    return [t.split('title="')[1].split('"')[0] for t in html.split('class="menu-item ativo"')[1:]]


def test_menu_lateral(cliente):
    c = cliente
    html = c.get("/vendas/nova").data.decode()
    for secao in ["Aluguel", "Vendas", "Financeiro"]:
        assert f'<div class="menu-titulo">{secao}</div>' in html
    for rotulo in ["Início", "Fichas", "Clientes", "Produtos de aluguel", "Saídas do dia", "Devoluções do dia",
                   "Disponibilidade", "Peças em lavagem", "Nova venda", "Vendas", "Produtos à venda",
                   "Financeiro", "Fechar caixa", "Configurações"]:
        assert f'<span class="menu-rotulo">{rotulo}</span>' in html, rotulo
    assert menu_ativo(html) == ["Nova venda"] and 'id="menu-recolher"' in html
    for url, esperado in [("/", "Início"), ("/fichas/nova", "Fichas"), ("/produtos/lavagem", "Peças em lavagem"),
                          ("/produtos/novo", "Produtos de aluguel"), ("/financeiro/fechamento", "Fechar caixa"),
                          ("/vendas/produtos/novo", "Produtos à venda"), ("/configuracoes/", "Configurações")]:
        assert menu_ativo(c.get(url).data.decode()) == [esperado], url
