"""Testes dos fluxos principais. Rode com:  python -m pytest -q"""
import os
import sys
from datetime import date, timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402
from app.backup import MANTER, fazer_backup, listar  # noqa: E402
from app.util import cpf_valido, formatar_brl, reais_para_centavos  # noqa: E402

CPF_A = "529.982.247-25"
CPF_B = "111.444.777-35"
HOJE = date.today()


@pytest.fixture
def app(tmp_path):
    return create_app(str(tmp_path / "teste.db"))


@pytest.fixture
def cliente(app):
    return app.test_client()


def criar_produto(c, _apelido, nome, valor):
    """Cadastra uma peça. O código é gerado pelo sistema (001, 002... na ordem de cadastro)."""
    r = c.post("/produtos/novo", data={"nome": nome, "tipo": "Terno",
                                        "tamanho": "50", "cor": "Preto", "valor_aluguel": valor})
    assert r.status_code == 302


def dados_ficha(**extra):
    base = {"cpf": CPF_A, "nome": "Maria Souza", "telefone": "(11) 98888-7777",
            "endereco": "Rua das Flores, 10", "produto_id": ["1"], "valor_cobrado": ["800,00"],
            "data_saida": HOJE.isoformat(), "data_devolucao": (HOJE + timedelta(days=3)).isoformat(),
            "situacao": "reservada"}
    base.update(extra)
    return base


def test_util():
    assert cpf_valido(CPF_A) and cpf_valido(CPF_B)
    assert not cpf_valido("123.456.789-00") and not cpf_valido("111.111.111-11")
    assert reais_para_centavos("1.234,56") == 123456
    assert reais_para_centavos("150.5") == 15050
    assert reais_para_centavos("1.200") == 120000
    assert reais_para_centavos("2.800.000") == 280000000
    assert reais_para_centavos("abc") is None
    assert formatar_brl(123456) == "R$ 1.234,56"


def test_todas_as_telas_abrem(cliente):
    for url in ["/", "/saidas", "/devolucoes", "/fichas/", "/fichas/nova", "/clientes/",
                "/produtos/", "/produtos/novo", "/financeiro/", "/financeiro/?modo=dia",
                "/financeiro/?modo=periodo", "/configuracoes/"]:
        r = cliente.get(url, follow_redirects=True)
        assert r.status_code == 200, url


