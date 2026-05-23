# =================================================================================
# SCRIPT 2: START AI PIPELINE (XTTS V2 - ROBUST DOCKER ARGUMENTS)
# =================================================================================

Write-Host "=== Starting AI Model Server Pipeline ===" -ForegroundColor Cyan

# =================================================================================
# CONFIGURATION
# =================================================================================

$LocalIP = $env:SPEECHSERVER_LOCAL_IP

$OllamaModel = "qwen3-30b-32k"
$OllamaKeepAlive = "24h"
$OllamaContext = 32768
$OllamaHost = $env:OLLAMA_HOST

$WhisperName = "faster-whisper-server"
$XTTSName = "xtts-api-server"

$WhisperGpu = "1"
$XTTSGpu = "1"

$XTTSImage = "daswer123/xtts-api-server:latest"

$XTTSBasePath = "$env:USERPROFILE\Documents\xtts-api-server"
$XTTSSpeakerPath = "$XTTSBasePath\speakers"
$XTTSOutputPath = "$XTTSBasePath\output"
$XTTSModelPath = "$XTTSBasePath\models"

# =================================================================================
# HELPER FUNCTIONS
# =================================================================================

function Test-DockerContainerRunning {
    param (
        [string]$ContainerName
    )

    $Status = docker inspect -f "{{.State.Running}}" $ContainerName 2>$null

    if ($Status -eq "true") {
        return $true
    }

    return $false
}

function Ensure-Folder {
    param (
        [string]$Path
    )

    if (-not (Test-Path $Path)) {
        Write-Host "Creating folder: $Path" -ForegroundColor DarkGray
        New-Item -ItemType Directory -Path $Path -Force > $null
    }
}

function Test-OllamaModelExists {
    param (
        [string]$ModelName
    )

    ollama show $ModelName > $null 2>$null
    return ($LASTEXITCODE -eq 0)
}

function Load-OllamaModel {
    param (
        [string]$ModelName,
        [string]$KeepAlive,
        [int]$Context
    )

    $BodyObject = @{
        model = $ModelName
        prompt = "/no_think`nready"
        stream = $false
        keep_alive = $KeepAlive
        options = @{
            num_ctx = $Context
            num_predict = 1
        }
    }

    $BodyJson = $BodyObject | ConvertTo-Json -Depth 10

    Invoke-RestMethod `
        -Uri "http://localhost:11434/api/generate" `
        -Method POST `
        -ContentType "application/json; charset=utf-8" `
        -Body ([System.Text.Encoding]::UTF8.GetBytes($BodyJson)) | Out-Null
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
# CREATE FOLDERS
# =================================================================================

Ensure-Folder $XTTSBasePath
Ensure-Folder $XTTSSpeakerPath
Ensure-Folder $XTTSOutputPath
Ensure-Folder $XTTSModelPath

# =================================================================================
# OLLAMA / LLM
# =================================================================================

Write-Host "`n[1/3] Starting Ollama server (LLM)..." -ForegroundColor Yellow

if (-not $LocalIP -or $LocalIP.Trim() -eq "") {
    $LocalIP = Get-LocalIPv4Address
}

if (-not $OllamaHost -or $OllamaHost.Trim() -eq "") {
    $OllamaHost = "0.0.0.0:11434"
}

$env:OLLAMA_HOST = $OllamaHost

Write-Host ""
Write-Host "Using local IP address: $LocalIP" -ForegroundColor Green
Write-Host "Ollama host binding: $OllamaHost" -ForegroundColor Green
Write-Host "Ollama model: $OllamaModel" -ForegroundColor Green
Write-Host "Whisper GPU: $WhisperGpu" -ForegroundColor Green
Write-Host "XTTS GPU: $XTTSGpu" -ForegroundColor Green
Write-Host "XTTS Image: $XTTSImage" -ForegroundColor Green

$OllamaProcess = Get-Process -Name "ollama" -ErrorAction SilentlyContinue

if (-not $OllamaProcess) {
    Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Hidden
    Start-Sleep -Seconds 3
} else {
    Write-Host "Ollama is already running." -ForegroundColor DarkGray
}

Write-Host "[OK] Ollama API is running at http://${LocalIP}:11434/v1" -ForegroundColor Green

if (-not (Test-OllamaModelExists $OllamaModel)) {
    Write-Host "[ERROR] Ollama model '$OllamaModel' was not found." -ForegroundColor Red
    Write-Host "Run .\install.bat first to pull qwen3:30b and create the 32k model variant." -ForegroundColor Yellow
    pause
    exit 1
}

Write-Host "Loading Ollama model '$OllamaModel' with $OllamaContext context and keepalive $OllamaKeepAlive..." -ForegroundColor DarkGray

try {
    Load-OllamaModel -ModelName $OllamaModel -KeepAlive $OllamaKeepAlive -Context $OllamaContext
} catch {
    Write-Host "[ERROR] Failed to load Ollama model '$OllamaModel'." -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Yellow
    pause
    exit 1
}

Write-Host "[OK] Ollama model '$OllamaModel' is loaded and ready." -ForegroundColor Green

# =================================================================================
# FASTER-WHISPER / STT
# =================================================================================

Write-Host "`n[2/3] Starting Faster-Whisper server (STT)..." -ForegroundColor Yellow

Write-Host "Removing old Faster-Whisper container, if present..." -ForegroundColor DarkGray
docker rm -f $WhisperName 2>$null | Out-Null

Write-Host "Creating new Faster-Whisper container..." -ForegroundColor DarkGray

$WhisperArgs = @(
    "run",
    "-d",
    "--gpus", "all",
    "-e", "CUDA_VISIBLE_DEVICES=$WhisperGpu",
    "--name", $WhisperName,
    "-p", "8001:8000",
    "-e", "WHISPER_MODEL=turbo",
    "-e", "WHISPER_BACKEND=ctranslate2",
    "-e", "WHISPER_LANGUAGE=de",
    "fedirz/faster-whisper-server:latest-cuda"
)

& docker.exe @WhisperArgs | Out-Null

if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] docker run for Faster-Whisper failed." -ForegroundColor Red
    pause
    exit 1
}

