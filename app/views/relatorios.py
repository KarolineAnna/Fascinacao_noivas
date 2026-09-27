"""Relatórios: faturamento por mês, peças mais alugadas, peças paradas e clientes que voltam."""
from datetime import date

from flask import Blueprint, render_template, request

from ..db import get_db
from ..util import MESES

bp = Blueprint("relatorios", __name__, url_prefix="/relatorios")

PERIODOS = {"3": "Últimos 3 meses", "6": "Últimos 6 meses", "12": "Últimos 12 meses",
            "ano": "Este ano", "tudo": "Desde o início"}


def escala_redonda(maximo_centavos):
    """Topo do eixo e marcas em valores redondos (passos de 1, 2, 2,5 ou 5 × 10ⁿ reais, 4 a 6 divisões),
    escolhendo o menor topo que cobre o maior mês, para as barras usarem bem a altura."""
    reais = max(maximo_centavos / 100, 1)
    melhor = None
    for divisoes in (4, 5, 6):
        bruto = reais / divisoes
        potencia = 10 ** (len(str(int(bruto))) - 1) if bruto >= 1 else 1
        passo = next(m * potencia for m in (1, 2, 2.5, 5, 10) if m * potencia >= bruto)
        if melhor is None or passo * divisoes < melhor[0] * melhor[1]:
            melhor = (passo, divisoes)
    passo_centavos, divisoes = int(round(melhor[0] * 100)), melhor[1]
    return passo_centavos * divisoes, [passo_centavos * i for i in range(divisoes + 1)]


def meses_entre(inicio, fim):
    """Lista de (ano, mês) de inicio até fim, inclusive."""
    a, m = inicio.year, inicio.month
    lista = []
    while (a, m) <= (fim.year, fim.month):
        lista.append((a, m))
        a, m = (a + 1, 1) if m == 12 else (a, m + 1)
    return lista


def intervalo(periodo, db):
    hoje = date.today()
    if periodo == "ano":
        return date(hoje.year, 1, 1), hoje
    if periodo == "tudo":
        primeiro = db.execute(
            """SELECT MIN(d) FROM (SELECT MIN(data) AS d FROM v_movimentos
                                   UNION ALL SELECT MIN(data_saida) FROM alugueis)""").fetchone()[0]
        inicio = date.fromisoformat(primeiro) if primeiro else hoje
        return inicio.replace(day=1), hoje
    n = int(periodo)
    a, m = hoje.year, hoje.month - (n - 1)
    while m < 1:
        a, m = a - 1, m + 12
    return date(a, m, 1), hoje


