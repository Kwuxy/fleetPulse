@echo off
setlocal enabledelayedexpansion

set "PROJECT_ROOT=%~dp0"
set "FLEET_DIR=%PROJECT_ROOT%apps\fleet_service"
set "DELIVERY_DIR=%PROJECT_ROOT%apps\delivery_service"

echo.
echo Building Docker images and deploying to Kubernetes...
echo.

REM Step 1: Build Docker images
echo [*] Building Docker images...
docker build -t fleet_service_image:latest "%FLEET_DIR%"
if errorlevel 1 goto error
docker build -t delivery_service_image:latest "%DELIVERY_DIR%"
if errorlevel 1 goto error
echo [OK] Docker images built
echo.

REM Step 2: Apply Kubernetes deployments
echo [*] Deploying to Kubernetes...
kubectl apply -f "%FLEET_DIR%\deployment\fleet_deployment.yaml"
if errorlevel 1 goto error
kubectl apply -f "%FLEET_DIR%\deployment\fleet_service.yaml"
if errorlevel 1 goto error
kubectl apply -f "%DELIVERY_DIR%\deployment\delivery_deployment.yaml"
if errorlevel 1 goto error
kubectl apply -f "%DELIVERY_DIR%\deployment\delivery_service.yaml"
if errorlevel 1 goto error
echo [OK] Deployments applied
echo.

REM Step 3: Wait for pods to be ready
echo [*] Waiting for pods to be ready...
kubectl rollout status deployment/fleet-deployment --timeout=60s
if errorlevel 1 goto error
kubectl rollout status deployment/delivery-deployment --timeout=60s
if errorlevel 1 goto error
echo [OK] All pods ready
echo.

REM Step 4: Start port forwarding
echo [*] Starting port forwarding...
echo    Fleet Service: http://localhost:8001
echo    Delivery Service: http://localhost:8002
echo.

REM Kill existing port-forward processes
for /f "tokens=2" %%A in ('tasklist ^| find /c "kubectl"') do (
  if %%A gtr 0 (
    taskkill /FI "WINDOWTITLE eq kubectl*" /T /F >nul 2>&1
    timeout /t 1 /nobreak >nul
  )
)

start /B "" kubectl port-forward svc/fleet-service 8001:8001 >nul 2>&1
start /B "" kubectl port-forward svc/delivery-service 8002:8002 >nul 2>&1

echo [OK] Port forwarding started
echo.
echo SUCCESS: FleetPulse is ready! 🚀
echo.
echo To stop: close the command windows above
echo.

pause
exit /b 0

:error
echo.
echo ERROR: Deployment failed. Check the error messages above.
echo.
pause
exit /b 1
