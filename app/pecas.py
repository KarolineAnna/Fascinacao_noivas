"""Situação das peças: Disponível → Alugada → Em lavagem → Disponível.

- Alugada: está numa ficha (não cancelada e ainda não devolvida) cuja saída já chegou
  ou que já foi marcada como retirada. Continua alugada depois da data de devolução
  até a ficha ser marcada como "Devolvida" (fica atrasada).
- Em lavagem: a ficha foi marcada como "Devolvida"; fica assim até clicar em "Disponibilizar".
- Disponível: nenhum dos dois casos.
"""
from datetime import date

SITUACOES_PECA = {
    "disponivel": "Disponível",
    "alugada": "Alugada",
    "lavagem": "Em lavagem",
}


def alugadas_hoje(db, hoje=None):
    """{produto_id: ficha} para as peças que estão fora da loja agora."""
    hoje = (hoje or date.today()).isoformat()
    linhas = db.execute(
        """SELECT i.produto_id, f.id AS ficha_id, f.cliente_nome, f.data_saida, f.data_devolucao
             FROM aluguel_itens i JOIN v_fichas f ON f.id = i.aluguel_id
            WHERE f.situacao IN ('reservada', 'retirada')
              AND (f.data_saida <= ? OR f.situacao = 'retirada')
            ORDER BY f.data_saida""", (hoje,)).fetchall()
    resultado = {}
    for linha in linhas:
        resultado.setdefault(linha["produto_id"], dict(linha, atrasada=linha["data_devolucao"] < hoje))
    return resultado


def situacao_das_pecas(db, hoje=None):
    """{produto_id: {"situacao": ..., "ficha": ... , "lavagem_desde": ...}} para todas as peças."""
    fora = alugadas_hoje(db, hoje)
    resultado = {}
    for p in db.execute("SELECT id, em_lavagem, lavagem_desde FROM produtos"):
        if p["id"] in fora:
            resultado[p["id"]] = {"situacao": "alugada", "ficha": fora[p["id"]]}
        elif p["em_lavagem"]:
            resultado[p["id"]] = {"situacao": "lavagem", "lavagem_desde": p["lavagem_desde"]}
        else:
            resultado[p["id"]] = {"situacao": "disponivel"}
    return resultado


def ao_mudar_situacao(db, ficha_id, anterior, nova):
    """Ao marcar a ficha como devolvida, as peças vão para a lavagem. Se a devolução
    for desfeita, as peças que ainda estavam na lavagem por causa dela voltam ao normal."""
    if nova == anterior:
        return
    from .contrato import desfazer_devolucao, registrar_devolucao
    if nova == "devolvida":
        db.execute(
            """UPDATE produtos SET em_lavagem = 1, lavagem_desde = ?, lavagem_ficha_id = ?
                WHERE id IN (SELECT produto_id FROM aluguel_itens WHERE aluguel_id = ?)""",
            (date.today().isoformat(), ficha_id, ficha_id))
        if anterior is None:
            # ficha cadastrada já como devolvida (registro de um aluguel passado): sem multa
            db.execute("UPDATE alugueis SET data_devolvida = data_devolucao WHERE id = ?", (ficha_id,))
        else:
            registrar_devolucao(db, ficha_id)      # data real + multa por atraso
    elif anterior == "devolvida":
        db.execute("""UPDATE produtos SET em_lavagem = 0, lavagem_desde = NULL, lavagem_ficha_id = NULL
                       WHERE em_lavagem = 1 AND lavagem_ficha_id = ?""", (ficha_id,))
        desfazer_devolucao(db, ficha_id)
