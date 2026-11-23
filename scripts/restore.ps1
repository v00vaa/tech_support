param(
    [Parameter(Mandatory = $true)]
    [string]$BackupPath
)

$ErrorActionPreference = "Stop"

function Invoke-Compose {
    param([string[]]$Arguments)
    & docker compose @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose $($Arguments -join ' ') завершилась с кодом $LASTEXITCODE"
    }
}

$backupDir = (Resolve-Path -LiteralPath $BackupPath).Path
$manifestPath = Join-Path $backupDir "manifest.json"
$dumpPath = Join-Path $backupDir "database.dump"
$uploadsPath = Join-Path $backupDir "uploads"
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf) -or
    -not (Test-Path -LiteralPath $dumpPath -PathType Leaf) -or
    -not (Test-Path -LiteralPath $uploadsPath -PathType Container)) {
    throw "Каталог не содержит полный комплект резервной копии."
}

$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
if ($manifest.format_version -ne 1) { throw "Неподдерживаемая версия manifest.json." }
$actualDumpHash = (Get-FileHash -LiteralPath $dumpPath -Algorithm SHA256).Hash
if ($actualDumpHash -ne $manifest.database_sha256) { throw "Контрольная сумма database.dump не совпадает." }
foreach ($file in $manifest.uploads) {
    $filePath = Join-Path $uploadsPath $file.path
    if (-not (Test-Path -LiteralPath $filePath -PathType Leaf)) {
        throw "Файл вложения отсутствует в резервной копии: $($file.path)"
    }
    $actualHash = (Get-FileHash -LiteralPath $filePath -Algorithm SHA256).Hash
    if ($actualHash -ne $file.sha256) {
        throw "Контрольная сумма вложения не совпадает: $($file.path)"
    }
}

$running = @(& docker compose ps --status running --services)
if ($LASTEXITCODE -ne 0) { throw "Не удалось получить состояние Docker Compose." }
$existing = @(& docker compose ps --all --services)
if ($LASTEXITCODE -ne 0) { throw "Не удалось получить список контейнеров Docker Compose." }
if ($running -notcontains "db") { throw "Сервис db должен быть запущен." }
if ($existing -notcontains "app") { throw "Сначала создайте контейнер app командой docker compose up -d." }

$wasAppRunning = $running -contains "app"
$wasWorkerRunning = $running -contains "worker"
$dumpContainerPath = "/tmp/support-restore.dump"

try {
    # Stop writers before replacing both persistent stores.
    Invoke-Compose -Arguments @("stop", "app", "worker")
    Invoke-Compose -Arguments @("cp", $dumpPath, "db:$dumpContainerPath")
    Invoke-Compose -Arguments @(
        "exec", "-T", "db", "pg_restore",
        "--clean", "--if-exists", "--no-owner", "--exit-on-error",
        "-U", "support", "-d", "support", $dumpContainerPath
    )
    Invoke-Compose -Arguments @(
        "run", "--rm", "--no-deps", "--entrypoint", "sh", "app",
        "-c", "mkdir -p /service/instance/uploads && find /service/instance/uploads -mindepth 1 -maxdepth 1 -exec rm -rf {} +"
    )
    Invoke-Compose -Arguments @(
        "cp", (Join-Path $uploadsPath "."), "app:/service/instance/uploads"
    )
    Write-Host "Восстановление завершено из: $backupDir"
}
finally {
    & docker compose exec -T db rm -f $dumpContainerPath 2>$null
    if ($wasAppRunning) { Invoke-Compose -Arguments @("start", "app") }
    if ($wasWorkerRunning) { Invoke-Compose -Arguments @("start", "worker") }
}
