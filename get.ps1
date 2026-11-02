$files = @(
    "app\__init__.py",
    "app/extensions.py",
    "app/api/errors.py",
    "app/api/routes.py",
    "tests/conftest.py",
    "tests/api/test_health.py",
    "tests/unit/test_app_factory.py"
)

foreach ($file in $files) {
    Write-Output "`n===== $file ====="
    if (Test-Path $file) {
        Get-Content -LiteralPath $file -Raw
    } else {
        Write-Output "Файл отсутствует"
    }
}