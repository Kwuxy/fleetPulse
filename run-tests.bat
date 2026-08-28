@echo off
setlocal enabledelayedexpansion

set "PROJECT_ROOT=%~dp0"
set "PYTEST_ARGS=%*"

echo.
echo Running tests sequentially (Delivery Service, then Fleet Service)...
echo.

echo [*] Running Delivery Service tests...
pushd "%PROJECT_ROOT%apps\delivery_service"
.venv\Scripts\python.exe -m pytest test %PYTEST_ARGS%
set "DELIVERY_EXIT=%ERRORLEVEL%"
popd
if not "%DELIVERY_EXIT%"=="0" goto error
echo [OK] Delivery Service tests passed
echo.

echo [*] Running Fleet Service tests...
pushd "%PROJECT_ROOT%apps\fleet_service"
.venv\Scripts\python.exe -m pytest test %PYTEST_ARGS%
set "FLEET_EXIT=%ERRORLEVEL%"
popd
if not "%FLEET_EXIT%"=="0" goto error
echo [OK] Fleet Service tests passed
echo.

echo SUCCESS: All tests passed.
exit /b 0

:error
echo.
echo ERROR: Tests failed. Check the output above.
exit /b 1
