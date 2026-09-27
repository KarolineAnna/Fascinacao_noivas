"""Botão "Limpar filtros" nas telas com filtros."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402

TELAS = [
    ("/fichas/", "?q=maria&situacao=reservada", "/fichas/"),
    ("/clientes/", "?q=123", "/clientes/"),
    ("/produtos/", "?q=terno&tipo=Terno&situacao=alugada&inativos=1", "/produtos/"),
    ("/produtos/disponibilidade", "?de=2026-10-01&ate=2026-10-05&q=vestido&livres=1", "/produtos/disponibilidade"),
    ("/vendas/produtos/", "?q=kaiak&categoria=7", "/vendas/produtos/"),
    ("/vendas/", "?modo=dia&dia=2026-09-20&forma=Pix", "/vendas/?modo=dia"),
    ("/financeiro/", "?modo=periodo&de=2026-09-01&ate=2026-09-30&tipo=saida&categoria=1&forma=Pix",
     "/financeiro/?modo=periodo"),
]


@pytest.fixture
def cliente(tmp_path):
    return create_app(str(tmp_path / "t.db")).test_client()


@pytest.mark.parametrize("url,filtros,limpo", TELAS)
def test_limpar_filtros(cliente, url, filtros, limpo):
    sem = cliente.get(url).data.decode()
    assert sem.count("Limpar filtros") == 1 and 'aria-disabled="true"' in sem      # sempre visível, apagado

    com = cliente.get(url + filtros).data.decode()
    assert f'class="btn btn-texto btn-limpar" href="{limpo}"' in com, url            # ativo, mantém Dia/Mês/Período
    assert "aria-disabled" not in com.split("Limpar filtros")[0].rsplit("<", 3)[-3:][0]
    assert cliente.get(limpo).status_code == 200


def test_so_o_modo_nao_conta_como_filtro(cliente):
    html = cliente.get("/financeiro/?modo=dia").data.decode()
    assert 'aria-disabled="true"' in html.split("Limpar filtros")[0][-400:]
