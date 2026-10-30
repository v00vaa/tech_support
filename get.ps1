$files = @(
    "app/extensions.py",
    "app/models/employee.py",
    "app/models/role.py",
    "app/models/client.py",
    "pyproject.toml",
    "app/models/dialog.py",
    "app/models/message.py",
    "app/models/attachment.py"
)

foreach ($file in $files) {
    Write-Output "`n===== $file ====="
    if (Test-Path $file) {
        Get-Content -LiteralPath $file -Raw
    } else {
        Write-Output "Файл отсутствует"
    }
}