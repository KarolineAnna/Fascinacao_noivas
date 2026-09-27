"""Contrato: multa por atraso, caução e termo de responsabilidade."""
import os
import sqlite3
import sys
from datetime import timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402
from test_fluxos import HOJE, criar_produto, dados_ficha  # noqa: E402


def d(n):
    return (HOJE + timedelta(days=n)).isoformat()


@pytest.fixture
def app(tmp_path):
    return create_app(str(tmp_path / "t.db"))


@pytest.fixture
def c(app):
    return app.test_client()


def ficha(app, fid=1):
    con = sqlite3.connect(app.config["DATABASE"])
    con.row_factory = sqlite3.Row
    return con.execute("SELECT * FROM v_fichas WHERE id = ?", (fid,)).fetchone()


def ficha_atrasada(c, dias=3, valor="1000"):
    """Ficha retirada com devolução prevista há `dias` dias (aluguel de R$ 1.000,00)."""
    criar_produto(c, "-", "Vestido", valor)
    c.post("/fichas/nova", data=dados_ficha(valor_cobrado=[valor], data_saida=d(-dias - 2),
                                            data_devolucao=d(-dias), situacao="retirada"))


def movimentos_hoje(c):
    html = c.get(f"/financeiro/?modo=dia&dia={HOJE.isoformat()}").data.decode()
    return html.split("<h2>Movimentações</h2>")[1].split("<h2>Por categoria</h2>")[0]


def test_multa_calculada_ao_devolver_com_atraso(app, c):
    ficha_atrasada(c, dias=3)
    # antes de devolver: a ficha e a Início mostram a multa acumulada até hoje (padrão 10%/dia)
    assert "R$ 300,00 até hoje" in c.get("/fichas/1").data.decode()
    assert "multa até hoje" in c.get("/").data.decode() and "R$ 300,00" in c.get("/").data.decode()
    assert 'data-atraso-dias="3"' in c.get("/fichas/1").data.decode()

    r = c.post("/fichas/1/controle", data={"campo": "devolvida", "ligar": "1"}, follow_redirects=True)
    assert "Multa por atraso de R$ 300,00 a receber" in r.data.decode()
    f = ficha(app)
    assert f["multa_valor"] == 30000 and not f["multa_paga"] and f["data_devolvida"] == HOJE.isoformat()
    # multa pendente aparece no "a receber"
    fin = c.get("/financeiro/").data.decode()
    receber = fin.split('id="a-receber"')[1]
    assert 'class="direita num valor-saida">R$ 300,00' in receber                  # coluna Multa
    assert "R$ 1.300,00" in receber                                                 # restante + multa

    # pagar a multa: entra no financeiro
    c.post("/fichas/1/controle", data={"campo": "multa", "ligar": "1", "valor": "300,00", "forma": "Pix", "data": HOJE.isoformat()})
    assert ficha(app)["multa_paga"] == 1
    assert "Multa por atraso da ficha nº 1" in movimentos_hoje(c)
    # desmarcar o pagamento tira do financeiro
    c.post("/fichas/1/controle", data={"campo": "multa", "ligar": "0"})
    assert "Multa por atraso da ficha" not in movimentos_hoje(c)


def test_devolucao_com_multa_ajustada_paga_e_caucao_devolvida(app, c):
    ficha_atrasada(c, dias=2)
    c.post("/fichas/1/controle", data={"campo": "caucao", "ligar": "1", "valor": "200", "forma": "Dinheiro", "data": HOJE.isoformat()})
    assert ficha(app)["caucao_valor"] == 20000
    assert 'data-caucao="200,00"' in c.get("/fichas/1").data.decode()

    r = c.post("/fichas/1/controle", data={
        "campo": "devolvida", "ligar": "1", "multa_valor": "150,00",
        "multa_agora": "1", "multa_forma": "Pix", "multa_data": HOJE.isoformat(),
        "caucao_agora": "1", "caucao_devolvido": "150,00", "caucao_forma": "Dinheiro", "caucao_data": HOJE.isoformat()},
        follow_redirects=True)
    assert "Multa de R$ 150,00 registrada como paga" in r.data.decode() and "Caução devolvida: R$ 150,00" in r.data.decode()
    f = ficha(app)
    assert f["multa_valor"] == 15000 and f["multa_paga"] and f["caucao_devolvida"] and f["caucao_devolvido_valor"] == 15000
    mov = movimentos_hoje(c)
    assert "Caução da ficha nº 1" in mov and "Devolução da caução da ficha nº 1" in mov and "Multa por atraso" in mov
    assert "retidos R$ 50,00" in c.get("/fichas/1").data.decode()

    # fechamento: dinheiro = +200 (caução) −150 (devolução); pix = +150 (multa)
    from app.views.financeiro import esperado_por_forma
    with app.test_request_context():
        linhas = {r["forma"]: r for r in esperado_por_forma(HOJE)}
    assert linhas["Dinheiro"]["esperado"] == 5000 and linhas["Dinheiro"]["saidas"] == 15000
    assert linhas["Pix"]["esperado"] == 15000

    # relatórios: caução não é faturamento, só o que ficou retido (R$ 50) + multa (R$ 150)
    rel = c.get("/relatorios/?periodo=3").data.decode()
    assert f'data-aluguel="R$ 200,00"' in rel


