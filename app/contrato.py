"""Contrato da ficha: multa por atraso, caução e termo de responsabilidade.

- Multa: configurável em Configurações, como valor fixo por dia (R$) ou percentual do valor do
  aluguel por dia. É calculada quando a ficha é marcada como "Devolvida" depois da data prevista
  (dias de atraso × multa por dia) e pode ser ajustada ou isentada.
- Caução: valor opcional recebido na ficha; ao devolver, pode ser devolvida inteira ou em parte
  (o que fica retido cobre danos). Entra e sai do Financeiro como qualquer movimento.
"""
from datetime import date

from .db import ler_config
from .util import formatar_brl, formatar_data

MULTA_TIPOS = {"percentual": "% do valor do aluguel por dia", "valor": "valor fixo por dia (R$)"}
MULTA_PADRAO = ("percentual", 1000)          # 10% do aluguel por dia (guardado em centésimos de %)

TERMO_PADRAO = """1. DEVOLUÇÃO: as peças devem ser devolvidas até {devolucao}. Após essa data será cobrada multa de {multa_dia} por dia de atraso, até a devolução.
2. DANOS: manchas, rasgos, queimaduras, perda de acessórios ou ajustes não autorizados serão avaliados pela loja. O conserto ou a reposição da peça serão cobrados do cliente e poderão ser descontados da caução.
3. LIMPEZA: a lavagem das peças é feita pela loja. O cliente não deve lavar, passar, tingir ou ajustar as peças por conta própria.
4. CAUÇÃO: {caucao}. A caução é devolvida após a conferência das peças, descontados eventuais danos ou multas.
5. O cliente declara ter conferido e recebido as peças acima em perfeito estado e concorda com estas condições."""


def config_multa(db):
    tipo = ler_config(db, "multa_tipo", MULTA_PADRAO[0])
    try:
        valor = int(ler_config(db, "multa_valor", str(MULTA_PADRAO[1])))
    except ValueError:
        valor = MULTA_PADRAO[1]
    return (tipo if tipo in MULTA_TIPOS else MULTA_PADRAO[0]), valor


def multa_por_dia(db, total_aluguel):
    """Multa de um dia de atraso, em centavos."""
    tipo, valor = config_multa(db)
    if tipo == "valor":
        return valor
    return (total_aluguel * valor + 5000) // 10000          # valor em centésimos de %


def texto_multa(db, total_aluguel):
    tipo, valor = config_multa(db)
    if tipo == "valor":
        return formatar_brl(valor)
    pct = f"{valor / 100:.2f}".rstrip("0").rstrip(".").replace(".", ",")
    return f"{pct}% do valor do aluguel ({formatar_brl(multa_por_dia(db, total_aluguel))})"


def dias_de_atraso(data_devolucao, devolvida_em=None):
    prevista = date.fromisoformat(data_devolucao)
    return max(0, ((devolvida_em or date.today()) - prevista).days)


def previa(db, ficha, dia=None):
    """(dias de atraso, multa) se a ficha fosse devolvida em `dia` (hoje, por padrão)."""
    dias = dias_de_atraso(ficha["data_devolucao"], dia)
    return dias, dias * multa_por_dia(db, ficha["total"])


def registrar_devolucao(db, ficha_id, dia=None):
    """Ficha marcada como devolvida: guarda a data real e calcula a multa (se ainda não foi paga)."""
    dia = dia or date.today()
    f = db.execute("SELECT * FROM v_fichas WHERE id = ?", (ficha_id,)).fetchone()
    db.execute("UPDATE alugueis SET data_devolvida = ? WHERE id = ?", (dia.isoformat(), ficha_id))
    if not f["multa_paga"]:
        _, multa = previa(db, f, dia)
        db.execute("UPDATE alugueis SET multa_valor = ? WHERE id = ?", (multa, ficha_id))


def desfazer_devolucao(db, ficha_id):
    """Devolução desmarcada: some a data real e a multa ainda não paga."""
    db.execute("""UPDATE alugueis SET data_devolvida = NULL,
                      multa_valor = CASE WHEN multa_paga = 1 THEN multa_valor ELSE 0 END
                   WHERE id = ?""", (ficha_id,))


def termo(db, ficha):
    """Parágrafos do termo de responsabilidade, com os dados da ficha."""
    texto = ler_config(db, "termo_texto") or TERMO_PADRAO
    caucao = (f"foi deixada caução de {formatar_brl(ficha['caucao_valor'])}" if ficha["caucao_valor"]
              else "não foi deixada caução")
    trocas = {"{devolucao}": formatar_data(ficha["data_devolucao"]),
              "{multa_dia}": texto_multa(db, ficha["total"]),
              "{caucao}": caucao,
              "{cliente}": ficha["cliente_nome"]}
    for chave, valor in trocas.items():
        texto = texto.replace(chave, valor)
    return [p.strip() for p in texto.splitlines() if p.strip()]
