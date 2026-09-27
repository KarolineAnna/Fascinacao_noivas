"""Validações e formatações usadas em todo o sistema."""
import re
from datetime import date
from decimal import Decimal, InvalidOperation

MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro"]
DIAS_SEMANA = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
               "sexta-feira", "sábado", "domingo"]

SITUACOES = {
    "reservada": "Reservada",
    "retirada": "Retirada",
    "devolvida": "Devolvida",
    "cancelada": "Cancelada",
}

STATUS_FINANCEIRO = {
    "entrada_pendente": "Entrada pendente",
    "entrada_paga": "Entrada paga",
    "quitada": "Quitada",
}


# --- CPF -------------------------------------------------------------------

def so_digitos(valor):
    return re.sub(r"\D", "", valor or "")


def cpf_valido(cpf):
    """Confere tamanho e dígitos verificadores. Recebe o CPF com ou sem máscara."""
    cpf = so_digitos(cpf)
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    for tamanho in (9, 10):
        soma = sum(int(cpf[i]) * (tamanho + 1 - i) for i in range(tamanho))
        digito = (soma * 10) % 11 % 10
        if digito != int(cpf[tamanho]):
            return False
    return True


def formatar_cpf(cpf):
    cpf = so_digitos(cpf)
    if len(cpf) != 11:
        return cpf
    return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"


# --- Dinheiro (guardado em centavos) ----------------------------------------

def reais_para_centavos(texto):
    """Aceita '150', '150,00', '1.234,56', 'R$ 99,9' ou '150.5'. Retorna None se inválido."""
    s = (texto or "").replace("R$", "").replace(" ", "").strip()
    if not s:
        return None
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", s):
        s = s.replace(".", "")          # "1.200" = mil e duzentos
    try:
        valor = Decimal(s)
    except InvalidOperation:
        return None
    if valor < 0:
        return None
    return int((valor * 100).quantize(Decimal("1")))


def formatar_brl(centavos):
    centavos = int(centavos or 0)
    inteiro, resto = divmod(abs(centavos), 100)
    texto = f"{inteiro:,}".replace(",", ".")
    sinal = "-" if centavos < 0 else ""
    return f"{sinal}R$ {texto},{resto:02d}"


def centavos_para_campo(centavos):
    """Valor para preencher um input de formulário (ex.: '150,00')."""
    centavos = int(centavos or 0)
    return f"{centavos // 100},{centavos % 100:02d}"


# --- Datas ------------------------------------------------------------------

def parse_data(texto):
    try:
        return date.fromisoformat((texto or "").strip())
    except ValueError:
        return None


def formatar_data(valor):
    if not valor:
        return ""
    d = valor if isinstance(valor, date) else parse_data(valor)
    return d.strftime("%d/%m/%Y") if d else str(valor)


def data_extenso(d):
    return f"{DIAS_SEMANA[d.weekday()]}, {d.day} de {MESES[d.month - 1]} de {d.year}"
