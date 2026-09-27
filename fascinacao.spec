# -*- mode: python ; coding: utf-8 -*-
# Gera dist\FascinacaoNoivas.exe. Use o gerar_instalador.bat (ou: python -m PyInstaller --noconfirm fascinacao.spec)

a = Analysis(
    ["iniciar.py"],
    pathex=[],
    datas=[("app/templates", "app/templates"), ("app/static", "app/static")],
    hiddenimports=["tkinter", "tkinter.filedialog"],
    excludes=["pytest"],
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="FascinacaoNoivas",
    console=False,          # sem a janela preta do terminal; encerra-se em Configurações
    icon="app/static/img/icone.ico",
    upx=False,
)
