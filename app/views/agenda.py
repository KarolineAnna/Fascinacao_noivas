"""Saídas do dia e Devoluções do dia: mesma tela, mudando a data de referência."""
from datetime import date, timedelta

from flask import Blueprint, redirect, render_template, request, url_for

from ..db import get_db
from ..util import data_extenso, parse_data

bp = Blueprint("agenda", __name__)

MODOS = {
    "saidas": {"titulo": "Saídas do dia", "coluna": "data_saida",
               "vazio": "Nenhuma peça com saída nesta data.",
               "acao": ("retirada", "Marcar retirada"), "de": "reservada"},
    "devolucoes": {"titulo": "Devoluções do dia", "coluna": "data_devolucao",
                   "vazio": "Nenhuma peça com devolução prevista nesta data.",
                   "acao": ("devolvida", "Marcar devolvida"), "de": "retirada"},
}


def devolucoes_atrasadas():
    """Fichas com devolução vencida que ainda não estão como devolvidas (nem canceladas)."""
    db = get_db()
    hoje = date.today()
    atrasadas = db.execute(
        """SELECT * FROM v_fichas
            WHERE data_devolucao < ? AND situacao NOT IN ('devolvida', 'cancelada')
            ORDER BY data_devolucao, id""", (hoje.isoformat(),)).fetchall()
    pecas = {f["id"]: pecas_da_ficha(f["id"]) for f in atrasadas}
    dias = {f["id"]: (hoje - date.fromisoformat(f["data_devolucao"])).days for f in atrasadas}
    return atrasadas, pecas, dias


def pecas_da_ficha(ficha_id):
    return get_db().execute(
        """SELECT p.codigo, p.nome, p.tamanho, p.cor
             FROM aluguel_itens i JOIN produtos p ON p.id = i.produto_id
            WHERE i.aluguel_id = ? ORDER BY i.id""", (ficha_id,)).fetchall()


@bp.route("/")
def inicio():
    db = get_db()
    hoje = date.today().isoformat()
    atrasadas, pecas, dias_atraso = devolucoes_atrasadas()
    contar = lambda sql, *p: db.execute(sql, p).fetchone()[0]
    resumo = {
        "saidas": contar("SELECT COUNT(*) FROM v_fichas WHERE data_saida = ? AND situacao != 'cancelada'", hoje),
        "devolucoes": contar("SELECT COUNT(*) FROM v_fichas WHERE data_devolucao = ? AND situacao NOT IN ('cancelada', 'devolvida')", hoje),
        "lavagem": contar("SELECT COUNT(*) FROM produtos WHERE em_lavagem = 1"),
        "a_receber": contar("""SELECT COALESCE(SUM(restante), 0) FROM v_fichas
                               WHERE status_financeiro != 'quitada' AND restante > 0 AND situacao != 'cancelada'"""),
        "recebido_hoje": contar("SELECT COALESCE(SUM(CASE tipo WHEN 'entrada' THEN valor ELSE -valor END), 0) FROM v_movimentos WHERE data = ?", hoje),
    }
    return render_template("inicio.html", atrasadas=atrasadas, pecas=pecas, dias_atraso=dias_atraso,
                           resumo=resumo, dia_extenso=data_extenso(date.today()))


def tela(modo):
    cfg = MODOS[modo]
    dia = parse_data(request.args.get("data")) or date.today()
    db = get_db()
    fichas = db.execute(
        f"""SELECT * FROM v_fichas WHERE {cfg['coluna']} = ? AND situacao != 'cancelada'
             ORDER BY cliente_nome COLLATE NOCASE, id""",
        (dia.isoformat(),),
    ).fetchall()

    pecas = {f["id"]: pecas_da_ficha(f["id"]) for f in fichas}

    return render_template(
        "agenda.html", modo=modo, cfg=cfg, dia=dia, dia_extenso=data_extenso(dia),
        anterior=dia - timedelta(days=1), seguinte=dia + timedelta(days=1),
        fichas=fichas, pecas=pecas, total_pecas=sum(len(pecas[f["id"]]) for f in fichas),
    )


@bp.route("/saidas")
def saidas():
    return tela("saidas")


@bp.route("/devolucoes")
def devolucoes():
    return tela("devolucoes")


@bp.route("/calendario")
def calendario():
    """Visão do mês: saídas e devoluções de cada dia (semana começando no domingo)."""
    import calendar as cal

    hoje = date.today()
    try:
        ano, mes = (int(x) for x in request.args.get("mes", "").split("-"))
        primeiro = date(ano, mes, 1)
    except ValueError:
        primeiro = hoje.replace(day=1)
    semanas = cal.Calendar(firstweekday=6).monthdatescalendar(primeiro.year, primeiro.month)
    inicio, fim = semanas[0][0], semanas[-1][-1]

    eventos = {}
    db = get_db()
    for f in db.execute(
            """SELECT id, cliente_nome, data_saida, data_devolucao, situacao FROM v_fichas
                WHERE situacao != 'cancelada'
                  AND (data_saida BETWEEN :i AND :f OR data_devolucao BETWEEN :i AND :f)
                ORDER BY cliente_nome COLLATE NOCASE""", {"i": inicio.isoformat(), "f": fim.isoformat()}):
        if inicio.isoformat() <= f["data_saida"] <= fim.isoformat():
            eventos.setdefault(f["data_saida"], []).append(
                {"tipo": "saida", "ficha": f, "feito": f["situacao"] in ("retirada", "devolvida")})
        if inicio.isoformat() <= f["data_devolucao"] <= fim.isoformat():
            atrasada = f["data_devolucao"] < hoje.isoformat() and f["situacao"] != "devolvida"
            eventos.setdefault(f["data_devolucao"], []).append(
                {"tipo": "devolucao", "ficha": f, "feito": f["situacao"] == "devolvida", "atrasada": atrasada})
    for lista in eventos.values():
        lista.sort(key=lambda e: e["tipo"] != "saida")   # saídas primeiro

    anterior = (primeiro - timedelta(days=1)).replace(day=1)
    seguinte = (primeiro + timedelta(days=32)).replace(day=1)
    no_mes = [e for d, lista in eventos.items() if d[:7] == primeiro.strftime("%Y-%m") for e in lista]
    from ..util import MESES
    return render_template(
        "calendario.html", semanas=semanas, eventos=eventos, primeiro=primeiro, hoje=hoje,
        titulo_mes=f"{MESES[primeiro.month - 1]} de {primeiro.year}",
        anterior=anterior, seguinte=seguinte,
        total_saidas=sum(1 for e in no_mes if e["tipo"] == "saida"),
        total_devolucoes=sum(1 for e in no_mes if e["tipo"] == "devolucao"),
    )
