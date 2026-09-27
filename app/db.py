"""Conexão com o SQLite e criação do esquema."""
import sqlite3

from flask import current_app, g

SCHEMA = """
CREATE TABLE IF NOT EXISTS produtos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo          TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    nome            TEXT    NOT NULL,
    tipo            TEXT    NOT NULL DEFAULT '',
    tamanho         TEXT    NOT NULL DEFAULT '',
    cor             TEXT    NOT NULL DEFAULT '',
    valor_aluguel   INTEGER NOT NULL DEFAULT 0,      -- em centavos
    ativo           INTEGER NOT NULL DEFAULT 1,
    em_lavagem      INTEGER NOT NULL DEFAULT 0,
    lavagem_desde   TEXT,                            -- data em que a peça foi devolvida
    lavagem_ficha_id INTEGER                         -- ficha que a peça voltou
);

CREATE TABLE IF NOT EXISTS clientes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    nome        TEXT NOT NULL,
    cpf         TEXT NOT NULL UNIQUE,                -- somente dígitos
    telefone    TEXT NOT NULL DEFAULT '',
    endereco    TEXT NOT NULL DEFAULT '',
    criado_em   TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS alugueis (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id      INTEGER NOT NULL REFERENCES clientes(id),
    data_saida      TEXT    NOT NULL,                -- AAAA-MM-DD
    data_devolucao  TEXT    NOT NULL,
    entrada_paga    INTEGER NOT NULL DEFAULT 0,
    valor_entrada   INTEGER NOT NULL DEFAULT 0,      -- em centavos
    data_entrada    TEXT,                            -- quando a entrada foi paga
    forma_entrada   TEXT,                            -- nome da forma de pagamento
    restante_pago   INTEGER NOT NULL DEFAULT 0,
    data_restante   TEXT,                            -- quando o restante foi pago
    forma_restante  TEXT,
    data_devolvida  TEXT,                            -- quando a peça voltou de fato
    multa_valor     INTEGER NOT NULL DEFAULT 0,      -- multa por atraso (centavos)
    multa_paga      INTEGER NOT NULL DEFAULT 0,
    multa_data      TEXT,
    multa_forma     TEXT,
    caucao_valor    INTEGER NOT NULL DEFAULT 0,      -- caução recebida (0 = sem caução)
    caucao_data     TEXT,
    caucao_forma    TEXT,
    caucao_devolvida        INTEGER NOT NULL DEFAULT 0,
    caucao_devolvido_valor  INTEGER NOT NULL DEFAULT 0,   -- pode ser menor que a caução (retenção por danos)
    caucao_devolucao_data   TEXT,
    caucao_devolucao_forma  TEXT,
    situacao       TEXT    NOT NULL DEFAULT 'reservada'
                    CHECK (situacao IN ('reservada', 'retirada', 'devolvida', 'cancelada')),
    observacoes     TEXT    NOT NULL DEFAULT '',
    criado_em       TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    CHECK (data_devolucao > data_saida)
);

CREATE TABLE IF NOT EXISTS aluguel_itens (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    aluguel_id      INTEGER NOT NULL REFERENCES alugueis(id) ON DELETE CASCADE,
    produto_id      INTEGER NOT NULL REFERENCES produtos(id),
    valor_cobrado   INTEGER NOT NULL DEFAULT 0,      -- em centavos
    UNIQUE (aluguel_id, produto_id)
);

CREATE TABLE IF NOT EXISTS formas_pagamento (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    nome    TEXT NOT NULL UNIQUE COLLATE NOCASE,
    ordem   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS configuracoes (
    chave   TEXT PRIMARY KEY,
    valor   TEXT NOT NULL
);

-- Categorias editáveis nas Configurações: grupo 'financeiro' (lançamentos) ou 'venda' (produtos à venda).
CREATE TABLE IF NOT EXISTS categorias (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    grupo   TEXT NOT NULL CHECK (grupo IN ('financeiro', 'venda')),
    nome    TEXT NOT NULL COLLATE NOCASE,
    ordem   INTEGER NOT NULL DEFAULT 0,
    UNIQUE (grupo, nome)
);

-- Movimentações financeiras manuais (entradas e saídas que não vêm de fichas nem vendas).
CREATE TABLE IF NOT EXISTS lancamentos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo            TEXT    NOT NULL CHECK (tipo IN ('entrada', 'saida')),
    data            TEXT    NOT NULL,
    descricao       TEXT    NOT NULL,
    categoria_id    INTEGER NOT NULL REFERENCES categorias(id),
    valor           INTEGER NOT NULL,                -- em centavos
    forma           TEXT    NOT NULL,
    observacao      TEXT    NOT NULL DEFAULT '',
    criado_em       TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- Produtos à venda (Natura, Avon, mel...), separados das peças de aluguel.
CREATE TABLE IF NOT EXISTS produtos_venda (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    nome            TEXT    NOT NULL,
    categoria_id    INTEGER NOT NULL REFERENCES categorias(id),
    preco           INTEGER NOT NULL DEFAULT 0,      -- em centavos
    ativo           INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS vendas (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    data            TEXT    NOT NULL,
    cliente_id      INTEGER REFERENCES clientes(id), -- opcional
    cliente_nome    TEXT    NOT NULL DEFAULT '',     -- nome livre quando não há cadastro
    forma           TEXT    NOT NULL,
    observacao      TEXT    NOT NULL DEFAULT '',
    criado_em       TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS venda_itens (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    venda_id        INTEGER NOT NULL REFERENCES vendas(id) ON DELETE CASCADE,
    produto_id      INTEGER NOT NULL REFERENCES produtos_venda(id),
    quantidade      INTEGER NOT NULL CHECK (quantidade > 0),
    preco_unitario  INTEGER NOT NULL                 -- preço no dia da venda
);

-- Fechamento de caixa: valor contado em cada forma de pagamento no fim do dia.
CREATE TABLE IF NOT EXISTS fechamentos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    data        TEXT    NOT NULL,
    forma       TEXT    NOT NULL,
    esperado    INTEGER NOT NULL,
    contado     INTEGER NOT NULL,
    observacao  TEXT    NOT NULL DEFAULT '',
    criado_em   TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    UNIQUE (data, forma)
);

CREATE INDEX IF NOT EXISTS idx_lancamentos_data    ON lancamentos(data);
CREATE INDEX IF NOT EXISTS idx_vendas_data         ON vendas(data);
CREATE INDEX IF NOT EXISTS idx_venda_itens_venda   ON venda_itens(venda_id);
CREATE INDEX IF NOT EXISTS idx_alugueis_saida     ON alugueis(data_saida);
CREATE INDEX IF NOT EXISTS idx_alugueis_devolucao  ON alugueis(data_devolucao);
CREATE INDEX IF NOT EXISTS idx_alugueis_cliente    ON alugueis(cliente_id);
CREATE INDEX IF NOT EXISTS idx_itens_produto       ON aluguel_itens(produto_id);

-- Ficha com cliente e valores calculados (total, restante e status financeiro).
DROP VIEW IF EXISTS v_fichas;
CREATE VIEW v_fichas AS
SELECT b.*,
       b.total - b.entrada_efetiva AS restante,
       CASE WHEN b.multa_valor > 0 AND b.multa_paga = 0 THEN b.multa_valor ELSE 0 END AS multa_pendente,
       CASE WHEN b.caucao_valor > 0 AND b.caucao_devolvida = 0 THEN b.caucao_valor ELSE 0 END AS caucao_em_aberto,
       CASE WHEN b.restante_pago = 1 OR (b.total > 0 AND b.total - b.entrada_efetiva <= 0)
                 THEN 'quitada'
            WHEN b.entrada_paga = 1 THEN 'entrada_paga'
            ELSE 'entrada_pendente'
       END AS status_financeiro
  FROM (SELECT a.*,
               c.nome     AS cliente_nome,
               c.cpf      AS cliente_cpf,
               c.telefone AS cliente_telefone,
               c.endereco AS cliente_endereco,
               COALESCE((SELECT SUM(i.valor_cobrado) FROM aluguel_itens i
                          WHERE i.aluguel_id = a.id), 0) AS total,
               CASE WHEN a.entrada_paga = 1 THEN a.valor_entrada ELSE 0 END AS entrada_efetiva
          FROM alugueis a
          JOIN clientes c ON c.id = a.cliente_id) b;

-- Venda com total e nome do cliente (cadastrado ou livre).
DROP VIEW IF EXISTS v_vendas;
CREATE VIEW v_vendas AS
SELECT v.*,
       COALESCE(c.nome, NULLIF(v.cliente_nome, ''), '') AS cliente,
       COALESCE((SELECT SUM(i.quantidade * i.preco_unitario) FROM venda_itens i
                  WHERE i.venda_id = v.id), 0) AS total,
       COALESCE((SELECT SUM(i.quantidade) FROM venda_itens i WHERE i.venda_id = v.id), 0) AS qtd_itens
  FROM vendas v LEFT JOIN clientes c ON c.id = v.cliente_id;

-- Todas as movimentações de dinheiro: recebimentos das fichas, vendas e lançamentos manuais.
-- origem: 'ficha' | 'venda' | 'manual'  ·  tipo: 'entrada' | 'saida'  ·  valor sempre positivo.
DROP VIEW IF EXISTS v_movimentos;
CREATE VIEW v_movimentos AS
SELECT 'ficha' AS origem, id AS ref_id, 'entrada' AS tipo, data_entrada AS data,
       'Entrada da ficha nº ' || id || ' · ' || cliente_nome AS descricao,
       'Aluguel' AS categoria, NULL AS categoria_id, valor_entrada AS valor,
       COALESCE(forma_entrada, '') AS forma, '' AS observacao, 'Entrada' AS detalhe
  FROM v_fichas WHERE entrada_paga = 1 AND valor_entrada > 0 AND data_entrada IS NOT NULL
UNION ALL
SELECT 'ficha', id, 'entrada', data_restante,
       'Restante da ficha nº ' || id || ' · ' || cliente_nome,
       'Aluguel', NULL, restante, COALESCE(forma_restante, ''), '', 'Restante'
  FROM v_fichas WHERE restante_pago = 1 AND restante > 0 AND data_restante IS NOT NULL
UNION ALL
SELECT 'ficha', id, 'entrada', multa_data,
       'Multa por atraso da ficha nº ' || id || ' · ' || cliente_nome,
       'Multa por atraso', NULL, multa_valor, COALESCE(multa_forma, ''), '', 'Multa'
  FROM v_fichas WHERE multa_paga = 1 AND multa_valor > 0 AND multa_data IS NOT NULL
UNION ALL
SELECT 'ficha', id, 'entrada', caucao_data,
       'Caução da ficha nº ' || id || ' · ' || cliente_nome,
       'Caução', NULL, caucao_valor, COALESCE(caucao_forma, ''), '', 'Caução'
  FROM v_fichas WHERE caucao_valor > 0 AND caucao_data IS NOT NULL
UNION ALL
SELECT 'ficha', id, 'saida', caucao_devolucao_data,
       'Devolução da caução da ficha nº ' || id || ' · ' || cliente_nome,
       'Caução', NULL, caucao_devolvido_valor, COALESCE(caucao_devolucao_forma, ''), '', 'Devolução de caução'
  FROM v_fichas WHERE caucao_devolvida = 1 AND caucao_devolvido_valor > 0 AND caucao_devolucao_data IS NOT NULL
UNION ALL
SELECT 'venda', id, 'entrada', data,
       'Venda nº ' || id || CASE WHEN cliente != '' THEN ' · ' || cliente ELSE '' END,
       'Venda', NULL, total, forma, observacao, 'Venda'
  FROM v_vendas WHERE total > 0
UNION ALL
SELECT 'manual', l.id, l.tipo, l.data, l.descricao, c.nome, l.categoria_id, l.valor, l.forma,
       l.observacao, 'Lançamento'
  FROM lancamentos l JOIN categorias c ON c.id = l.categoria_id;
"""