def test_fluxo_completo(cliente):
    c = cliente
    criar_produto(c, "T01", "Terno slim", "800,00")
    criar_produto(c, "G01", "Gravata de seda", "50")

    # validações
    r = c.post("/fichas/nova", data=dados_ficha(cpf="123.456.789-00"))
    assert "CPF inválido".encode() in r.data
    r = c.post("/fichas/nova", data=dados_ficha(data_devolucao=HOJE.isoformat()))
    assert "posterior à data de saída".encode() in r.data
    r = c.post("/fichas/nova", data=dados_ficha(entrada_paga="1", valor_entrada="900",
                                                data_entrada=HOJE.isoformat(), forma_entrada="Pix"))
    assert "maior que o valor do aluguel".encode() in r.data
    r = c.post("/fichas/nova", data=dados_ficha(entrada_paga="1", valor_entrada="300",
                                                data_entrada=HOJE.isoformat()))
    assert "forma de pagamento da entrada".encode() in r.data

    # ficha 1 com entrada em Pix
    r = c.post("/fichas/nova", data=dados_ficha(entrada_paga="1", valor_entrada="300,00",
                                                data_entrada=HOJE.isoformat(), forma_entrada="Pix"))
    assert r.status_code == 302 and r.headers["Location"].endswith("/fichas/1")
    r = c.get("/fichas/1")
    assert "Entrada paga".encode() in r.data and "R$ 500,00".encode() in r.data

    # reaproveita o cliente pelo CPF (sem duplicar)
    j = c.get("/clientes/api/cpf/52998224725").get_json()
    assert j["valido"] and j["cliente"]["nome"] == "Maria Souza"

    # conflito: mesma peça em período sobreposto -> aviso; confirma e salva
    ficha2 = dados_ficha(cpf=CPF_B, nome="João Lima", produto_id=["1", "2"],
                         valor_cobrado=["800,00", "50,00"],
                         data_saida=(HOJE + timedelta(days=1)).isoformat(),
                         data_devolucao=(HOJE + timedelta(days=5)).isoformat())
    r = c.post("/fichas/nova", data=ficha2)
    assert r.status_code == 200 and "já reservada neste período".encode() in r.data
    assert "ficha nº 1".encode() in r.data
    r = c.post("/fichas/nova", data=dict(ficha2, confirmar_conflito="1-1"))
    assert r.status_code == 302 and r.headers["Location"].endswith("/fichas/2")

    # cancelar a ficha 1 libera a peça: nova ficha no período não gera aviso
    c.post("/fichas/1/situacao", data={"situacao": "cancelada"})
    r = c.post("/fichas/nova", data=dados_ficha(cpf=CPF_A, produto_id=["1"],
                                                data_saida=HOJE.isoformat(),
                                                data_devolucao=(HOJE + timedelta(days=1)).isoformat()))
    # a ficha 2 (não cancelada) ainda conflita
    assert "ficha nº 2".encode() in r.data and "ficha nº 1<".encode() not in r.data

    r = c.get("/clientes/")
    assert r.data.count("Maria Souza".encode()) == 1

    # quitação do restante em dinheiro
    r = c.post("/fichas/2/quitar", data={"forma": "Dinheiro"})
    assert r.status_code == 302
    r = c.get("/fichas/2")
    assert "Quitada".encode() in r.data

    # caixa: entrada da ficha cancelada continua; totais por forma
    r = c.get(f"/financeiro/?modo=dia&dia={HOJE.isoformat()}")
    html = r.data.decode()
    assert "R$ 300,00" in html and "R$ 850,00" in html and "R$ 1.150,00" in html
    assert "Pix" in html and "Dinheiro" in html
    r = c.get(f"/financeiro/?modo=dia&dia={HOJE.isoformat()}&forma=Pix")
    assert "João Lima" not in r.data.decode().split("A receber")[0].split("<h2>Movimentações</h2>")[1]

    # a receber: ficha cancelada fica de fora
    assert "Nenhum valor em aberto".encode() in c.get("/financeiro/").data

    # impressão
    r = c.get("/fichas/2/imprimir")
    assert "Assinatura do cliente".encode() in r.data and "Dinheiro".encode() in r.data

    # saídas do dia e devoluções
    assert "Terno slim".encode() in c.get(f"/saidas?data={(HOJE + timedelta(days=1)).isoformat()}").data
    assert "João Lima".encode() in c.get(f"/devolucoes?data={(HOJE + timedelta(days=5)).isoformat()}").data


def test_devolucoes_atrasadas(cliente):
    c = cliente
    criar_produto(c, "V01", "Vestido princesa", "1500")
    c.post("/fichas/nova", data=dados_ficha(
        produto_id=["1"], valor_cobrado=["1500"],
        data_saida=(HOJE - timedelta(days=10)).isoformat(),
        data_devolucao=(HOJE - timedelta(days=2)).isoformat(), situacao="retirada"))
    html = c.get("/").data.decode()                                   # tela Início
    assert "Devoluções atrasadas" in html and "2 dias de atraso" in html and "(11) 98888-7777" in html
    c.post("/fichas/1/situacao", data={"situacao": "devolvida"})
    assert "Devoluções atrasadas" not in c.get("/").data.decode()


def test_produto_usado_e_arquivado(cliente):
    c = cliente
    criar_produto(c, "T01", "Terno", "100")
    criar_produto(c, "T02", "Terno azul", "100")
    c.post("/fichas/nova", data=dados_ficha(valor_cobrado=["100"]))
    c.post("/produtos/1/excluir")
    c.post("/produtos/2/excluir")
    assert "Terno</td>".encode() not in c.get("/produtos/").data
    assert "Arquivada".encode() in c.get("/produtos/?inativos=1").data
    assert "Terno azul".encode() not in c.get("/produtos/?inativos=1").data


def test_formas_de_pagamento(cliente):
    c = cliente
    c.post("/configuracoes/formas", data={"nome": "Transferência"})
    assert "Transferência".encode() in c.get("/configuracoes/").data
    c.post("/configuracoes/formas/1/remover")  # Pix
    assert "<td class=\"principal\">Pix</td>".encode() not in c.get("/configuracoes/").data


def test_backup_mantem_30(app, tmp_path):
    pasta = tmp_path / "bk"
    for i in range(MANTER + 5):
        destino = fazer_backup(app.config["DATABASE"], str(pasta))
        os.utime(destino, (1_000_000 + i, 1_000_000 + i))
    assert len(listar(str(pasta))) == MANTER


