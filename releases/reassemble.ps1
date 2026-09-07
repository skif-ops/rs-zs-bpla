param(
    [Parameter(Mandatory = $true)][string]$PartsDirectory,
    [Parameter(Mandatory = $true)][string]$OutputZip
)

$parts = Get-ChildItem -LiteralPath $PartsDirectory -Filter 'part-*' | Sort-Object Name
if (-not $parts) { throw "Parts not found: $PartsDirectory" }

$output = [System.IO.File]::Create($OutputZip)
try {
    foreach ($part in $parts) {
        $input = [System.IO.File]::OpenRead($part.FullName)
        try { $input.CopyTo($output) } finally { $input.Dispose() }
    }
} finally {
    $output.Dispose()
}

Get-FileHash -Algorithm SHA256 -LiteralPath $OutputZip

