# =================================================================================
# SCRIPT: STOP AI PIPELINE (XTTS V2 EDITION)
# =================================================================================

Write-Host "=== Stopping AI Model Server Pipeline ===" -ForegroundColor Cyan

# =================================================================================
# CONFIGURATION
# =================================================================================

$WhisperName = "faster-whisper-server"
$XTTSName = "xtts-api-server"

$OllamaModel = "qwen3-30b-32k"

# Old TTS containers from previous Piper/Wyoming variants
$OldPiperName = "piper-tts-server"
$OldPiperBackendName = "piper-backend-server"

# Should Ollama be stopped too?
# $true  = stop Ollama process
# $false = keep Ollama running
$StopOllama = $true

# Should the configured Ollama model be unloaded before stopping Ollama?
$UnloadOllamaModel = $true

# Should containers only be stopped or fully removed?
# $true  = docker rm -f, containers are removed
# $false = docker stop, containers remain available
$RemoveContainers = $false

# =================================================================================
# HELPER FUNCTIONS
# =================================================================================

function Test-DockerContainerExists {
    param (
        [string]$ContainerName
    )

    $Exists = docker ps -a --format "{{.Names}}" 2>$null | Select-String -Pattern "^$ContainerName$"

    if ($Exists) {
        return $true
    }

    return $false
}

function Stop-DockerContainerIfExists {
    param (
        [string]$ContainerName
    )

    if (Test-DockerContainerExists $ContainerName) {
        Write-Host "Stopping container: $ContainerName" -ForegroundColor Yellow
        docker stop $ContainerName 2>$null | Out-Null

        if ($LASTEXITCODE -eq 0) {
            Write-Host "[OK] Container stopped: $ContainerName" -ForegroundColor Green
        } else {
            Write-Host "[WARNING] Container may not have stopped: $ContainerName" -ForegroundColor Yellow
        }
    } else {
        Write-Host "[INFO] Container not found: $ContainerName" -ForegroundColor DarkGray
    }
}

function Remove-DockerContainerIfExists {
    param (
        [string]$ContainerName
    )

    if (Test-DockerContainerExists $ContainerName) {
        Write-Host "Removing container: $ContainerName" -ForegroundColor Yellow
        docker rm -f $ContainerName 2>$null | Out-Null

        if ($LASTEXITCODE -eq 0) {
            Write-Host "[OK] Container removed: $ContainerName" -ForegroundColor Green
        } else {
            Write-Host "[WARNING] Container may not have been removed: $ContainerName" -ForegroundColor Yellow
        }
    } else {
        Write-Host "[INFO] Container not found: $ContainerName" -ForegroundColor DarkGray
    }
}

function Stop-Or-Remove-Container {
    param (
        [string]$ContainerName
    )

    if ($RemoveContainers) {
        Remove-DockerContainerIfExists $ContainerName
    } else {
        Stop-DockerContainerIfExists $ContainerName
    }
}

# =================================================================================
# 1) STOP STT
# =================================================================================

Write-Host "`n[1/3] Stopping Faster-Whisper server (STT)..." -ForegroundColor Cyan

Stop-Or-Remove-Container $WhisperName

# =================================================================================
# 2) STOP XTTS V2
# =================================================================================

Write-Host "`n[2/3] Stopping XTTS v2 server (TTS / Voice Cloning)..." -ForegroundColor Cyan

Stop-Or-Remove-Container $XTTSName

# Clean up old Piper leftovers too
Write-Host "`nCleaning up old Piper leftovers, if present..." -ForegroundColor Cyan

Stop-Or-Remove-Container $OldPiperName
Stop-Or-Remove-Container $OldPiperBackendName

# =================================================================================
# 3) STOP OLLAMA
# =================================================================================

Write-Host "`n[3/3] Stopping Ollama server (LLM)..." -ForegroundColor Cyan

$OllamaProcesses = Get-Process -Name "ollama" -ErrorAction SilentlyContinue

if ($UnloadOllamaModel -and $OllamaProcesses) {
    Write-Host "Unloading Ollama model: $OllamaModel" -ForegroundColor Yellow
    ollama stop $OllamaModel 2>$null | Out-Null

    if ($LASTEXITCODE -eq 0) {
        Write-Host "[OK] Ollama model unloaded: $OllamaModel" -ForegroundColor Green
    } else {
        Write-Host "[INFO] Ollama model was not loaded or could not be unloaded: $OllamaModel" -ForegroundColor DarkGray
    }
}

if ($StopOllama) {
    if ($OllamaProcesses) {
        Write-Host "Stopping Ollama process..." -ForegroundColor Yellow
        $OllamaProcesses | Stop-Process -Force
        Write-Host "[OK] Ollama stopped." -ForegroundColor Green
    } else {
        Write-Host "[INFO] Ollama process not found." -ForegroundColor DarkGray
    }
} else {
    Write-Host "[INFO] Ollama remains active because StopOllama is set to false." -ForegroundColor DarkGray
}

# =================================================================================
# STATUS
# =================================================================================

Write-Host "`n==================================================" -ForegroundColor Cyan
Write-Host "  AI pipeline has been stopped." -ForegroundColor Green
Write-Host "==================================================" -ForegroundColor Cyan

Write-Host "Current relevant Docker containers:" -ForegroundColor White

$RelevantContainers = docker ps -a --format "table {{.Names}}\t{{.Ports}}\t{{.Status}}" |
    Select-String -Pattern "faster-whisper|xtts|piper"

if ($RelevantContainers) {
    $RelevantContainers
} else {
    Write-Host "[INFO] No relevant containers found." -ForegroundColor DarkGray
}

Write-Host "==================================================" -ForegroundColor Cyan

pause
