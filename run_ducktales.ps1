param(
    [Nullable[long]]$Steps,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$PlayerArguments
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$arguments = @()
if ($null -ne $Steps) {
    $arguments += @('--steps', [string]$Steps)
}
$arguments += $PlayerArguments
& python (Join-Path $projectRoot 'scripts\play.py') @arguments
exit $LASTEXITCODE
