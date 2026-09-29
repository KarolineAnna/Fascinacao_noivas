"""Paleta centralizada: toda cor vem de variável do :root, e nenhuma variável usada fica sem definição."""
import glob
import os
import re

RAIZ = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
CSS = os.path.join(RAIZ, "static", "css", "style.css")


def ler(p):
    return open(p, encoding="utf-8").read()


def test_variaveis_usadas_estao_definidas():
    definidas = set(re.findall(r"--([a-z0-9-]+)\s*:", ler(CSS)))
    arquivos = (glob.glob(os.path.join(RAIZ, "static", "css", "*.css")) + glob.glob(os.path.join(RAIZ, "static", "js", "*.js"))
                + glob.glob(os.path.join(RAIZ, "templates", "**", "*.html"), recursive=True))
    faltando = {}
    for p in arquivos:
        for v in re.findall(r"var\(--([a-z0-9-]+)", ler(p)):
            if v not in definidas and v != "qtd":            # --qtd é definida inline no gráfico
                faltando.setdefault(v, set()).add(os.path.basename(p))
    assert not faltando, faltando


def test_cores_so_no_root():
    css = ler(CSS)
    fim_root = css.index("--sombra")                        # o :root da paleta termina aqui
    fora = re.findall(r"#[0-9A-Fa-f]{3,6}\b", css[fim_root:])
    assert not fora, f"cores literais fora do :root: {sorted(set(fora))}"


def test_paleta_marsala():
    css = ler(CSS)
    for nome, cor in [("fundo", "#FAF5F3"), ("cartao", "#FFFFFF"), ("borda", "#E8D8D4"), ("texto", "#3B2426"),
                      ("texto-2", "#76595A"), ("destaque", "#955251"), ("destaque-hover", "#7A4040"),
                      ("sobre-destaque", "#FFFFFF"), ("m-fundo", "#955251"), ("m-texto", "#FFFFFF"),
                      ("m-titulo", "#FBE3DF"), ("m-ativo-fundo", "#FBEFEC"), ("m-ativo-texto", "#7A3E3E"),
                      ("ok", "#2F5A34"), ("ok-fundo", "#E4EDE3"), ("pend", "#7A5A10"), ("pend-fundo", "#F8EBCB"),
                      ("erro", "#9B1C1C"), ("erro-fundo", "#FBE3E3")]:
        assert re.search(r"--" + re.escape(nome) + r":\s*" + re.escape(cor) + r"\b", css, re.I), nome
    assert "--m-hover: rgba(255, 255, 255, .08)" in css
    assert "background: var(--m-fundo)" in css                   # menu lateral no marsala
