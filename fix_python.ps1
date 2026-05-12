# Fix Python Installation Script for RouteManager
# Run this as Administrator

Write-Host "=== RouteManager Python Fix ===" -ForegroundColor Cyan
Write-Host ""

# Check current Python status
Write-Host "Checking Python installation..." -ForegroundColor Yellow
$pythonFound = $false

try {
    $pyVersion = & py -3 --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  [OK] Python Launcher found: $pyVersion" -ForegroundColor Green
        $pythonFound = $true
    }
} catch {}

if (-not $pythonFound) {
    try {
        $pythonVersion = & python --version 2>&1
        if ($pythonVersion -notlike "*was not found*" -and $pythonVersion -notlike "*Microsoft Store*") {
            Write-Host "  [OK] Python found: $pythonVersion" -ForegroundColor Green
            $pythonFound = $true
        }
    } catch {}
}

if (-not $pythonFound) {
    Write-Host "  [X] Python not found" -ForegroundColor Red
    Write-Host ""
    Write-Host "Step 1: Disabling Windows Store App Aliases..." -ForegroundColor Yellow

    # Disable Windows Store Python aliases
    $appAliases = @("python.exe", "python3.exe")
    foreach ($alias in $appAliases) {
        Write-Host "  Disabling $alias alias..." -NoNewline
        # Note: This requires manual action in Settings
        Write-Host " (requires manual action)" -ForegroundColor Yellow
    }

    Write-Host ""
    Write-Host "ACTION REQUIRED:" -ForegroundColor Red
    Write-Host "1. Open Settings > Apps > Advanced app settings > App execution aliases" -ForegroundColor White
    Write-Host "2. Turn OFF the toggles for:" -ForegroundColor White
    Write-Host "   - python.exe" -ForegroundColor White
    Write-Host "   - python3.exe" -ForegroundColor White
    Write-Host ""
    Write-Host "3. Download and install Python from:" -ForegroundColor White
    Write-Host "   https://www.python.org/downloads/windows/" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "4. During installation, CHECK the box:" -ForegroundColor White
    Write-Host "   [X] Add python.exe to PATH" -ForegroundColor Yellow
    Write-Host ""

    # Open the download page
    $response = Read-Host "Open Python download page in browser? (Y/N)"
    if ($response -eq "Y" -or $response -eq "y") {
        Start-Process "https://www.python.org/downloads/windows/"
    }

    Write-Host ""
    Write-Host "After installing Python, run this script again to verify." -ForegroundColor Cyan
} else {
    Write-Host ""
    Write-Host "Python is installed correctly!" -ForegroundColor Green
    Write-Host "You can now run start_route.bat" -ForegroundColor Green
}

Write-Host ""
Write-Host "Press any key to exit..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
