@echo off
echo ========================================
echo  COMPILANDO FICHATECH MONITOR
echo ========================================

REM Activar entorno
call .venv\Scripts\activate.bat

REM Limpiar
echo Limpiando builds anteriores...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

REM Compilar
echo Compilando...
pyinstaller "Fichatech Monitor Server.spec" --clean --noconfirm

REM Verificar
if exist "dist\Fichatech Monitor Server.exe" (
    echo.
    echo ✅ COMPILACION EXITOSA
    echo Ejecutable: dist\Fichatech Monitor Server.exe
    echo.
    pause
) else (
    echo.
    echo ❌ ERROR EN COMPILACION
    pause
    exit /b 1
)