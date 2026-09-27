@echo off
rem Instala ou atualiza o sistema no computador da loja.
rem O programa vai para C:\FascinacaoNoivas. Os dados ficam em outra pasta
rem (C:\Fascinacao Noivas Dados) e NAO sao alterados por esta instalacao.
title Instalar - Fascinacao Noivas
set "DESTINO=C:\FascinacaoNoivas"

echo ============================================================
echo   Fascinacao Noivas - instalacao / atualizacao
echo ============================================================
echo.
echo Os dados da loja (fichas, clientes, produtos e backups) NAO serao apagados.
echo.

echo Fechando o sistema, caso esteja aberto...
taskkill /IM FascinacaoNoivas.exe /F >nul 2>nul
timeout /t 2 /nobreak >nul

if not exist "%DESTINO%" mkdir "%DESTINO%" || goto erro
copy /y "%~dp0FascinacaoNoivas.exe" "%DESTINO%\FascinacaoNoivas.exe" >nul || goto erro
copy /y "%~dp0LEIA-ME.txt" "%DESTINO%\LEIA-ME.txt" >nul

echo Criando o atalho na area de trabalho...
"%DESTINO%\FascinacaoNoivas.exe" --criar-atalho

echo.
echo Instalado com sucesso! Abrindo o sistema...
start "" "%DESTINO%\FascinacaoNoivas.exe"
timeout /t 5
exit /b 0

:erro
echo.
echo Nao foi possivel copiar o programa para %DESTINO%.
echo Clique com o botao direito em instalar.bat e escolha "Executar como administrador".
pause
exit /b 1