def get_db():
    if "db" not in g:
        conn = sqlite3.connect(current_app.config["DATABASE"])
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        g.db = conn
    return g.db


def close_db(_exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def ler_config(conn, chave, padrao=None):
    linha = conn.execute("SELECT valor FROM configuracoes WHERE chave = ?", (chave,)).fetchone()
    return linha[0] if linha else padrao


def gravar_config(conn, chave, valor):
    conn.execute("INSERT INTO configuracoes (chave, valor) VALUES (?, ?)"
                 " ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor", (chave, valor))
    conn.commit()


FORMAS_PADRAO = ["Pix", "Dinheiro", "Cartão de débito", "Cartão de crédito"]
CATEGORIAS_PADRAO = {
    "financeiro": ["Lavanderia", "Costureira", "Aluguel do imóvel", "Contas", "Compra de peças", "Outros"],
    "venda": ["Natura", "Avon", "Mel e própolis"],
}


def categorias(conn, grupo):
    return conn.execute("SELECT * FROM categorias WHERE grupo = ? ORDER BY ordem, id", (grupo,)).fetchall()


def formas_de_pagamento(conn, incluir=()):
    """Nomes das formas cadastradas, mais as já usadas numa ficha (caso tenham sido removidas)."""
    nomes = [r[0] for r in conn.execute("SELECT nome FROM formas_pagamento ORDER BY ordem, id")]
    return nomes + [n for n in incluir if n and n not in nomes]


# Colunas acrescentadas depois da primeira versão: bancos antigos recebem ao abrir.
MIGRACOES = {
    "produtos": [("em_lavagem", "INTEGER NOT NULL DEFAULT 0"), ("lavagem_desde", "TEXT"),
                 ("lavagem_ficha_id", "INTEGER")],
    "alugueis": [('data_devolvida', 'TEXT'), ('multa_valor', 'INTEGER NOT NULL DEFAULT 0'), ('multa_paga', 'INTEGER NOT NULL DEFAULT 0'), ('multa_data', 'TEXT'), ('multa_forma', 'TEXT'), ('caucao_valor', 'INTEGER NOT NULL DEFAULT 0'), ('caucao_data', 'TEXT'), ('caucao_forma', 'TEXT'), ('caucao_devolvida', 'INTEGER NOT NULL DEFAULT 0'), ('caucao_devolvido_valor', 'INTEGER NOT NULL DEFAULT 0'), ('caucao_devolucao_data', 'TEXT'), ('caucao_devolucao_forma', 'TEXT')],
}


def migrar(conn):
    for tabela, colunas in MIGRACOES.items():
        existentes = {r[1] for r in conn.execute(f"PRAGMA table_info({tabela})")}
        if not existentes:
            continue
        for nome, tipo in colunas:
            if nome not in existentes:
                conn.execute(f"ALTER TABLE {tabela} ADD COLUMN {nome} {tipo}")


def init_db(path):
    conn = sqlite3.connect(path)
    try:
        migrar(conn)
        conn.executescript(SCHEMA)
        if ler_config(conn, "formas_iniciais") is None:
            conn.executemany("INSERT OR IGNORE INTO formas_pagamento (nome, ordem) VALUES (?, ?)",
                             [(n, i) for i, n in enumerate(FORMAS_PADRAO)])
            gravar_config(conn, "formas_iniciais", "1")
        if ler_config(conn, "categorias_iniciais") is None:
            conn.executemany("INSERT OR IGNORE INTO categorias (grupo, nome, ordem) VALUES (?, ?, ?)",
                             [(g, n, i) for g, nomes in CATEGORIAS_PADRAO.items() for i, n in enumerate(nomes)])
            gravar_config(conn, "categorias_iniciais", "1")
        conn.commit()
    finally:
        conn.close()
