$files = @(
    "app/core/config.py",
    "app/extensions.py",
    "app/models/dialog.py",
    "app/models/message.py",
    "app/services/dialog_service.py",
    "app/services/message_service.py",
    "app/web/routes.py",
    "pyproject.toml",
    "tests/conftest.py"
)

foreach ($file in $files) {
    Write-Output "`n===== $file ====="
    if (Test-Path $file) {
        Get-Content -LiteralPath $file -Raw
    } else {
        Write-Output "Файл отсутствует"
    }
}