def situacao_na_lista(c, codigo):
    html = c.get("/produtos/").data.decode()
    linha = html.split(f'<span class="codigo">{codigo}</span>')[1].split("</tr>")[0]
    for rotulo in ("Disponível", "Alugada", "Em lavagem"):
        if f">{rotulo}</span>" in linha:
            return rotulo


def test_ciclo_da_peca(cliente):
    c = cliente
    criar_produto(c, "T01", "Terno", "500")
    assert situacao_na_lista(c, "001") == "Disponível"

    # reserva futura não deixa a peça alugada hoje
    c.post("/fichas/nova", data=dados_ficha(valor_cobrado=["500"],
                                            data_saida=(HOJE + timedelta(days=10)).isoformat(),
                                            data_devolucao=(HOJE + timedelta(days=12)).isoformat()))
    assert situacao_na_lista(c, "001") == "Disponível"

    # saída hoje -> alugada
    c.post("/fichas/nova", data=dados_ficha(valor_cobrado=["500"], data_saida=HOJE.isoformat(),
                                            data_devolucao=(HOJE + timedelta(days=2)).isoformat(),
                                            confirmar_conflito=""))
    assert situacao_na_lista(c, "001") == "Alugada"

    # devolvida -> em lavagem, aparece na tela de lavagem
    r = c.post("/fichas/2/situacao", data={"situacao": "devolvida"}, follow_redirects=True)
    assert "foram para a lavagem".encode() in r.data
    assert situacao_na_lista(c, "001") == "Em lavagem"
    html = c.get("/produtos/lavagem").data.decode()
    assert "Terno" in html and "Disponibilizar" in html and "nº 2" in html

    # reservar peça em lavagem para data futura mostra aviso (sem bloquear)
    r = c.post("/fichas/nova", data=dados_ficha(valor_cobrado=["500"],
                                                data_saida=(HOJE + timedelta(days=20)).isoformat(),
                                                data_devolucao=(HOJE + timedelta(days=22)).isoformat()),
               follow_redirects=True)
    assert "em lavagem hoje".encode() in r.data and "Ficha nº 3 criada".encode() in r.data

    # disponibilizar -> disponível
    c.post("/produtos/1/disponibilizar")
    assert situacao_na_lista(c, "001") == "Disponível"
    assert "Nenhuma peça em lavagem".encode() in c.get("/produtos/lavagem").data


def test_atrasada_continua_alugada_e_bloqueia_periodo(cliente):
    c = cliente
    criar_produto(c, "V01", "Vestido", "2000")
    c.post("/fichas/nova", data=dados_ficha(valor_cobrado=["2000"],
                                            data_saida=(HOJE - timedelta(days=5)).isoformat(),
                                            data_devolucao=(HOJE - timedelta(days=1)).isoformat(),
                                            situacao="retirada"))
    assert situacao_na_lista(c, "001") == "Alugada"
    # período que começa hoje, depois da devolução prevista: ainda conflita porque a peça não voltou
    r = c.post("/fichas/nova", data=dados_ficha(cpf=CPF_B, nome="Ana", valor_cobrado=["2000"],
                                                data_saida=HOJE.isoformat(),
                                                data_devolucao=(HOJE + timedelta(days=2)).isoformat()))
    assert "devolução atrasada".encode() in r.data
    # cancelada não conta
    c.post("/fichas/1/situacao", data={"situacao": "cancelada"})
    assert situacao_na_lista(c, "001") == "Disponível"


def test_migra_banco_antigo(tmp_path):
    import sqlite3
    caminho = tmp_path / "antigo.db"
    conn = sqlite3.connect(caminho)
    conn.executescript("""CREATE TABLE produtos (id INTEGER PRIMARY KEY AUTOINCREMENT,
        codigo TEXT NOT NULL UNIQUE COLLATE NOCASE, nome TEXT NOT NULL, tipo TEXT NOT NULL DEFAULT '',
        tamanho TEXT NOT NULL DEFAULT '', cor TEXT NOT NULL DEFAULT '',
        valor_aluguel INTEGER NOT NULL DEFAULT 0, ativo INTEGER NOT NULL DEFAULT 1);
        INSERT INTO produtos (codigo, nome) VALUES ('X1', 'Peça antiga');""")
    conn.close()
    app = create_app(str(caminho))
    html = app.test_client().get("/produtos/").data.decode()
    assert "Peça antiga" in html and "Disponível" in html