def test_validacoes_da_devolucao(app, c):
    ficha_atrasada(c, dias=1)
    c.post("/fichas/1/controle", data={"campo": "caucao", "ligar": "1", "valor": "100", "forma": "Pix", "data": HOJE.isoformat()})
    r = c.post("/fichas/1/controle", data={"campo": "devolvida", "ligar": "1", "multa_agora": "1", "multa_data": HOJE.isoformat()},
               follow_redirects=True)
    assert "forma de pagamento da multa" in r.data.decode() and ficha(app)["situacao"] == "retirada"
    r = c.post("/fichas/1/controle", data={"campo": "devolvida", "ligar": "1", "caucao_agora": "1", "caucao_devolvido": "500",
                                            "caucao_forma": "Pix", "caucao_data": HOJE.isoformat()}, follow_redirects=True)
    assert "não pode ser maior que a caução" in r.data.decode()


def test_isentar_desfazer_e_sem_atraso(app, c):
    ficha_atrasada(c, dias=4)
    c.post("/fichas/1/controle", data={"campo": "devolvida", "ligar": "1", "multa_valor": "0"})
    assert ficha(app)["multa_valor"] == 0                             # isentada na própria devolução
    c.post("/fichas/1/controle", data={"campo": "devolvida", "ligar": "0"})
    c.post("/fichas/1/controle", data={"campo": "devolvida", "ligar": "1"})
    assert ficha(app)["multa_valor"] == 40000                         # recalculada: 4 dias × R$ 100
    c.post("/fichas/1/controle", data={"campo": "isentar_multa", "ligar": "1"})
    assert ficha(app)["multa_valor"] == 0
    c.post("/fichas/1/controle", data={"campo": "devolvida", "ligar": "0"})
    f = ficha(app)
    assert f["data_devolvida"] is None and f["multa_valor"] == 0

    # devolução no prazo: sem multa
    criar_produto(c, "-", "Terno", "300")
    c.post("/fichas/nova", data=dados_ficha(cpf="111.444.777-35", nome="Ana", produto_id=["2"], valor_cobrado=["300"],
                                            data_saida=d(-1), data_devolucao=d(2), situacao="retirada"))
    c.post("/fichas/2/controle", data={"campo": "devolvida", "ligar": "1"})
    assert ficha(app, 2)["multa_valor"] == 0
    # ficha cadastrada já como devolvida (registro antigo): sem multa
    c.post("/fichas/nova", data=dados_ficha(cpf="123.456.789-09", nome="Bia", produto_id=["2"], valor_cobrado=["300"],
                                            data_saida=d(-30), data_devolucao=d(-28), situacao="devolvida"))
    assert ficha(app, 3)["multa_valor"] == 0 and ficha(app, 3)["data_devolvida"] == d(-28)


def test_caucao_nao_pode_ser_removida_depois_de_devolvida(app, c):
    ficha_atrasada(c, dias=0)
    c.post("/fichas/1/controle", data={"campo": "caucao", "ligar": "1", "valor": "100", "forma": "Pix", "data": HOJE.isoformat()})
    c.post("/fichas/1/controle", data={"campo": "caucao_devolvida", "ligar": "1", "forma": "Pix", "data": HOJE.isoformat()})
    assert ficha(app)["caucao_devolvido_valor"] == 10000              # sem valor informado: devolve tudo
    r = c.post("/fichas/1/controle", data={"campo": "caucao", "ligar": "0"}, follow_redirects=True)
    assert "Desmarque “Caução devolvida”" in r.data.decode() and ficha(app)["caucao_valor"] == 10000


def test_configuracao_da_multa_e_termo(app, c):
    html = c.get("/configuracoes/").data.decode()
    assert "Contrato e multa por atraso" in html and "DEVOLUÇÃO" in html and 'value="10"' in html
    r = c.post("/configuracoes/contrato", data={"multa_tipo": "percentual", "multa_valor": "150"}, follow_redirects=True)
    assert "não pode passar de 100%" in r.data.decode()
    c.post("/configuracoes/contrato", data={"multa_tipo": "valor", "multa_valor": "50,00",
                                            "termo_texto": "Devolver até {devolucao}. Multa: {multa_dia}/dia. {caucao}. Cliente: {cliente}."})
    ficha_atrasada(c, dias=2)
    assert "R$ 100,00 até hoje" in c.get("/fichas/1").data.decode()      # 2 dias × R$ 50
    impressa = c.get("/fichas/1/imprimir").data.decode()
    assert "Termo de responsabilidade" in impressa
    assert f"Devolver até {HOJE.fromisoformat(d(-2)).strftime('%d/%m/%Y')}. Multa: R$ 50,00/dia. não foi deixada caução. Cliente: Maria Souza." in impressa
    assert "sem caução" in impressa
    # restaurar o texto padrão
    c.post("/configuracoes/contrato", data={"acao": "padrao"})
    impressa = c.get("/fichas/1/imprimir").data.decode()
    assert "DANOS" in impressa and "LIMPEZA" in impressa and "R$ 50,00 por dia de atraso" in impressa
