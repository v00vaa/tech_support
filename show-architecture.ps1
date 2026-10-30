param(
    [string]$Path = ".",
    [int]$MaxDepth = 10,
    [switch]$ShowHidden
)

$ErrorActionPreference = "Stop"

$Root = (Resolve-Path -LiteralPath $Path).Path

$ExcludedDirectories = @(
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    "node_modules",
    "dist",
    "build",
    ".idea",
    ".vscode",
    "htmlcov",
    "coverage",
    ".coverage",
    "site-packages"
)

$ExcludedFiles = @(
    "*.pyc",
    "*.pyo",
    "*.log",
    ".DS_Store",
    "Thumbs.db"
)

function Write-Tree {
    param(
        [string]$Directory,
        [string]$Prefix,
        [int]$Depth
    )

    if ($Depth -ge $MaxDepth) {
        $children = @(Get-ChildItem -LiteralPath $Directory -Force |
            Where-Object {
                $_.Name -notin $ExcludedDirectories -and
                $_.Name -notlike ".env" -and
                ($ShowHidden -or -not $_.Name.StartsWith("."))
            })

        if ($children.Count -gt 0) {
            Write-Output "$Prefix└── ... (достигнута максимальная глубина)"
        }

        return
    }

    $Items = @(Get-ChildItem -LiteralPath $Directory -Force |
        Where-Object {
            $item = $_

            if ($item.PSIsContainer) {
                return (
                    $item.Name -notin $ExcludedDirectories -and
                    ($ShowHidden -or -not $item.Name.StartsWith("."))
                )
            }

            if ($item.Name -eq ".env") {
                return $false
            }

            if (-not $ShowHidden -and $item.Name.StartsWith(".")) {
                return $false
            }

            foreach ($pattern in $ExcludedFiles) {
                if ($item.Name -like $pattern) {
                    return $false
                }
            }

            return $true
        } |
        Sort-Object @{ Expression = { -not $_.PSIsContainer } }, Name)

    for ($i = 0; $i -lt $Items.Count; $i++) {
        $Item = $Items[$i]
        $IsLast = $i -eq ($Items.Count - 1)

        if ($i -eq $Items.Count - 1) {
            $Branch = "\-- "
            $NextPrefix = $Prefix + "   "
        }
        else {
            $Branch = "|-- "
            $NextPrefix = $Prefix + "|  "
        }

        if ($Item.PSIsContainer) {
            Write-Output "$Prefix$Branch$($Item.Name)/"
            Write-Tree -Directory $Item.FullName -Prefix $NextPrefix -Depth ($Depth + 1)
        }
        else {
            Write-Output "$Prefix$Branch$($Item.Name)"
        }
    }
}

Write-Output ""
Write-Output "Архитектура проекта: $Root"
Write-Output ""

Write-Tree -Directory $Root -Prefix "" -Depth 0
