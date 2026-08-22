@echo off
setlocal enabledelayedexpansion

echo.
echo Shutting down FleetPulse...
echo.

REM Step 1: Kill port-forward processes
echo [*] Stopping port forwarding...
tasklist | find /i "kubectl" >nul
if errorlevel 1 (
  echo [OK] No port-forward processes running
) else (
  taskkill /IM kubectl.exe /F >nul 2>&1
  echo [OK] Port forwarding stopped
)
echo.

REM Step 2: Delete Kubernetes deployments and services
echo [*] Removing Kubernetes resources...
kubectl delete deployment fleet-deployment >nul 2>&1
kubectl delete service fleet-service >nul 2>&1
kubectl delete deployment delivery-deployment >nul 2>&1
kubectl delete service delivery-service >nul 2>&1
echo [OK] Kubernetes resources deleted
echo.

echo SUCCESS: FleetPulse has been shut down
exit /b 0
