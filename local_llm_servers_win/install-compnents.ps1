# =================================================================================
# SCRIPT 1: PREPARE AI PIPELINE (OLLAMA + FASTER-WHISPER + XTTS V2)
# =================================================================================

Write-Host "=== AI Server System Preparation ===" -ForegroundColor Cyan

# =================================================================================
# CONFIGURATION
# =================================================================================

$LocalIP = $env:SPEECHSERVER_LOCAL_IP

$OllamaBaseModel = "qwen3:30b"
$OllamaModel = "qwen3-30b-32k"
$OllamaModelfile = ".\Modelfile.qwen3-30b-32k"

$WhisperName = "faster-whisper-server"
$WhisperImage = "fedirz/faster-whisper-server:latest-cuda"
$WhisperGpu = "1"

$XTTSName = "xtts-api-server"
$XTTSImage = "daswer123/xtts-api-server:latest"
$XTTSGpu = "1"

$XTTSBasePath = "$env:USERPROFILE\Documents\xtts-api-server"
$XTTSSpeakerPath = "$XTTSBasePath\speakers"
$XTTSOutputPath = "$XTTSBasePath\output"
$XTTSModelPath = "$XTTSBasePath\models"

$OldContainerNames = @(
    "kokoro-tts-server",
    "piper-tts-server",
    "piper-backend-server"
)

# =================================================================================
# HELPER FUNCTIONS
# =================================================================================

function Assert-CommandExists {
    param (
        [string]$CommandName,
        [string]$InstallHint
    )

    if (-not (Get-Command $CommandName -ErrorAction SilentlyContinue)) {
        Write-Host "[ERROR] '$CommandName' was not found." -ForegroundColor Red
        Write-Host $InstallHint -ForegroundColor Yellow
        pause
        exit 1
    }
}

function Assert-FileExists {
    param (
        [string]$Path,
        [string]$ErrorMessage
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        Write-Host "[ERROR] Required file was not found: $Path" -ForegroundColor Red
        Write-Host $ErrorMessage -ForegroundColor Yellow
        pause
        exit 1
    }
}

function Ensure-Folder {
    param (
        [string]$Path
    )

    if (-not (Test-Path $Path)) {
        Write-Host "Creating folder: $Path" -ForegroundColor DarkGray
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    } else {
        Write-Host "Folder already exists: $Path" -ForegroundColor DarkGray
    }
}

function Invoke-RequiredCommand {
    param (
        [string]$Description,
        [scriptblock]$Command
    )

    Write-Host ""
    Write-Host $Description -ForegroundColor Yellow

    & $Command

    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] Step failed: $Description" -ForegroundColor Red
        pause
        exit 1
    }
}

function Test-DockerContainerExists {
    param (
        [string]$ContainerName
    )

    $Exists = docker ps -a --format "{{.Names}}" 2>$null | Select-String -Pattern "^$ContainerName$"
    return [bool]$Exists
}

function Get-LocalIPv4Address {
    $Address = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object {
            $_.IPAddress -notlike "127.*" -and
            $_.IPAddress -notlike "169.254.*" -and
            $_.PrefixOrigin -ne "WellKnown"
        } |
        Select-Object -First 1 -ExpandProperty IPAddress

    if ($Address) {
        return $Address
    }

    return "localhost"
}

# =================================================================================
# BASIC CHECKS
# =================================================================================

if (-not $LocalIP -or $LocalIP.Trim() -eq "") {
    $LocalIP = Get-LocalIPv4Address
}

Write-Host ""
Write-Host "Configuration:" -ForegroundColor White
Write-Host "- Local IP:           $LocalIP" -ForegroundColor White
Write-Host "- Ollama base model:  $OllamaBaseModel" -ForegroundColor White
Write-Host "- Ollama test model:  $OllamaModel" -ForegroundColor White
Write-Host "- STT Image:          $WhisperImage" -ForegroundColor White
Write-Host "- STT GPU:            $WhisperGpu" -ForegroundColor White
Write-Host "- TTS Image:          $XTTSImage" -ForegroundColor White
Write-Host "- TTS GPU:            $XTTSGpu" -ForegroundColor White

Assert-CommandExists "docker" "Please install and start Docker Desktop."
Assert-CommandExists "ollama" "Please install Ollama: https://ollama.com"
Assert-CommandExists "nvidia-smi" "Please check your NVIDIA driver/CUDA support."
Assert-FileExists $OllamaModelfile "The Qwen3 30B 32k Modelfile must be next to this setup script."

Invoke-RequiredCommand "Checking Docker daemon..." {
    docker info | Out-Null
}

Write-Host ""
Write-Host "GPU overview:" -ForegroundColor Yellow
nvidia-smi

# =================================================================================
# CREATE FOLDERS
# =================================================================================

Write-Host ""
Write-Host "Creating XTTS working folders..." -ForegroundColor Yellow

Ensure-Folder $XTTSBasePath
Ensure-Folder $XTTSSpeakerPath
Ensure-Folder $XTTSOutputPath
Ensure-Folder $XTTSModelPath

# =================================================================================
# PREPARE IMAGES AND MODELS
# =================================================================================

Invoke-RequiredCommand "Pulling/updating Faster-Whisper CUDA image..." {
    docker pull $WhisperImage
}

Invoke-RequiredCommand "Pulling/updating XTTS v2 image..." {
    docker pull $XTTSImage
}

Invoke-RequiredCommand "Pulling Ollama base model $OllamaBaseModel..." {
    ollama pull $OllamaBaseModel
}

Invoke-RequiredCommand "Creating Ollama test model $OllamaModel..." {
    ollama create $OllamaModel -f $OllamaModelfile
}

Invoke-RequiredCommand "Verifying Ollama test model $OllamaModel..." {
    ollama show $OllamaModel | Out-Null
}

# =================================================================================
# REPORT OLD CONTAINERS FROM PREVIOUS VARIANTS
# =================================================================================

Write-Host ""
Write-Host "Checking old TTS containers from previous variants..." -ForegroundColor Yellow

foreach ($ContainerName in $OldContainerNames) {
    if (Test-DockerContainerExists $ContainerName) {
        Write-Host "[NOTICE] Old container found: $ContainerName" -ForegroundColor Yellow
        Write-Host "         Remove if needed with: docker rm -f $ContainerName" -ForegroundColor DarkGray
    }
}

# =================================================================================
# CURRENT TARGET STATE
# =================================================================================

Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  Preparation complete." -ForegroundColor Green
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "Start afterwards with: .\start.bat" -ForegroundColor White
Write-Host ""
Write-Host "Endpoints after startup:" -ForegroundColor White
Write-Host "- LLM (Ollama/Qwen):     http://${LocalIP}:11434/v1  model: $OllamaModel" -ForegroundColor White
Write-Host "- STT (Whisper):         http://${LocalIP}:8001/v1" -ForegroundColor White
Write-Host "- TTS (XTTS v2):         http://${LocalIP}:8002" -ForegroundColor White
Write-Host "- TTS API Docs:          http://${LocalIP}:8002/docs" -ForegroundColor White
Write-Host ""
Write-Host "Place voice-cloning samples here:" -ForegroundColor Yellow
Write-Host $XTTSSpeakerPath -ForegroundColor White
Write-Host "==================================================" -ForegroundColor Cyan

pause