def recebimentos_hoje(c):
    html = c.get(f"/financeiro/?modo=dia&dia={HOJE.isoformat()}").data.decode()
    return html.split("<h2>Movimentações</h2>")[1].split("A receber")[0]


def test_controles_da_ficha(cliente):
    c = cliente
    criar_produto(c, "T01", "Terno", "1000")
    c.post("/fichas/nova", data=dados_ficha(valor_cobrado=["1000"]))
    url = "/fichas/1/controle"

    # entrada: liga com valor/data/forma -> aparece no caixa; desliga -> some
    r = c.post(url, data={"campo": "entrada", "ligar": "1", "valor": "1.200", "data": HOJE.isoformat(), "forma": "Pix"},
               follow_redirects=True)
    assert "não pode ser maior".encode() in r.data
    c.post(url, data={"campo": "entrada", "ligar": "1", "valor": "400", "data": HOJE.isoformat(), "forma": "Pix"})
    assert "R$ 400,00" in recebimentos_hoje(c)
    c.post(url, data={"campo": "entrada", "ligar": "0"})
    assert "R$ 400,00" not in recebimentos_hoje(c)
    c.post(url, data={"campo": "entrada", "ligar": "1", "valor": "400", "data": HOJE.isoformat(), "forma": "Pix"})

    # retirada perguntando o restante: sem forma -> erro; com forma -> quita
    r = c.post(url, data={"campo": "retirada", "ligar": "1", "restante_agora": "1", "data": HOJE.isoformat()},
               follow_redirects=True)
    assert "forma de pagamento do restante".encode() in r.data
    c.post(url, data={"campo": "retirada", "ligar": "1", "restante_agora": "1",
                      "data": HOJE.isoformat(), "forma": "Dinheiro"})
    html = c.get("/fichas/1").data.decode()
    assert "Quitada" in html and ">Retirada</span>" in html
    assert "R$ 600,00" in recebimentos_hoje(c) and "Dinheiro" in recebimentos_hoje(c)

    # restante: desmarcar tira do caixa
    c.post(url, data={"campo": "restante", "ligar": "0"})
    assert "R$ 600,00" not in recebimentos_hoje(c)
    c.post(url, data={"campo": "restante", "ligar": "1", "data": HOJE.isoformat(), "forma": "Pix"})

    # devolvida -> lavagem; desmarcar -> volta para retirada e sai da lavagem
    c.post(url, data={"campo": "devolvida", "ligar": "1"})
    assert situacao_na_lista(c, "001") == "Em lavagem"
    r = c.post(url, data={"campo": "retirada", "ligar": "0"}, follow_redirects=True)
    assert "Desmarque “Devolvida”".encode() in r.data
    c.post(url, data={"campo": "devolvida", "ligar": "0"})
    assert ">Retirada</span>" in c.get("/fichas/1").data.decode()
    assert situacao_na_lista(c, "001") == "Alugada"
    assert "Nenhuma peça em lavagem".encode() in c.get("/produtos/lavagem").data

    # retirada desmarcada -> reservada
    c.post(url, data={"campo": "retirada", "ligar": "0"})
    assert ">Reservada</span>" in c.get("/fichas/1").data.decode()

    # ficha cancelada não aceita controles
    c.post("/fichas/1/situacao", data={"situacao": "cancelada"})
    r = c.post(url, data={"campo": "devolvida", "ligar": "1"}, follow_redirects=True)
    assert "Reative-a".encode() in r.data