Start-Sleep -Seconds 2

if (-not (Test-DockerContainerRunning $WhisperName)) {
    Write-Host "[ERROR] Faster-Whisper container is not running." -ForegroundColor Red
    Write-Host "Docker-Logs:" -ForegroundColor Yellow
    docker logs $WhisperName
    pause
    exit 1
}

Write-Host "[OK] STT API is running at http://${LocalIP}:8001/v1" -ForegroundColor Green

# =================================================================================
# XTTS V2 / TTS
# =================================================================================

Write-Host "`n[3/3] Starting XTTS v2 server (TTS / Voice Cloning)..." -ForegroundColor Yellow

Write-Host "Removing old Piper containers, if present..." -ForegroundColor DarkGray
docker rm -f piper-tts-server piper-backend-server 2>$null | Out-Null

Write-Host "Removing old XTTS container, if present..." -ForegroundColor DarkGray
docker rm -f $XTTSName 2>$null | Out-Null

Write-Host "Creating new XTTS v2 container..." -ForegroundColor DarkGray

$XTTSArgs = @(
    "run",
    "-d",
    "--gpus", "all",
    "-e", "CUDA_VISIBLE_DEVICES=$XTTSGpu",
    "--name", $XTTSName,
    "-p", "8002:8020",
    "-e", "COQUI_TOS_AGREED=1",
    "-v", "${XTTSSpeakerPath}:/speakers",
    "-v", "${XTTSOutputPath}:/output",
    "-v", "${XTTSModelPath}:/models",
    $XTTSImage,
    "python3",
    "-m", "xtts_api_server",
    "--listen",
    "--host", "0.0.0.0",
    "--port", "8020",
    "--speaker-folder", "/speakers",
    "--output", "/output",
    "--model-folder", "/models"
)

Write-Host ""
Write-Host "Docker command for XTTS:" -ForegroundColor DarkGray
Write-Host "docker $($XTTSArgs -join ' ')" -ForegroundColor DarkGray
Write-Host ""

& docker.exe @XTTSArgs | Out-Null

if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] docker run for XTTS failed." -ForegroundColor Red
    Write-Host "Check the Docker command printed above." -ForegroundColor Yellow
    pause
    exit 1
}

Start-Sleep -Seconds 12

if (-not (Test-DockerContainerRunning $XTTSName)) {
    Write-Host "[ERROR] XTTS container is not running." -ForegroundColor Red
    Write-Host ""
    Write-Host "Docker-Logs:" -ForegroundColor Yellow
    docker logs $XTTSName
    pause
    exit 1
}

Write-Host "[OK] XTTS v2 API is running at http://${LocalIP}:8002" -ForegroundColor Green
Write-Host "[OK] XTTS API Docs: http://${LocalIP}:8002/docs" -ForegroundColor Green

# =================================================================================
# OUTPUT
# =================================================================================

Write-Host "`n==================================================" -ForegroundColor Cyan
Write-Host "  Your AI pipeline is ready!" -ForegroundColor Green
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "Endpoints for your client apps:" -ForegroundColor White
Write-Host "- LLM (Ollama/Qwen):     http://${LocalIP}:11434/v1  model: $OllamaModel" -ForegroundColor White
Write-Host "- STT (Whisper):         http://${LocalIP}:8001/v1" -ForegroundColor White
Write-Host "- TTS (XTTS v2):         http://${LocalIP}:8002" -ForegroundColor White
Write-Host "- TTS API Docs:          http://${LocalIP}:8002/docs" -ForegroundColor White
Write-Host "--------------------------------------------------" -ForegroundColor Cyan
Write-Host "Place voice-cloning samples here:" -ForegroundColor Yellow
Write-Host $XTTSSpeakerPath -ForegroundColor White
Write-Host "==================================================" -ForegroundColor Cyan

pause
