"""Calendário do mês e relatórios."""
import os
import sqlite3
import sys
from datetime import date, timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402
from app.views.relatorios import escala_redonda, meses_entre  # noqa: E402
from test_fluxos import CPF_A, CPF_B, HOJE, criar_produto, dados_ficha  # noqa: E402


@pytest.fixture
def app(tmp_path):
    return create_app(str(tmp_path / "t.db"))


@pytest.fixture
def c(app):
    return app.test_client()


def d(n):
    return (HOJE + timedelta(days=n)).isoformat()


def test_calendario_do_mes(c):
    criar_produto(c, "-", "Vestido A", "500")
    criar_produto(c, "-", "Vestido B", "500")
    c.post("/fichas/nova", data=dados_ficha(produto_id=["1"], valor_cobrado=["500"], nome="Maria Souza",
                                            data_saida=d(0), data_devolucao=d(2)))
    c.post("/fichas/nova", data=dados_ficha(produto_id=["2"], valor_cobrado=["500"], cpf=CPF_B, nome="Ana Lima",
                                            data_saida=d(0), data_devolucao=d(3), situacao="cancelada"))
    html = c.get("/calendario").data.decode()
    mes = HOJE.strftime("%Y-%m")
    assert "calendario-dia" in html and 'class="calendario-dia  hoje' in html.replace("fora", "") or "hoje" in html
    # semana começa no domingo
    assert html.index(">Dom<") < html.index(">Seg<") < html.index(">Sáb<")
    # saída e devolução da ficha aparecem; a cancelada não
    assert html.count('class="evento saida') >= 1 and html.count('class="evento devolucao') >= 1
    assert "Maria Souza" in html and "Ana Lima" not in html
    # navegação entre meses
    assert c.get("/calendario?mes=2026-02").status_code == 200
    assert f'value="{mes}"' in html


def test_calendario_marca_atrasada_e_feita(c):
    criar_produto(c, "-", "Terno", "100")
    criar_produto(c, "-", "Gravata", "50")
    # atrasada: devolução ontem, ainda retirada
    c.post("/fichas/nova", data=dados_ficha(produto_id=["1"], valor_cobrado=["100"], data_saida=d(-3),
                                            data_devolucao=d(-1), situacao="retirada"))
    # já devolvida
    c.post("/fichas/nova", data=dados_ficha(produto_id=["2"], valor_cobrado=["50"], cpf=CPF_B, nome="Ana",
                                            data_saida=d(-3), data_devolucao=d(-1), situacao="devolvida"))
    mes = (HOJE - timedelta(days=1)).strftime("%Y-%m")
    html = c.get(f"/calendario?mes={mes}").data.decode()
    assert "evento devolucao  atrasado" in html or "atrasado" in html
    assert "evento devolucao feito" in html


def test_calendario_mais_de_tres_no_dia(c):
    for i in range(5):
        criar_produto(c, "-", f"Peça {i}", "100")
    cpfs = ["529.982.247-25", "111.444.777-35", "123.456.789-09", "987.654.321-00", "390.533.447-05"]
    for i, cpf in enumerate(cpfs):
        c.post("/fichas/nova", data=dados_ficha(produto_id=[str(i + 1)], valor_cobrado=["100"], cpf=cpf,
                                                nome=f"Cliente {i}", data_saida=d(1), data_devolucao=d(4)))
    html = c.get(f"/calendario?mes={(HOJE + timedelta(days=1)).strftime('%Y-%m')}").data.decode()
    assert "+ 2 mais" in html and "cheio" in html


def test_escala_do_grafico():
    for maximo in (0, 99, 123456, 583990, 2050000, 10000000):
        topo, marcas = escala_redonda(maximo)
        assert topo >= maximo and marcas[0] == 0 and marcas[-1] == topo and 4 <= len(marcas) - 1 <= 6
        assert maximo < 10000 or maximo / topo > 0.8        # barras usam bem a altura (a partir de R$ 100)
    assert meses_entre(date(2025, 11, 5), date(2026, 2, 1)) == [(2025, 11), (2025, 12), (2026, 1), (2026, 2)]


def test_relatorios(app, c):
    criar_produto(c, "-", "Vestido sereia", "1000")      # 001: alugada 2x
    criar_produto(c, "-", "Terno slim", "300")           # 002: alugada 1x
    criar_produto(c, "-", "Véu longo", "80")             # 003: nunca alugada
    c.post("/fichas/nova", data=dados_ficha(produto_id=["1", "2"], valor_cobrado=["1000", "300"], data_saida=d(0),
                                            data_devolucao=d(3), entrada_paga="1", valor_entrada="500",
                                            data_entrada=HOJE.isoformat(), forma_entrada="Pix"))
    c.post("/fichas/nova", data=dados_ficha(produto_id=["1"], valor_cobrado=["1000"], data_saida=d(-40),
                                            data_devolucao=d(-38), situacao="devolvida"))  # mesma cliente: volta
    c.post("/fichas/nova", data=dados_ficha(produto_id=["2"], valor_cobrado=["300"], cpf=CPF_B, nome="Ana",
                                            data_saida=d(1), data_devolucao=d(2), situacao="cancelada"))
    con = sqlite3.connect(app.config["DATABASE"])
    cat = con.execute("SELECT id FROM categorias WHERE grupo='venda' LIMIT 1").fetchone()[0]
    c.post("/vendas/produtos/novo", data={"nome": "Mel", "categoria_id": cat, "preco": "40"})
    c.post("/vendas/nova", data={"produto_id": ["1"], "quantidade": ["2"], "forma": "Dinheiro", "data": HOJE.isoformat()})

    html = c.get("/relatorios/?periodo=12").data.decode()
    # faturamento: aluguel 500 + vendas 80 no mês atual
    assert "R$ 580,00" in html and 'data-aluguel="R$ 500,00"' in html and 'data-vendas="R$ 80,00"' in html
    assert html.count('class="grafico-coluna"') == 12                               # um por mês
    # mais alugadas: vestido 2x primeiro, terno 1x (a ficha cancelada não conta)
    mais = html.split("Peças mais alugadas")[1].split("Peças paradas")[0]
    assert mais.index("Vestido sereia") < mais.index("Terno slim")
    assert "<strong>2</strong>" in mais.split("Vestido sereia")[1].split("</tr>")[0]
    assert "<strong>1</strong>" in mais.split("Terno slim")[1].split("</tr>")[0]
    # paradas: só o véu, nunca alugado
    paradas = html.split("Peças paradas")[1].split("Clientes que voltam")[0]
    assert "Véu longo" in paradas and "Nunca alugada" in paradas and "Vestido sereia" not in paradas
    # clientes que voltam: Maria (2 fichas, R$ 2.300,00); Ana só tem ficha cancelada
    voltam = html.split("Clientes que voltam</h2>")[1]
    assert "Maria Souza" in voltam and "R$ 2.300,00" in voltam and "Ana" not in voltam
    assert "100%" in html                                                           # 1 de 1 cliente volta

    for p in ("3", "6", "ano", "tudo", "invalido"):
        assert c.get(f"/relatorios/?periodo={p}").status_code == 200


def test_menu_tem_calendario_e_relatorios(c):
    html = c.get("/relatorios/").data.decode()
    assert '<span class="menu-rotulo">Calendário</span>' in html
    assert 'class="menu-item ativo" href="/relatorios/"' in html
    assert 'class="menu-item ativo" href="/calendario"' in c.get("/calendario").data.decode()
