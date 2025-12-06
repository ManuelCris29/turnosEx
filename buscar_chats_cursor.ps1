# Script para encontrar los chats de Cursor
Write-Host "Buscando carpetas de Cursor..." -ForegroundColor Cyan
Write-Host ""

# Buscar en APPDATA
$appDataPath = "$env:APPDATA\Cursor"
if (Test-Path $appDataPath) {
    Write-Host "✅ ENCONTRADO en APPDATA:" -ForegroundColor Green
    Write-Host "   $appDataPath" -ForegroundColor Yellow
    Write-Host ""
    
    # Buscar subcarpetas relevantes
    Write-Host "Carpetas encontradas:" -ForegroundColor Cyan
    Get-ChildItem $appDataPath -Directory | ForEach-Object {
        Write-Host "   - $($_.Name)" -ForegroundColor White
    }
    Write-Host ""
    
    # Buscar archivos relacionados con chats
    Write-Host "Buscando archivos relacionados con chats..." -ForegroundColor Cyan
    $chatFiles = Get-ChildItem $appDataPath -Recurse -Filter "*chat*" -ErrorAction SilentlyContinue | Select-Object -First 10
    if ($chatFiles) {
        Write-Host "Archivos encontrados:" -ForegroundColor Green
        $chatFiles | ForEach-Object {
            Write-Host "   - $($_.FullName)" -ForegroundColor White
        }
    } else {
        Write-Host "   No se encontraron archivos con 'chat' en el nombre" -ForegroundColor Yellow
    }
    Write-Host ""
    
    # Buscar archivos .db (posibles bases de datos)
    Write-Host "Buscando bases de datos (.db)..." -ForegroundColor Cyan
    $dbFiles = Get-ChildItem $appDataPath -Recurse -Filter "*.db" -ErrorAction SilentlyContinue | Select-Object -First 10
    if ($dbFiles) {
        Write-Host "Bases de datos encontradas:" -ForegroundColor Green
        $dbFiles | ForEach-Object {
            Write-Host "   - $($_.FullName) ($([math]::Round($_.Length / 1KB, 2)) KB)" -ForegroundColor White
        }
    } else {
        Write-Host "   No se encontraron archivos .db" -ForegroundColor Yellow
    }
} else {
    Write-Host "❌ No encontrado en APPDATA" -ForegroundColor Red
}

Write-Host ""
Write-Host "=" * 60 -ForegroundColor Gray
Write-Host ""

# Buscar en LOCALAPPDATA
$localAppDataPath = "$env:LOCALAPPDATA\Cursor"
if (Test-Path $localAppDataPath) {
    Write-Host "✅ ENCONTRADO en LOCALAPPDATA:" -ForegroundColor Green
    Write-Host "   $localAppDataPath" -ForegroundColor Yellow
    Write-Host ""
    
    # Buscar subcarpetas relevantes
    Write-Host "Carpetas encontradas:" -ForegroundColor Cyan
    Get-ChildItem $localAppDataPath -Directory | ForEach-Object {
        Write-Host "   - $($_.Name)" -ForegroundColor White
    }
    Write-Host ""
    
    # Buscar archivos relacionados con chats
    Write-Host "Buscando archivos relacionados con chats..." -ForegroundColor Cyan
    $chatFiles = Get-ChildItem $localAppDataPath -Recurse -Filter "*chat*" -ErrorAction SilentlyContinue | Select-Object -First 10
    if ($chatFiles) {
        Write-Host "Archivos encontrados:" -ForegroundColor Green
        $chatFiles | ForEach-Object {
            Write-Host "   - $($_.FullName)" -ForegroundColor White
        }
    } else {
        Write-Host "   No se encontraron archivos con 'chat' en el nombre" -ForegroundColor Yellow
    }
    Write-Host ""
    
    # Buscar archivos .db
    Write-Host "Buscando bases de datos (.db)..." -ForegroundColor Cyan
    $dbFiles = Get-ChildItem $localAppDataPath -Recurse -Filter "*.db" -ErrorAction SilentlyContinue | Select-Object -First 10
    if ($dbFiles) {
        Write-Host "Bases de datos encontradas:" -ForegroundColor Green
        $dbFiles | ForEach-Object {
            Write-Host "   - $($_.FullName) ($([math]::Round($_.Length / 1KB, 2)) KB)" -ForegroundColor White
        }
    } else {
        Write-Host "   No se encontraron archivos .db" -ForegroundColor Yellow
    }
} else {
    Write-Host "❌ No encontrado en LOCALAPPDATA" -ForegroundColor Red
}

Write-Host ""
Write-Host "=" * 60 -ForegroundColor Gray
Write-Host ""
Write-Host "RECOMENDACIÓN:" -ForegroundColor Cyan
Write-Host "Si encontraste las carpetas, puedes hacer backup de:" -ForegroundColor White
Write-Host "  1. Toda la carpeta Cursor (más seguro)" -ForegroundColor Yellow
Write-Host "  2. Solo las carpetas 'User\globalStorage' o 'User\workspaceStorage'" -ForegroundColor Yellow
Write-Host ""
Write-Host "Usa el archivo GUIA_EXPORTAR_CHATS_CURSOR.md para más detalles" -ForegroundColor Cyan



