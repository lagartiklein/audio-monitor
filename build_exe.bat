@echo off
echo ========================================
echo  FICHATECH MONITOR - BUILD EXECUTABLE
echo ========================================
echo.

REM Activar entorno virtual
call .venv\Scripts\activate.bat

REM Limpiar builds anteriores
echo [1/4] Limpiando builds anteriores...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist "Fichatech Monitor Server.spec" del "Fichatech Monitor Server.spec"

REM Generar spec file
echo [2/4] Generando spec file...
pyi-makespec --onefile --noconsole --name "Fichatech Monitor Server" --icon=icono.ico main.py

REM Modificar spec para incluir datos adicionales
echo [3/4] Compilando con PyInstaller...
pyinstaller "Fichatech Monitor Server.spec" --clean --noconfirm

REM Verificar resultado
echo [4/4] Verificando build...
if exist "dist\Fichatech Monitor Server.exe" (
    echo.
    echo ========================================
    echo  BUILD EXITOSO
    echo ========================================
    echo  Ejecutable: dist\Fichatech Monitor Server.exe
    echo.
    
    REM Copiar frontend si existe
    if exist frontend (
        echo Copiando frontend...
        xcopy /E /I /Y frontend "dist\frontend"
    )
    
    echo Build completado correctamente!
    pause
) else (
    echo.
    echo ========================================
    echo  BUILD FALLIDO
    echo ========================================
    echo  Revisa los errores arriba
    pause
    exit /b 1
)