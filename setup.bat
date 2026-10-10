@echo off
setlocal

set "PROJECT_ROOT=%~dp0"

echo [*] Checking environment...
where uv >nul 2>&1
if errorlevel 1 (
    echo     ERROR: uv is missing, please install it with command `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
    exit /b 1
)

docker info >nul 2>&1
if errorlevel 1 (
    echo     ERROR: Can't find Docker, install ^(https://www.docker.com/products/docker-desktop/^) and/or start it then rerun this command.
    exit /b 1
)

echo [*] Setting .env file...
if not exist "%PROJECT_ROOT%.env" (
    copy "%PROJECT_ROOT%.env.example" "%PROJECT_ROOT%.env"
    echo     Copied .env file from example. You can either use the current local development variables or set new ones. Don't use them in any other environment.
) else (
    echo     .env file already exist, great job for being proactive !
)
echo.

echo [*] Creating Fleet Service venv...
pushd "%PROJECT_ROOT%apps\fleet_service"
uv sync --locked
set "FLEET_EXIT=%ERRORLEVEL%"
popd
if not "%FLEET_EXIT%"=="0" goto error
echo [OK] Fleet Service venv created
echo.

echo [*] Creating Delivery Service venv...
pushd "%PROJECT_ROOT%apps\delivery_service"
uv sync --locked
set "DELIVERY_EXIT=%ERRORLEVEL%"
popd
if not "%DELIVERY_EXIT%"=="0" goto error
echo [OK] Delivery Service venv created
echo.

echo [*] Creating GPS Simulator venv...
pushd "%PROJECT_ROOT%apps\gps_simulator"
uv sync --locked
set "GPS_EXIT=%ERRORLEVEL%"
popd
if not "%GPS_EXIT%"=="0" goto error
echo [OK] GPS Simulator venv created
echo.

pushd "%PROJECT_ROOT%"
docker compose up --build -d
set "COMPOSE_EXIT=%ERRORLEVEL%"
popd
if not "%COMPOSE_EXIT%"=="0" goto error
echo [OK] App is up on Docker
echo.

echo SUCCESS: You're good to go ! Try APIs with Bruno, a collection is ready in the api_collection folder, you can also run tests with the command run-tests.bat
exit /b 0

:error
echo.
echo     ERROR: Woops, something wrong happened. Check the output above.
exit /b 1