def test_todas_as_telas_com_dados(cliente):
    """Abre todas as telas com fichas em todas as situações e confere que nenhuma dá erro."""
    c = cliente
    for i, cod in enumerate(["A1", "A2", "A3", "A4", "A5"]):
        criar_produto(c, cod, f"Peça {cod}", "300")
    datas = [(0, 3, "reservada"), (-6, -2, "retirada"), (-10, -5, "devolvida"), (5, 8, "reservada"), (1, 4, "cancelada")]
    for i, (s, d, sit) in enumerate(datas, start=1):
        c.post("/fichas/nova", data=dados_ficha(
            produto_id=[str(i)], valor_cobrado=["300"], situacao=sit,
            data_saida=(HOJE + timedelta(days=s)).isoformat(), data_devolucao=(HOJE + timedelta(days=d)).isoformat(),
            entrada_paga="1" if i % 2 else "", valor_entrada="100", data_entrada=HOJE.isoformat(), forma_entrada="Pix"))
    urls = ["/", "/saidas", "/devolucoes", f"/saidas?data={(HOJE - timedelta(days=6)).isoformat()}",
            "/produtos/lavagem", "/fichas/", "/fichas/nova", "/fichas/?situacao=cancelada&status=quitada",
            "/clientes/", "/clientes/1", "/fichas/nova?cpf=52998224725",
            "/produtos/", "/produtos/novo", "/produtos/1/editar", "/produtos/?inativos=1",
            "/financeiro/", "/financeiro/?modo=dia", "/financeiro/?modo=periodo&de=2020-01-01&ate=2030-12-31",
            "/financeiro/?modo=mes&mes=2026-01&forma=Pix", "/configuracoes/"]
    urls += [f"/produtos/?situacao={s}" for s in ("disponivel", "alugada", "lavagem")]
    for n in range(1, 6):
        urls += [f"/fichas/{n}", f"/fichas/{n}/editar", f"/fichas/{n}/imprimir"]
    for url in urls:
        r = c.get(url, follow_redirects=True)
        assert r.status_code == 200, url
    # o filtro de situação usa o cálculo pelas fichas
    assert "Peça A2" in c.get("/produtos/?situacao=alugada").data.decode()      # atrasada continua alugada
    assert "Peça A3" in c.get("/produtos/?situacao=lavagem").data.decode()
    disponiveis = c.get("/produtos/?situacao=disponivel").data.decode()
    assert "Peça A4" in disponiveis and "Peça A5" in disponiveis and "Peça A2" not in disponiveis


def test_dados_da_pergunta_do_restante_na_retirada(cliente):
    """A janela de retirada só pergunta do restante quando há valor pendente (lido destes atributos)."""
    c = cliente
    criar_produto(c, "T01", "Terno", "350")
    criar_produto(c, "T02", "Terno 2", "350")
    criar_produto(c, "T03", "Terno 3", "350")
    base = dict(data_saida=HOJE.isoformat(), data_devolucao=(HOJE + timedelta(days=2)).isoformat())
    c.post("/fichas/nova", data=dados_ficha(produto_id=["1"], valor_cobrado=["350"], **base))
    c.post("/fichas/nova", data=dados_ficha(produto_id=["2"], valor_cobrado=["350"], restante_pago="1",
                                            data_restante=HOJE.isoformat(), forma_restante="Pix", **base))
    c.post("/fichas/nova", data=dados_ficha(produto_id=["3"], valor_cobrado=["350"], entrada_paga="1",
                                            valor_entrada="350", data_entrada=HOJE.isoformat(),
                                            forma_entrada="Pix", **base))
    pendente = c.get("/fichas/1").data.decode()
    assert 'data-restante="R$ 350,00"' in pendente and 'data-restante-pago="0"' in pendente
    assert 'data-controle="retirada"' in pendente and "js/controles.js" in pendente
    assert 'data-restante-pago="1"' in c.get("/fichas/2").data.decode()        # já pago
    assert 'data-restante-pago="1"' in c.get("/fichas/3").data.decode()        # restante R$ 0,00
    # na tela de saídas o botão "Marcar retirada" usa a mesma janela
    assert c.get("/saidas").data.decode().count('data-controle="retirada"') == 3


def test_cadastro_rapido_de_produto_na_ficha(cliente):
    c = cliente
    html = c.get("/fichas/nova").data.decode()
    assert "js/janela.js" in html and "/produtos/api/novo" in html and "Gravata-borboleta" in html

    novo = {"nome": "verde oliva M", "tipo": "Colete", "tamanho": "M",
            "cor": "Verde oliva", "valor_aluguel": "1.200"}
    r = c.post("/produtos/api/novo", data=novo)
    j = r.get_json()
    assert r.status_code == 200 and j["ok"]
    assert j["produto"]["nome"] == "verde oliva M" and j["produto"]["valor"] == "1200,00"
    assert j["produto"]["situacao"] == "disponivel" and j["produto"]["codigo"] == "001"
    assert "verde oliva M" in c.get("/produtos/").data.decode()          # entrou no cadastro normal

    # código automático: a próxima peça recebe o número seguinte, mesmo com nome igual
    assert c.post("/produtos/api/novo", data=novo).get_json()["produto"]["codigo"] == "002"
    # mesmas validações do cadastro de produtos (nome e valor)
    r = c.post("/produtos/api/novo", data={"codigo": "999", "nome": "", "valor_aluguel": "abc"})
    erros = r.get_json()["erros"]
    assert r.status_code == 400 and len(erros) == 2

    # a peça criada pode ser usada na ficha em seguida
    r = c.post("/fichas/nova", data=dados_ficha(produto_id=[str(j["produto"]["id"])], valor_cobrado=["1.200"]))
    assert r.status_code == 302
    assert "verde oliva M".encode() in c.get("/fichas/1").data


