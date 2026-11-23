param(
    [string]$BackupRoot = "backups"
)

$ErrorActionPreference = "Stop"

function Invoke-Compose {
    param([string[]]$Arguments)
    & docker compose @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose $($Arguments -join ' ') завершилась с кодом $LASTEXITCODE"
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
$timestamp = (Get-Date).ToUniversalTime().ToString("yyyyMMdd-HHmmss")
$backupDir = Join-Path $BackupRoot $timestamp
$dumpName = "support-$timestamp.dump"
$dumpContainerPath = "/tmp/$dumpName"

New-Item -ItemType Directory -Force -Path (Join-Path $backupDir "uploads") | Out-Null

try {
    # Stop writers so the database dump and uploaded files describe one consistent state.
    Invoke-Compose -Arguments @("stop", "app", "worker")

    Invoke-Compose -Arguments @(
        "exec", "-T", "db", "pg_dump",
        "-U", "support", "-d", "support", "-Fc", "-f", $dumpContainerPath
    )
    Invoke-Compose -Arguments @("cp", "db:$dumpContainerPath", (Join-Path $backupDir "database.dump"))
    Invoke-Compose -Arguments @("cp", "app:/service/instance/uploads", (Join-Path $backupDir "uploads"))

    $uploadManifest = @(
        Get-ChildItem -LiteralPath (Join-Path $backupDir "uploads") -File -Recurse |
            ForEach-Object {
                [PSCustomObject]@{
                    path = $_.FullName.Substring((Join-Path $backupDir "uploads").Length).TrimStart([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar)
                    sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
                }
            }
    )
    $manifest = [PSCustomObject]@{
        format_version = 1
        created_at_utc = (Get-Date).ToUniversalTime().ToString("o")
        git_commit = (& git rev-parse HEAD 2>$null)
        database_sha256 = (Get-FileHash -LiteralPath (Join-Path $backupDir "database.dump") -Algorithm SHA256).Hash
        uploads = $uploadManifest
    }
    $manifest | ConvertTo-Json -Depth 8 |
        Set-Content -LiteralPath (Join-Path $backupDir "manifest.json") -Encoding utf8

    Write-Host "Резервная копия создана: $backupDir"
}
finally {
    & docker compose exec -T db rm -f $dumpContainerPath 2>$null
    if ($wasAppRunning) { Invoke-Compose -Arguments @("start", "app") }
    if ($wasWorkerRunning) { Invoke-Compose -Arguments @("start", "worker") }
}
