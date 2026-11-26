# Registra las tareas programadas de Yumori en Windows (usuario actual, sin permisos de administrador).
#   Yumori-scrape   precios de todas las tiendas (esto acumula el historial), con dos disparadores:
#                   diario a la hora indicada y 2 min después de iniciar sesión (para que haya red).
#                   Corre con --diario: si ya hubo una corrida completa ese día, la segunda se omite.
#   Yumori-ratings  semanal (domingo 10:00): valoraciones de Shopify/Judge.me, tarda ~5 horas
#
# Uso:   powershell -ExecutionPolicy Bypass -File install_schedule.ps1 [-Hora 07:00]
# Quitar: Unregister-ScheduledTask -TaskName Yumori-scrape,Yumori-ratings -Confirm:$false
#
# Si el PC está apagado o dormido a esa hora, la tarea corre apenas vuelva a estar disponible.
# Las rutas salen de la carpeta del script, así que sirve igual en otro PC: basta volver a ejecutarlo ahí.
param([string]$Hora = "07:00")
$ErrorActionPreference = "Stop"

$dir = $PSScriptRoot
$python = (Get-Command python).Source
$pythonw = Join-Path (Split-Path $python) "pythonw.exe"  # sin ventana de consola
if (-not (Test-Path $pythonw)) { $pythonw = $python }

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -RunOnlyIfNetworkAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 8)

function Registrar($nombre, $script, $trigger, $descripcion) {
    $action = New-ScheduledTaskAction -Execute $pythonw -Argument $script -WorkingDirectory $dir
    Register-ScheduledTask -TaskName $nombre -Action $action -Trigger $trigger -Settings $settings -Description $descripcion -Force | Out-Null
    $next = (Get-ScheduledTask -TaskName $nombre | Get-ScheduledTaskInfo).NextRunTime
    Write-Host "OK  $nombre  (proxima ejecucion: $next)"
}

$alIniciar = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$alIniciar.Delay = "PT2M"
Registrar "Yumori-scrape" "scrape.py --diario" @((New-ScheduledTaskTrigger -Daily -At $Hora), $alIniciar) "Yumori: precios de todas las tiendas (diario y al iniciar sesion, una corrida completa por dia)"
Registrar "Yumori-ratings" "ratings.py" (New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At "10:00") "Yumori: valoraciones de Shopify/Judge.me (semanal)"
Write-Host "Registro en: $dir\data\yumori.log"
