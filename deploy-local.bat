@echo off
setlocal enabledelayedexpansion

set "PROJECT_ROOT=%~dp0"
set "FLEET_DIR=%PROJECT_ROOT%apps\fleet_service"
set "DELIVERY_DIR=%PROJECT_ROOT%apps\delivery_service"

echo.
echo Building Docker images and deploying to Kubernetes...
echo.

REM Step 0: Check if Kubernetes cluster is running
echo [*] Checking Kubernetes cluster...
kubectl cluster-info >nul 2>&1
if errorlevel 1 (
  echo [!] Kubernetes cluster not running.
  
  REM Check if Docker Desktop is running
  docker ps >nul 2>&1
  if errorlevel 1 (
    echo [ERROR] Docker Desktop is not running. Please start Docker Desktop manually.
    pause
    exit /b 1
  )
  
  echo [*] Waiting for Kubernetes to be ready...
  ping -n 6 127.0.0.1 >nul
  
  REM Wait up to 120 seconds for cluster to be ready
  set "retry=0"
  :wait_cluster
  kubectl cluster-info >nul 2>&1
  if errorlevel 1 (
    if !retry! lss 24 (
      set /a retry=!retry!+1
      echo [*] Waiting... Attempt !retry!/24
      ping -n 6 127.0.0.1 >nul
      goto wait_cluster
    ) else (
      echo [ERROR] Kubernetes cluster failed to start after 120 seconds.
      echo [INFO] Please enable Kubernetes in Docker Desktop:
      echo        1. Open Docker Desktop Settings
      echo        2. Go to Settings - Kubernetes
      echo        3. Check "Enable Kubernetes"
      echo        4. Click Apply and wait for it to initialize
      echo        5. Run this script again
      pause
      exit /b 1
    )
  )
  echo [OK] Kubernetes cluster is ready
) else (
  echo [OK] Kubernetes cluster is running
)
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
    ping -n 2 127.0.0.1 >nul
  )
)

start /B "" kubectl port-forward svc/fleet-service 8001:8001 >nul 2>&1
start /B "" kubectl port-forward svc/delivery-service 8002:8002 >nul 2>&1

echo [OK] Port forwarding started
echo.
echo SUCCESS: FleetPulse is ready! 🚀
echo.
echo To stop: run shutdown.bat

exit /b 0

:error
echo.
echo ERROR: Deployment failed. Check the error messages above.
exit /b 1