def test_pasta_de_dados_fica_fora_do_programa(tmp_path, monkeypatch):
    import app as pacote
    programa = tmp_path / "programa"
    (programa / "dados").mkdir(parents=True)
    (programa / "dados" / "fascinacao.db").write_bytes(b"antigo")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(programa / "FascinacaoNoivas.exe"))
    monkeypatch.delenv("FASCINACAO_DADOS", raising=False)
    assert pacote.PASTA_DADOS_LOJA == r"C:\Fascinação Noivas Dados"
    # com a variável, usa a pasta indicada; e traz o banco da versão antiga (ao lado do .exe)
    monkeypatch.setenv("FASCINACAO_DADOS", str(tmp_path / "Dados"))
    pasta = pacote.pasta_de_dados()
    assert pasta == str(tmp_path / "Dados")
    assert (tmp_path / "Dados" / "fascinacao.db").read_bytes() == b"antigo"
    assert (programa / "dados" / "fascinacao.db").exists()            # o antigo não é apagado


def test_banco_criado_vazio_na_primeira_execucao(tmp_path):
    caminho = tmp_path / "novo" / "fascinacao.db"
    caminho.parent.mkdir()
    app = create_app(str(caminho))
    assert caminho.exists()
    c = app.test_client()
    assert "Nenhuma peça encontrada".encode() in c.get("/produtos/").data
    assert "Nenhuma ficha encontrada".encode() in c.get("/fichas/").data


def test_encerrar_sistema(app):
    c = app.test_client()
    assert "Encerrar o sistema".encode() not in c.get("/configuracoes/").data   # só no executável/iniciar.py
    chamado = []
    app.config["ENCERRAR"] = lambda: chamado.append(True)
    assert "Encerrar o sistema".encode() in c.get("/configuracoes/").data
    r = c.post("/configuracoes/encerrar")
    assert r.status_code == 200 and "Sistema encerrado".encode() in r.data and chamado


def test_nova_ficha_so_na_tela_inicial_e_voltar_padronizado(cliente):
    c = cliente
    criar_produto(c, "T01", "Terno", "100")
    c.post("/fichas/nova", data=dados_ficha(valor_cobrado=["100"]))
    inicial = c.get("/").data.decode()
    assert inicial.count("+ Nova ficha") == 1 and "btn-destaque-grande" in inicial
    assert "data-voltar-app" not in inicial                                   # tela inicial não tem Voltar
    for url in ["/saidas", "/devolucoes", "/produtos/lavagem", "/produtos/disponibilidade",
                "/vendas/", "/vendas/nova", "/vendas/produtos/", "/financeiro/fechamento", "/fichas/", "/fichas/1", "/fichas/1/editar", "/fichas/nova",
                "/clientes/", "/clientes/1", "/produtos/", "/produtos/novo", "/produtos/1/editar",
                "/financeiro/", "/configuracoes/"]:
        html = c.get(url).data.decode()
        assert "+ Nova ficha" not in html, url
        assert html.count("data-voltar-app") == 1, url                         # um único Voltar, no topo
        assert html.index("data-voltar-app") < html.index("<h1"), url
        assert "js/navegacao.js" in html and html.count("js/janela.js") == 1, url
    # destino padrão quando a aba não tem caminho anterior
    assert 'href="/fichas/1" data-voltar-app' in c.get("/fichas/1/editar").data.decode()
    assert 'href="/fichas/" data-voltar-app' in c.get("/fichas/1").data.decode()
    # formulários avisam alterações não salvas (e um formulário devolvido com erro já conta como alterado)
    for url in ["/fichas/nova", "/fichas/1/editar", "/produtos/novo", "/produtos/1/editar", "/clientes/1"]:
        assert "data-rastrear" in c.get(url).data.decode(), url
    r = c.post("/produtos/novo", data={"nome": "", "valor_aluguel": "1"})
    assert 'data-alterado="1"' in r.data.decode()