@bp.route("/")
def pagina():
    db = get_db()
    periodo = request.args.get("periodo", "12")
    if periodo not in PERIODOS:
        periodo = "12"
    de, ate = intervalo(periodo, db)
    faixa = {"de": de.isoformat(), "ate": ate.isoformat()}

    # --- Faturamento por mês (pela data do pagamento) ---
    por_mes = {f"{a:04d}-{m:02d}": {"aluguel": 0, "vendas": 0, "outras": 0, "saidas": 0}
               for a, m in meses_entre(de, ate)}
    for r in db.execute(
            """SELECT substr(data, 1, 7) AS mes, origem, tipo, SUM(valor) AS total
                 FROM v_movimentos WHERE data BETWEEN :de AND :ate AND categoria != 'Caução'
                GROUP BY mes, origem, tipo
               UNION ALL
               -- caução retida (não devolvida por danos) passa a ser receita do aluguel
               SELECT substr(caucao_devolucao_data, 1, 7), 'ficha', 'entrada',
                      SUM(caucao_valor - caucao_devolvido_valor)
                 FROM alugueis WHERE caucao_devolvida = 1 AND caucao_valor > caucao_devolvido_valor
                  AND caucao_devolucao_data BETWEEN :de AND :ate
                GROUP BY 1""", faixa):
        linha = por_mes.get(r["mes"])
        if linha is None:
            continue
        if r["origem"] == "ficha":
            linha["aluguel"] += r["total"]
        elif r["origem"] == "venda":
            linha["vendas"] += r["total"]
        elif r["tipo"] == "entrada":
            linha["outras"] += r["total"]
        else:
            linha["saidas"] += r["total"]
    meses = []
    for chave, v in por_mes.items():
        a, m = int(chave[:4]), int(chave[5:])
        entradas = v["aluguel"] + v["vendas"] + v["outras"]
        meses.append({**v, "chave": chave, "rotulo": f"{MESES[m - 1][:3]}/{str(a)[2:]}",
                      "nome": f"{MESES[m - 1]} de {a}", "entradas": entradas, "saldo": entradas - v["saidas"]})
    totais = {k: sum(m[k] for m in meses) for k in ("aluguel", "vendas", "outras", "saidas", "entradas", "saldo")}

    # --- Fichas no período (pela data de saída, sem as canceladas) ---
    fichas = db.execute(
        """SELECT COUNT(*) AS qtd, COALESCE(SUM(total), 0) AS valor FROM v_fichas
            WHERE situacao != 'cancelada' AND data_saida BETWEEN :de AND :ate""", faixa).fetchone()

    # --- Peças mais alugadas ---
    mais_alugadas = db.execute(
        """SELECT p.id, p.codigo, p.nome, p.tipo, p.tamanho, p.cor,
                  COUNT(DISTINCT f.id) AS vezes,
                  SUM(julianday(f.data_devolucao) - julianday(f.data_saida)) AS dias,
                  SUM(i.valor_cobrado) AS receita
             FROM aluguel_itens i
             JOIN v_fichas f ON f.id = i.aluguel_id
             JOIN produtos p ON p.id = i.produto_id
            WHERE f.situacao != 'cancelada' AND f.data_saida BETWEEN :de AND :ate
            GROUP BY p.id
            ORDER BY vezes DESC, receita DESC
            LIMIT 10""", faixa).fetchall()

    # --- Peças paradas: ativas e sem nenhum aluguel no período ---
    paradas = db.execute(
        """SELECT p.id, p.codigo, p.nome, p.tipo, p.tamanho, p.cor, p.valor_aluguel,
                  (SELECT MAX(f.data_saida) FROM aluguel_itens i JOIN alugueis f ON f.id = i.aluguel_id
                    WHERE i.produto_id = p.id AND f.situacao != 'cancelada') AS ultimo,
                  (SELECT COUNT(*) FROM aluguel_itens i JOIN alugueis f ON f.id = i.aluguel_id
                    WHERE i.produto_id = p.id AND f.situacao != 'cancelada') AS vezes_total
             FROM produtos p
            WHERE p.ativo = 1
              AND NOT EXISTS (SELECT 1 FROM aluguel_itens i JOIN alugueis f ON f.id = i.aluguel_id
                               WHERE i.produto_id = p.id AND f.situacao != 'cancelada'
                                 AND f.data_saida BETWEEN :de AND :ate)
            ORDER BY ultimo IS NOT NULL, ultimo, p.nome COLLATE NOCASE""", faixa).fetchall()
    hoje = date.today()
    dias_parada = {p["id"]: (hoje - date.fromisoformat(p["ultimo"])).days if p["ultimo"] else None for p in paradas}
    total_pecas = db.execute("SELECT COUNT(*) FROM produtos WHERE ativo = 1").fetchone()[0]

    # --- Clientes que voltam (2 ou mais fichas, em todo o histórico) ---
    voltam = db.execute(
        """SELECT c.id, c.nome, c.telefone,
                  COUNT(f.id) AS fichas, MIN(f.data_saida) AS primeira, MAX(f.data_saida) AS ultima,
                  COALESCE(SUM(f.total), 0) AS total,
                  (SELECT COALESCE(SUM(v.total), 0) FROM v_vendas v WHERE v.cliente_id = c.id) AS compras,
                  SUM(CASE WHEN f.data_saida BETWEEN :de AND :ate THEN 1 ELSE 0 END) AS no_periodo
             FROM clientes c JOIN v_fichas f ON f.cliente_id = c.id AND f.situacao != 'cancelada'
            GROUP BY c.id HAVING COUNT(f.id) >= 2
            ORDER BY fichas DESC, total DESC""", faixa).fetchall()
    com_ficha = db.execute(
        "SELECT COUNT(DISTINCT cliente_id) FROM alugueis WHERE situacao != 'cancelada'").fetchone()[0]

    escala, marcas = escala_redonda(max([m["entradas"] for m in meses] + [0]))
    return render_template(
        "relatorios.html", periodo=periodo, periodos=PERIODOS, de=de, ate=ate,
        meses=meses, totais=totais, escala=escala, marcas=marcas,
        maior_mes=max(meses, key=lambda m: m["entradas"])["chave"] if totais["entradas"] else None,
        fichas=fichas, ticket=(fichas["valor"] // fichas["qtd"]) if fichas["qtd"] else 0,
        mais_alugadas=mais_alugadas, paradas=paradas, dias_parada=dias_parada, total_pecas=total_pecas,
        voltam=voltam, com_ficha=com_ficha,
        taxa_retorno=round(100 * len(voltam) / com_ficha) if com_ficha else 0,
    )
