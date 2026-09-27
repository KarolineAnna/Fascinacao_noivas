@echo off
rem Gera o FascinacaoNoivas.exe e monta a pasta que vai para o pendrive.
cd /d "%~dp0"
title Gerar instalador - Fascinacao Noivas
echo ============================================================
echo   Fascinacao Noivas - gerar instalador
echo ============================================================
echo.

if exist "venv\Scripts\python.exe" (
    set "PY=venv\Scripts\python.exe"
) else (
    where python >nul 2>nul || (
        echo Python nao encontrado. Instale o Python em https://www.python.org/downloads/
        echo e marque a opcao "Add python.exe to PATH".
        goto erro
    )
    set "PY=python"
)

echo [1/3] Instalando dependencias...
"%PY%" -m pip install --disable-pip-version-check -q -r requirements.txt pyinstaller || goto erro

echo [2/3] Gerando o executavel (leva cerca de 1 minuto)...
"%PY%" -m PyInstaller --noconfirm --clean --log-level WARN fascinacao.spec || goto erro

echo [3/3] Montando a pasta do pendrive...
set "SAIDA=PENDRIVE\Fascinacao Noivas"
if exist "PENDRIVE" rmdir /s /q "PENDRIVE"
mkdir "%SAIDA%" || goto erro
copy /y "dist\FascinacaoNoivas.exe" "%SAIDA%\" >nul || goto erro
copy /y "instalador\instalar.bat" "%SAIDA%\" >nul || goto erro
copy /y "instalador\LEIA-ME.txt" "%SAIDA%\" >nul || goto erro
if exist "build" rmdir /s /q "build"

echo.
echo ============================================================
echo   Pronto!
echo   Copie a pasta  PENDRIVE\Fascinacao Noivas  para o pendrive.
echo ============================================================
if not defined SEM_PAUSA (start "" explorer "PENDRIVE" & pause)
exit /b 0

:erro
echo.
echo Ocorreu um erro. Confira as mensagens acima.
if not defined SEM_PAUSA pause
exit /b 1
