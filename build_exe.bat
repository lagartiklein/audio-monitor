@echo off
chcp 65001 >nul
color 0A
echo.
echo ========================================================================
echo   FICHATECH MONITOR - INSTALACION COMPLETA
echo ========================================================================
echo.

REM Verificar que estamos en directorio correcto
if not exist "main.py" (
    echo ❌ ERROR: main.py no encontrado
    echo    Ejecuta este script desde la raíz del proyecto
    pause
    exit /b 1
)

REM Preguntar si eliminar entorno existente
if exist ".venv" (
    echo ⚠️  Entorno virtual existente detectado
    echo.
    choice /c SN /n /m "¿Eliminar y recrear entorno virtual? (S/N): "
    if errorlevel 2 goto skip_delete
    if errorlevel 1 (
        echo [1/7] 🗑️  Eliminando entorno virtual anterior...
        rmdir /s /q .venv
        if exist ".venv" (
            echo ❌ ERROR: No se pudo eliminar .venv
            echo    Cierra todas las terminales y programas que usen Python
            pause
            exit /b 1
        )
        echo ✅ Entorno anterior eliminado
    )
)

:skip_delete

REM Crear entorno virtual
if not exist ".venv" (
    echo [2/7] 🔨 Creando entorno virtual...
    python -m venv .venv
    if errorlevel 1 (
        echo ❌ ERROR: No se pudo crear entorno virtual
        echo.
        echo Posibles causas:
        echo   1. Python no está en PATH
        echo   2. Permisos insuficientes
        echo   3. Espacio en disco insuficiente
        pause
        exit /b 1
    )
    echo ✅ Entorno virtual creado
) else (
    echo [2/7] ✅ Entorno virtual ya existe
)

REM Activar entorno virtual
echo [3/7] 🔧 Activando entorno virtual...
call .venv\Scripts\activate.bat
if errorlevel 1 (
    echo ❌ ERROR: No se pudo activar entorno virtual
    pause
    exit /b 1
)
echo ✅ Entorno activado

REM Verificar que estamos EN el entorno virtual
where python | findstr /i "\.venv" >nul
if errorlevel 1 (
    echo ❌ ERROR: Python NO está usando el entorno virtual
    echo    Python actual: 
    where python
    echo.
    echo    Debería ser: C:\audio-monitor\.venv\Scripts\python.exe
    pause
    exit /b 1
)
echo ✅ Entorno virtual verificado

REM Actualizar pip, setuptools y wheel
echo.
echo [4/7] 📦 Actualizando herramientas de instalación...
python -m pip install --upgrade pip setuptools wheel --quiet
if errorlevel 1 (
    echo ❌ ERROR: No se pudo actualizar pip
    pause
    exit /b 1
)
echo ✅ Herramientas actualizadas

REM Verificar requirements.txt
if not exist "requirements.txt" (
    echo ❌ ERROR: requirements.txt no encontrado
    pause
    exit /b 1
)

REM Instalar dependencias
echo.
echo [5/7] 📚 Instalando dependencias...
echo    Esto puede tardar varios minutos...
echo.

pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo ❌ ERROR: Falló la instalación de dependencias
    echo.
    echo Soluciones posibles:
    echo   1. Verifica tu conexión a internet
    echo   2. Si usas Python 3.13, considera usar Python 3.11 o 3.12
    echo   3. Ejecuta manualmente: pip install -r requirements.txt
    pause
    exit /b 1
)

echo ✅ Dependencias instaladas

REM Verificar instalación
echo.
echo [6/7] ✅ Verificando instalación...
python -c "import sounddevice" 2>nul
if errorlevel 1 (
    echo ❌ ERROR: sounddevice no importa correctamente
    pause
    exit /b 1
)

python -c "import numpy" 2>nul
if errorlevel 1 (
    echo ❌ ERROR: numpy no importa correctamente
    pause
    exit /b 1
)

python -c "import flask" 2>nul
if errorlevel 1 (
    echo ❌ ERROR: flask no importa correctamente
    pause
    exit /b 1
)

python -c "import flask_socketio" 2>nul
if errorlevel 1 (
    echo ❌ ERROR: flask_socketio no importa correctamente
    pause
    exit /b 1
)

python -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo ❌ ERROR: PyInstaller no importa correctamente
    pause
    exit /b 1
)

echo ✅ Todas las dependencias verificadas

REM Mostrar versiones
echo.
echo [7/7] 📊 Información del sistema:
echo.
python --version
echo.
python -c "import numpy; print(f'NumPy: {numpy.__version__}')"
python -c "import flask; print(f'Flask: {flask.__version__}')"
python -c "import flask_socketio; print(f'Flask-SocketIO: {flask_socketio.__version__}')"
python -c "import PyInstaller; print(f'PyInstaller: {PyInstaller.__version__}')"

echo.
echo ========================================================================
echo   ✅ INSTALACION COMPLETADA EXITOSAMENTE
echo ========================================================================
echo.
echo 📝 Siguientes pasos:
echo   1. El entorno virtual está activado y listo
echo   2. Ejecuta: python main.py (para probar)
echo   3. O ejecuta: build.bat (para compilar exe)
echo.
echo 💡 Para activar el entorno manualmente:
echo   .venv\Scripts\activate
echo.

REM Preguntar si quiere ejecutar el programa
choice /c SN /n /m "¿Quieres probar el programa ahora? (S/N): "
if errorlevel 2 goto end
if errorlevel 1 (
    echo.
    echo 🚀 Iniciando Fichatech Monitor...
    python main.py
)

:end
echo.
pause