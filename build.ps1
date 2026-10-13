$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$version = Get-Content -Raw (Join-Path $projectRoot "version.json") | ConvertFrom-Json
$versionMatch = [regex]::Match($version.version, '^v(?<major>\d+)\.(?<minor>\d+)$')
if (-not $versionMatch.Success) {
    throw "Unsupported version format '$($version.version)'. Expected vMAJOR.MINOR."
}

$versionFile = Join-Path $projectRoot "version_info.txt"
$versionInfo = @"
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=($($versionMatch.Groups['major'].Value), $($versionMatch.Groups['minor'].Value), 0, 0),
    prodvers=($($versionMatch.Groups['major'].Value), $($versionMatch.Groups['minor'].Value), 0, 0),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable('040904B0', [
        StringStruct('CompanyName', 'HDR2KTX2'),
        StringStruct('FileDescription', 'HDR to IBL cubemap KTX2 converter'),
        StringStruct('FileVersion', '$($version.version)'),
        StringStruct('InternalName', 'HDR2KTX2'),
        StringStruct('OriginalFilename', 'HDR2KTX2.exe'),
        StringStruct('ProductName', 'HDR2KTX2'),
        StringStruct('ProductVersion', '$($version.version)')
      ])
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"@
Set-Content -LiteralPath $versionFile -Value $versionInfo -Encoding ascii

$bundlePath = Join-Path $projectRoot "bundle"
$requiredFiles = @("cli.exe", "GltfIblSampler.dll", "ktx.dll", "vulkan-1.dll", "vcruntime140.dll", "msvcp140.dll")
foreach ($file in $requiredFiles) {
    if (-not (Test-Path -LiteralPath (Join-Path $bundlePath $file) -PathType Leaf)) {
        throw "Required native runtime file is missing: bundle/$file"
    }
}
if (-not (Test-Path -LiteralPath (Join-Path $bundlePath "shaders\filter.frag") -PathType Leaf)) {
    throw "Required shader is missing: bundle/shaders/filter.frag"
}

Push-Location $projectRoot
try {
    python -m PyInstaller `
        --clean `
        --noconfirm `
        --onefile `
        --windowed `
        --name HDR2KTX2 `
        --version-file $versionFile `
        --add-data "version.json;." `
        --add-data "bundle;bundle" `
        main.py
} finally {
    Pop-Location
}
