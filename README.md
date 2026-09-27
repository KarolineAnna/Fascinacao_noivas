# Fascinação Noivas — sistema da loja

Sistema local para a loja de aluguel de trajes para noivas e padrinhos, que também vende produtos
(Natura, Avon, mel e própolis). Cobre as fichas de aluguel, os clientes, o acervo de peças, a agenda de
saídas e devoluções, a disponibilidade, a lavagem, as vendas, o financeiro com fechamento de caixa,
a impressão da ficha e o backup automático.

Funciona **100% offline**. O sistema roda no próprio computador e abre no navegador.
Nada é enviado para a internet.

> **Instalação na loja:** veja o [instalador/LEIA-ME.txt](instalador/LEIA-ME.txt), que também vai
> para o pendrive e cobre instalação, atualização e restauração de backup.

---

## 1. Como a instalação funciona

| O quê | Onde |
|---|---|
| Programa | `C:\FascinacaoNoivas\FascinacaoNoivas.exe` (atalho **Fascinação Noivas** na área de trabalho) |
| Dados da loja | `C:\Fascinação Noivas Dados\` → `fascinacao.db`, `backups\`, `sistema.log` |

- O programa e os dados ficam em **pastas separadas**. Atualizar o programa (trocar o `.exe`) nunca
  mexe no banco nem nos backups.
- Na primeira execução, se o banco não existir, ele é **criado vazio**.
- O executável **não mostra a janela preta**: o sistema roda em segundo plano, abre o navegador
  sozinho e é encerrado em **Configurações → Encerrar o sistema** (ou ao desligar o computador).
  Clicar no atalho com o sistema já aberto só abre uma nova aba.
- Erros ao abrir aparecem numa janela do Windows e ficam registrados em `sistema.log`.

## 2. Gerar o instalador (pendrive)

Dê dois cliques em **`gerar_instalador.bat`**. Ele instala as dependências, gera
`dist\FascinacaoNoivas.exe` (com ícone e sem terminal) e monta a pasta:

```
PENDRIVE\Fascinacao Noivas\
  FascinacaoNoivas.exe   ← o programa
  instalar.bat           ← instala ou atualiza (copia para C:\FascinacaoNoivas e cria o atalho)
  LEIA-ME.txt            ← passo a passo para a loja
```

**Copie a pasta `PENDRIVE\Fascinacao Noivas` para o pendrive.** No computador da loja, basta abrir
essa pasta e dar dois cliques em `instalar.bat`, tanto na primeira instalação quanto nas atualizações.

> Se o antivírus ou o SmartScreen alertarem sobre o `.exe`, é comum com programas sem assinatura
> digital: clique em "Mais informações" → "Executar assim mesmo", ou adicione uma exceção para `C:\FascinacaoNoivas`.

## 3. Desenvolvimento

Requisitos: **Windows** e **Python 3.10+** ([python.org](https://www.python.org/downloads/)), com
*"Add python.exe to PATH"* marcado.

```bat
cd "C:\Fascinação Noivas"
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python iniciar.py
```

Abre em `http://127.0.0.1:5780/`. Em desenvolvimento os dados ficam em `dados\` na raiz do projeto,
separados dos dados da loja. Variáveis úteis: `FASCINACAO_DADOS` (outra pasta de dados),
`FASCINACAO_PORTA` (outra porta) e `FASCINACAO_SEM_NAVEGADOR=1` (não abre o navegador).

```bat
pip install pytest
python -m pytest -q
```

> Depois de alterar o código, feche e abra o sistema de novo: o Flask guarda as telas em memória, e
> uma instância antiga misturando código novo e antigo pode dar erro 500.

---

## 4. Telas

O menu lateral fica fixo à esquerda, destaca a tela aberta e pode ser **recolhido** para mostrar só os
ícones (a escolha fica lembrada). Todas as telas, menos a Início, têm o botão **← Voltar** no topo,
que retorna à tela de origem e pede confirmação se houver alterações não salvas.

| Seção | Tela | O que faz |
|---|---|---|
| Aluguel | **Início** | Botão grande **+ Nova ficha**, **devoluções atrasadas** (com nome e telefone) e o resumo do dia. |
| | **Fichas** | Lista com busca e filtros. Criar, consultar, editar, cancelar e imprimir a ficha. |
| | **Clientes** | Busca por nome ou CPF; dados e histórico de aluguéis. |
| | **Produtos de aluguel** | Acervo de peças com a situação de cada uma (Disponível, Alugada ou Em lavagem). O **código é gerado automaticamente** ao cadastrar: o próximo número depois do maior já usado, com o mesmo número de dígitos (acervo vazio começa em `001`). Ele não muda depois, porque pode estar em etiquetas. |
| | **Saídas / Devoluções do dia** | Peças por data, com cliente, telefone, pagamento e os botões *Marcar retirada* e *Marcar devolvida*. |
| | **Calendário** | Mês inteiro com as saídas e devoluções de cada dia (semana começando no domingo), marcando as já feitas e as atrasadas. |
| | **Disponibilidade** | Peças livres num período, com a ficha que ocupa cada peça. Avisa se a peça está em lavagem ou atrasada. |
| | **Peças em lavagem** | Peças devolvidas com a data da devolução e o botão **Disponibilizar**. |
| Vendas | **Nova venda** | Produtos com quantidade, total automático, forma de pagamento, data (hoje) e cliente opcional. |
| | **Vendas** | Lista com filtros por período, marca/categoria e forma de pagamento, e o total vendido. |
| | **Produtos à venda** | Cadastro separado: nome, marca/categoria e preço de venda. |
| Financeiro | **Financeiro** | Movimentações de fichas, vendas e lançamentos manuais, com filtros, totais (entradas, saídas e saldo), totais por categoria e por forma, e a lista **a receber**. |
| | **Relatórios** | Faturamento por mês (aluguel, vendas e outras entradas, com gráfico e tabela), peças mais alugadas, peças paradas e clientes que voltam. Períodos: 3, 6 ou 12 meses, este ano ou tudo. |
| | **Fechar caixa** | Esperado por forma de pagamento no dia (fichas + vendas + entradas − saídas), valor contado, diferença e histórico de fechamentos. |
| | **Configurações** | Backup, categorias do financeiro, marcas de produtos à venda, formas de pagamento e *Encerrar o sistema*. |

