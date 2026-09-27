"""Código das peças de aluguel gerado automaticamente."""
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402


def peca(c, nome, **extra):
    return c.post("/produtos/novo", data={"nome": nome, "valor_aluguel": "100", **extra}, follow_redirects=True)


def codigos(app):
    con = sqlite3.connect(app.config["DATABASE"])
    return [r[0] for r in con.execute("SELECT codigo FROM produtos ORDER BY id")]


def test_sequencia_em_acervo_vazio(tmp_path):
    app = create_app(str(tmp_path / "t.db"))
    c = app.test_client()
    form = c.get("/produtos/novo").data.decode()
    assert 'name="codigo"' not in form and "001" in form and "Gerado automaticamente" in form
    r = peca(c, "Vestido sereia", codigo="XYZ")          # um código enviado à mão é ignorado
    assert "cadastrada com o código 001" in r.data.decode()
    peca(c, "Terno slim")
    assert codigos(app) == ["001", "002"]


def test_segue_o_padrao_dos_codigos_existentes(tmp_path):
    app = create_app(str(tmp_path / "t.db"))
    con = sqlite3.connect(app.config["DATABASE"])
    con.executemany("INSERT INTO produtos (codigo, nome) VALUES (?, ?)",
                    [("01", "Vestido Terracota"), ("02", "Vestido Verde Oliva"), ("05", "Paletó Grotto"), ("V01", "Antigo")])
    con.commit()
    c = app.test_client()
    assert "06" in c.get("/produtos/novo").data.decode()
    peca(c, "Vestido novo")
    assert codigos(app)[-1] == "06"                       # próximo depois do maior, com 2 dígitos


def test_codigo_nao_muda_na_edicao(tmp_path):
    app = create_app(str(tmp_path / "t.db"))
    c = app.test_client()
    peca(c, "Vestido", tipo="Vestido de noiva")
    form = c.get("/produtos/1/editar").data.decode()
    assert 'name="codigo"' not in form and "O código não muda" in form
    c.post("/produtos/1/editar", data={"codigo": "999", "nome": "Vestido editado", "tipo": "Terno", "valor_aluguel": "200"})
    assert codigos(app) == ["001"]
    assert "Vestido editado" in c.get("/produtos/").data.decode()


def test_cadastro_rapido_na_ficha_sem_campo_de_codigo(tmp_path):
    app = create_app(str(tmp_path / "t.db"))
    c = app.test_client()
    js = c.get("/static/js/ficha.js").data.decode()
    assert 'name="codigo"' not in js and "código gerado automaticamente" in js
