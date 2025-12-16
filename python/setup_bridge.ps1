Param(
    [string]$ExtensionId,
    [int]$Port = 7345
)

Write-Host "===== Configuracion del bridge CLI - Extension =====" -ForegroundColor Cyan

# 1. Calcular rutas basadas en la ubicación de este script
$BaseDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$HostCmdPath = Join-Path $BaseDir "host.cmd"
$HostPyPath  = Join-Path $BaseDir "host.py"
$BridgeJsonPath = Join-Path $BaseDir "bridge.json"

Write-Host "Carpeta base: $BaseDir"
Write-Host "host.cmd:     $HostCmdPath"
Write-Host "host.py:      $HostPyPath"
Write-Host "bridge.json:  $BridgeJsonPath"
Write-Host ""

# 2. Pedir Extension ID si no se pasó como parámetro
if (-not $ExtensionId) {
    $ExtensionId = Read-Host "Introduce el ID de la extension (ej: pjkgfpacjkfdafcppfjimceefbpnimed)"
}
if (-not $ExtensionId) {
    Write-Host "!ERROR No se proporciono Extension ID. Abortando." -ForegroundColor Red
    exit 1
}

# 3. Preguntar si se desea cambiar el puerto (por si acaso)
$portInput = Read-Host "Puerto TCP para el bridge (ENTER para usar el actual: $Port)"
if ($portInput -match '^\d+$') {
    $Port = [int]$portInput
}
Write-Host "Usando puerto: $Port"
Write-Host ""

# 4. Actualizar/crear bridge.json
Write-Host "Actualizando bridge.json ..." -ForegroundColor Yellow

$allowedOrigin = "chrome-extension://$ExtensionId/"

$bridgeObj = @{
    "name" = "com.local.cli_bridge"
    "description" = "Bridge CLI Extension (local only)"
    "path" = $HostCmdPath
    "type" = "stdio"
    "allowed_origins" = @($allowedOrigin)
}

# Serializar como JSON con indentación
$bridgeJson = $bridgeObj | ConvertTo-Json -Depth 5
$bridgeJson | Out-File -FilePath $BridgeJsonPath -Encoding UTF8

Write-Host "bridge.json actualizado con:"
Write-Host "  path           = $HostCmdPath"
Write-Host "  allowed_origin = $allowedOrigin"
Write-Host ""

# 5. Registrar Native Messaging Host en Chrome y Edge
Write-Host "Registrando Native Messaging Host en el registro..." -ForegroundColor Yellow

$chromeRegPath = "HKCU:\Software\Google\Chrome\NativeMessagingHosts\com.local.cli_bridge"
$edgeRegPath   = "HKCU:\Software\Microsoft\Edge\NativeMessagingHosts\com.local.cli_bridge"

# Chrome
New-Item -Path $chromeRegPath -Force | Out-Null
Set-ItemProperty -Path $chromeRegPath -Name "(default)" -Value $BridgeJsonPath

Write-Host "Chrome -> $chromeRegPath -> (default) = $BridgeJsonPath"

# Edge
New-Item -Path $edgeRegPath -Force | Out-Null
Set-ItemProperty -Path $edgeRegPath -Name "(default)" -Value $BridgeJsonPath

Write-Host "Edge   -> $edgeRegPath -> (default) = $BridgeJsonPath"
Write-Host ""

# 6. Crear regla de Firewall para el puerto
Write-Host "Creando regla de firewall para el puerto $Port..." -ForegroundColor Yellow

$fwRuleName = "Socket$Port"

# Si ya existe, la borramos para recrearla limpia
$existingRule = Get-NetFirewallRule -DisplayName $fwRuleName -ErrorAction SilentlyContinue
if ($existingRule) {
    Write-Host "Regla de firewall existente encontrada. Eliminando..." -ForegroundColor DarkYellow
    $existingRule | Remove-NetFirewallRule
}

New-NetFirewallRule `
    -DisplayName $fwRuleName `
    -Direction Inbound `
    -Action Allow `
    -Protocol TCP `
    -LocalPort $Port `
    -Profile Any `
    -Description "Bridge host.py TCP $Port"

Write-Host "Regla de firewall creada: $fwRuleName (TCP $Port)" -ForegroundColor Green
Write-Host ""

# 7. Configurar variables de entorno opcionales para Docker / otros clientes
$setEnv = Read-Host "¿Configurar variables de entorno SOCKET_HOST=host.docker.internal y SOCKET_PORT=$Port para el usuario actual? (S/n)"
if ($setEnv -eq "" -or $setEnv -match "^[sS]") {
    [Environment]::SetEnvironmentVariable("SOCKET_HOST", "host.docker.internal", "User")
    [Environment]::SetEnvironmentVariable("SOCKET_PORT", "$Port", "User")
    Write-Host "Variables de entorno configuradas para el usuario actual:" -ForegroundColor Green
    Write-Host "  SOCKET_HOST = host.docker.internal"
    Write-Host "  SOCKET_PORT = $Port"
} else {
    Write-Host "Saltando configuración de variables de entorno." -ForegroundColor DarkYellow
}
Write-Host ""

# 8. Mostrar comando recomendado para lanzar host.cmd oculto
Write-Host "Para lanzar el host en segundo plano desde PowerShell puedes usar:" -ForegroundColor Cyan

# Usamos comillas simples + formato para evitar problemas de escape
$startCmd = 'Start-Process cmd.exe -ArgumentList "/c ""{0}""" -WindowStyle Hidden' -f $HostCmdPath
Write-Host $startCmd
Write-Host ""

Write-Host "===== Configuración completada =====" -ForegroundColor Green
Write-Host "Reinicia Chrome/Edge si estaban abiertos y prueba la extension."