## 5. Regras principais

**Fichas e clientes**
- O CPF é validado e não se repete. Numa ficha nova, um CPF já cadastrado preenche os dados do cliente.
- A devolução precisa ser posterior à saída. Datas: calendário em português, semana começando no
  domingo, exibição `dd/mm/aaaa` (também dá para digitar). O servidor continua recebendo `aaaa-mm-dd`.
- Situação: Reservada → Retirada → Devolvida, ou **Cancelada**. Uma ficha cancelada libera as peças,
  e os valores já recebidos continuam no financeiro.
- Na busca de peças, se nada for encontrado, **+ Cadastrar novo produto** abre uma janela com o nome
  digitado. A peça criada entra direto na ficha, sem perder o que já foi preenchido.
- **Controles** (interruptores com confirmação): Entrada paga, Retirada, Restante pago e Devolvida.
  Ao marcar Retirada, dá para registrar no mesmo passo o pagamento do restante. Desmarcar um pagamento
  tira o valor do financeiro.

**Peças: Disponível → Alugada → Em lavagem → Disponível**
- **Alugada:** da saída até a ficha ser marcada como Devolvida. Se a devolução atrasar, a peça continua alugada.
- **Em lavagem:** ao marcar a ficha como Devolvida, até clicar em **Disponibilizar**.
- **Datas futuras:** calculadas pelas fichas (saída até devolução). Conflitos geram um aviso com a
  ficha que está com a peça e podem ser confirmados.

**Contrato, multa e caução**
- Em Configurações → *Contrato e multa por atraso*: multa por dia em % do aluguel (padrão: 10%) ou valor
  fixo em R$, e o texto do **termo de responsabilidade** impresso na ficha, com os campos {devolucao},
  {multa_dia}, {caucao} e {cliente}.
- Na ficha, *Caução e multa*: **Caução recebida**, **Caução devolvida** (inteira ou em parte, o que fica
  retido cobre danos) e **Multa paga** (com opção de isentar).
- Ao marcar *Devolvida* depois da data prevista, a multa é calculada (dias de atraso × multa por dia).
  A janela permite ajustar ou isentar a multa, registrar o pagamento e devolver a caução no mesmo passo.
  Desmarcar a devolução descarta a multa ainda não paga. Uma ficha cadastrada já como devolvida não gera multa.
- No Financeiro, a caução recebida é entrada, a devolução é saída e a multa paga é entrada. Tudo entra
  no fechamento de caixa. Nos relatórios, a caução não conta como faturamento; só o valor retido conta.

**Financeiro e vendas**
- As movimentações vêm de três origens: **Ficha** (entradas e restantes), **Venda** e **Lançamento**
  manual (entrada ou saída, com categoria). Recebimentos de fichas e vendas só podem ser alterados
  na própria ficha ou venda; o financeiro traz o link para abri-las.
- **Fechamento de caixa:** esperado de cada forma = fichas + vendas + entradas manuais − saídas manuais
  do dia. Por exemplo, R$ 500 recebidos em dinheiro nas fichas e R$ 80 pagos em dinheiro à lavanderia
  dão R$ 420 esperados em dinheiro.
- Categorias, marcas e formas de pagamento são editadas nas Configurações. Uma categoria em uso não
  pode ser removida, mas pode ser renomeada.

**Backup:** uma cópia do banco a cada abertura, mantendo as 30 mais recentes, na pasta padrão
(`C:\Fascinação Noivas Dados\backups`) ou na pasta escolhida nas Configurações (Google Drive, pendrive).

---

## 6. Estrutura do projeto

```
iniciar.py              inicializador: backup, servidor, navegador, atalho (--criar-atalho) e log
fascinacao.spec         configuração do PyInstaller (FascinacaoNoivas.exe, sem console, com ícone)
gerar_instalador.bat    gera o .exe e monta a pasta PENDRIVE
instalador/             instalar.bat e LEIA-ME.txt (vão para o pendrive)
app/
  __init__.py           app Flask, pasta de dados, menu/voltar
  db.py                 esquema SQLite, migrações e views (v_fichas, v_vendas, v_movimentos)
  pecas.py              ciclo das peças
  backup.py             cópias de segurança
  util.py               CPF, valores em R$, datas
  views/                agenda, fichas, clientes, produtos, vendas, financeiro, configurações
  templates/            telas (Jinja)
  static/               CSS, JavaScript, fontes, ícones e vendor/flatpickr (calendário, local)
tests/                  testes automatizados (pytest)
```

Os valores em dinheiro são guardados em centavos. As colunas novas são adicionadas automaticamente aos
bancos antigos ao abrir (`MIGRACOES` em `app/db.py`), e as tabelas novas são criadas se não existirem.

Licenças de terceiros: fontes Cormorant Garamond e Jost (SIL Open Font License) e flatpickr (MIT,
em `app/static/vendor/flatpickr/LICENSE.md`).
