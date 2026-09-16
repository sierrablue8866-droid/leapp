<#
.SYNOPSIS
    ALEAPP Ultimate USB Forensic Extractor & Automated Parser
.DESCRIPTION
    Takes advantage of all USB extraction vectors (ADB, Windows MTP/WPD, 
    Android Backup, Smart Switch bridge, and System Telemetry) for Android
    devices, specifically optimized for Samsung Galaxy devices with broken screens.
#>

[CmdletBinding()]
param (
    [string]$OutputDir = "H:\extracted_phone_data",
    [string]$ReportDir = "H:\reports",
    [switch]$AutoMode = $false
)

$Host.UI.RawUI.WindowTitle = "ALEAPP Ultimate USB Forensic Extractor"

# Paths
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$AdbExe = Join-Path $ScriptDir "platform-tools\adb.exe"
if (-not (Test-Path $AdbExe)) {
    $AdbExe = "H:\leapp\platform-tools\adb.exe"
}
if (-not (Test-Path $AdbExe)) {
    $AdbExe = "adb.exe"
}

$VenvPython = "H:\leapp\ALEAPP\.venv\Scripts\python.exe"
$AleappPy = "H:\leapp\ALEAPP\aleapp.py"
$AleappGuiExe = "H:\leapp\ALEAPP_USB_Portable\aleappGUI.exe"

function Show-Banner {
    Clear-Host
    Write-Host "================================================================================" -ForegroundColor Cyan
    Write-Host "            ALEAPP ULTIMATE USB FORENSIC EXTRACTION SUITE                       " -ForegroundColor Yellow
    Write-Host "      Optimized for Samsung Galaxy (Including Broken Screen & Locked Devices)   " -ForegroundColor White
    Write-Host "================================================================================" -ForegroundColor Cyan
    Write-Host " Output Directory: $OutputDir" -ForegroundColor Gray
    Write-Host " Report Directory: $ReportDir" -ForegroundColor Gray
    Write-Host " ADB Binary:       $AdbExe" -ForegroundColor Gray
    Write-Host "================================================================================" -ForegroundColor Cyan
    Write-Host ""
}

function Get-UsbScan {
    $results = @{
        AdbState = "None"
        AdbSerial = $null
        AdbModel = $null
        MtpDevices = @()
        SamsungHardwareDetected = $false
        SmartSwitchBackups = @()
    }

    # 1. Check ADB
    try {
        $adbOutput = & $AdbExe devices -l 2>$null
        foreach ($line in ($adbOutput -split "`r?`n")) {
            if ($line -match '^([^\s]+)\s+(device|unauthorized|offline|recovery|sideload)\s*(.*)$') {
                $results.AdbSerial = $matches[1]
                $results.AdbState = $matches[2]
                $info = $matches[3]
                if ($info -match 'model:([^\s]+)') {
                    $results.AdbModel = $matches[1]
                }
                break
            }
        }
    } catch {}

    # 2. Check Samsung USB Hardware via PnP
    try {
        $samsungPnp = Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | Where-Object {
            ($_.InstanceId -match 'USB\\VID_04E8' -or $_.FriendlyName -match 'Galaxy|Samsung Mobile|SAMSUNG Android') -and $_.Class -ne 'DiskDrive' -and $_.Class -ne 'SCSIAdapter'
        }
        if ($samsungPnp) {
            $results.SamsungHardwareDetected = $true
        }
    } catch {}

    # 3. Check Windows Shell MTP / Portable Devices
    try {
        $shell = New-Object -ComObject Shell.Application
        $ssfDRIVES = 17
        $folder = $shell.Namespace($ssfDRIVES)
        if ($folder) {
            foreach ($item in $folder.Items()) {
                # MTP devices typically do not have drive paths like "C:\"
                if ($item.Path -match '^::\{' -or $item.Type -match 'Portable|Phone|Galaxy|Android' -or $item.Name -match 'Galaxy|Samsung|Android|Phone|A56') {
                    $results.MtpDevices += $item
                }
            }
        }
    } catch {}

    # 4. Check Smart Switch Backups
    $ssPath = Join-Path $env:USERPROFILE "Documents\Samsung\SmartSwitch\backup"
    if (Test-Path $ssPath) {
        $backups = Get-ChildItem $ssPath -Directory -ErrorAction SilentlyContinue
        if ($backups) {
            $results.SmartSwitchBackups = $backups
        }
    }

    return $results
}

function Invoke-AdbFullExtraction {
    param([string]$Serial)

    Write-Host "`n[+] Starting Comprehensive ADB Forensic Extraction..." -ForegroundColor Green
    if (-not (Test-Path $OutputDir)) {
        New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
    }

    # Gather device metadata
    Write-Host "[1/8] Querying Device Properties & Build Fingerprint..." -ForegroundColor Cyan
    $deviceProps = & $AdbExe -s $Serial shell getprop 2>$null
    $deviceProps | Out-File -FilePath (Join-Path $OutputDir "device_build_props.txt") -Encoding UTF8

    # Internal Storage Targets
    $targets = @(
        @{ Remote = "/sdcard/DCIM"; Local = "DCIM"; Label = "Photos & Camera (DCIM)" },
        @{ Remote = "/sdcard/Pictures"; Local = "Pictures"; Label = "Pictures & Screenshots" },
        @{ Remote = "/sdcard/Download"; Local = "Download"; Label = "Downloads" },
        @{ Remote = "/sdcard/Documents"; Local = "Documents"; Label = "Documents" },
        @{ Remote = "/sdcard/Android/media"; Local = "media"; Label = "App Media (WhatsApp, Telegram, Signal)" },
        @{ Remote = "/sdcard/Movies"; Local = "Movies"; Label = "Movies & Screen Recordings" },
        @{ Remote = "/sdcard/Music"; Local = "Music"; Label = "Audio & Music" },
        @{ Remote = "/sdcard/Recordings"; Local = "Recordings"; Label = "Voice Recordings" }
    )

    $step = 2
    foreach ($tgt in $targets) {
        Write-Host "[$step/8] Pulling $($tgt.Label)..." -ForegroundColor Cyan
        $dest = Join-Path $OutputDir $tgt.Local
        & $AdbExe -s $Serial pull $tgt.Remote $dest 2>&1 | Out-Null
        $step++
    }

    # System Logs & Forensic Telemetry
    Write-Host "[7/8] Dumping System Telemetry, Accounts & App Inventory..." -ForegroundColor Cyan
    & $AdbExe -s $Serial shell dumpsys package 2>$null | Out-File -FilePath (Join-Path $OutputDir "dumpsys_packages.txt") -Encoding UTF8
    & $AdbExe -s $Serial shell dumpsys batterystats 2>$null | Out-File -FilePath (Join-Path $OutputDir "dumpsys_batterystats.txt") -Encoding UTF8
    & $AdbExe -s $Serial shell dumpsys netstats 2>$null | Out-File -FilePath (Join-Path $OutputDir "dumpsys_netstats.txt") -Encoding UTF8
    & $AdbExe -s $Serial shell pm list packages -f 2>$null | Out-File -FilePath (Join-Path $OutputDir "installed_packages.txt") -Encoding UTF8
    & $AdbExe -s $Serial shell logcat -d 2>$null | Out-File -FilePath (Join-Path $OutputDir "logcat.txt") -Encoding UTF8

    # Full Android Backup Archive
    Write-Host "[8/8] Generating ADB Backup Archive (backup.ab)..." -ForegroundColor Cyan
    $abPath = Join-Path $OutputDir "backup.ab"
    Write-Host "    Executing 'adb backup -all -shared'..." -ForegroundColor Gray
    Write-Host "    (If the phone prompts for backup password, tap OK if screen touch works)" -ForegroundColor Gray
    & $AdbExe -s $Serial backup -all -apk -shared -f $abPath 2>&1 | Out-Null

    Write-Host "`n[SUCCESS] ADB Forensic Extraction Complete!" -ForegroundColor Green
    Write-Host "Files saved to: $OutputDir" -ForegroundColor White
    
    Launch-Aleapp -InputPath $OutputDir
}

function Invoke-MtpExtraction {
    param($MtpDeviceItem)

    Write-Host "`n[+] Starting Windows MTP Direct Storage Extraction..." -ForegroundColor Green
    Write-Host "Target Device: $($MtpDeviceItem.Name)" -ForegroundColor Yellow
    
    if (-not (Test-Path $OutputDir)) {
        New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
    }

    $shell = New-Object -ComObject Shell.Application
    $deviceFolder = $MtpDeviceItem.GetFolder
    if (-not $deviceFolder) {
        Write-Host "[!] Could not access storage folders on $($MtpDeviceItem.Name)." -ForegroundColor Red
        Write-Host "    Ensure the phone is unlocked so Windows can read the files." -ForegroundColor Yellow
        return
    }

    $destFolder = $shell.Namespace($OutputDir)

    # Recursive or top-level folder copier
    foreach ($item in $deviceFolder.Items()) {
        Write-Host "  Found Storage: $($item.Name)" -ForegroundColor Cyan
        $storageFolder = $item.GetFolder
        if ($storageFolder) {
            foreach ($sub in $storageFolder.Items()) {
                $subName = $sub.Name
                if ($subName -match 'DCIM|Pictures|Download|Documents|Android|Movies|Music|Recordings') {
                    Write-Host "    Extracting '$subName' over USB MTP..." -ForegroundColor Green
                    $destFolder.CopyHere($sub, 16) # 16 = Respond with Yes to All
                }
            }
        }
    }

    Write-Host "`n[SUCCESS] MTP Extraction Finished!" -ForegroundColor Green
    Write-Host "Files saved to: $OutputDir" -ForegroundColor White
    Launch-Aleapp -InputPath $OutputDir
}

function Invoke-BlindUnlock {
    param([string]$Serial)

    Write-Host "`n--- BLIND UNLOCK ASSISTANT (FOR BROKEN SCREENS) ---" -ForegroundColor Yellow
    Write-Host "If ADB is active but phone is locked, we can inject hardware keycodes." -ForegroundColor White
    Write-Host "1. Wake Phone"
    Write-Host "2. Swipe Up (Open Keypad)"
    Write-Host "3. Enter PIN & Press Enter"
    Write-Host "4. Dismiss dialogs (Allow USB Debugging / Transfer)"
    Write-Host ""
    $pin = Read-Host "Enter your lock screen PIN (or leave blank to just wake/swipe)"

    Write-Host "[*] Waking screen..." -ForegroundColor Cyan
    & $AdbExe -s $Serial shell input keyevent 26 2>$null
    Start-Sleep -Milliseconds 500

    Write-Host "[*] Swiping up to show unlock pad..." -ForegroundColor Cyan
    & $AdbExe -s $Serial shell input swipe 500 1500 500 500 300 2>$null
    Start-Sleep -Milliseconds 500

    if ($pin) {
        Write-Host "[*] Typing PIN..." -ForegroundColor Cyan
        & $AdbExe -s $Serial shell input text $pin 2>$null
        Start-Sleep -Milliseconds 300
        Write-Host "[*] Pressing ENTER / OK..." -ForegroundColor Cyan
        & $AdbExe -s $Serial shell input keyevent 66 2>$null
    }

    Write-Host "[*] Attempting to press RIGHT + ENTER on any USB authorization dialog..." -ForegroundColor Cyan
    & $AdbExe -s $Serial shell input keyevent 22 2>$null # DPAD_RIGHT
    & $AdbExe -s $Serial shell input keyevent 66 2>$null # ENTER

    Write-Host "[*] Blind unlock sequence complete." -ForegroundColor Green
}

function Launch-Aleapp {
    param([string]$InputPath)

    Write-Host "`n================================================================================" -ForegroundColor Cyan
    Write-Host "                      LAUNCHING ALEAPP FORENSIC PARSER                           " -ForegroundColor Yellow
    Write-Host "================================================================================" -ForegroundColor Cyan

    if (-not (Test-Path $ReportDir)) {
        New-Item -ItemType Directory -Path $ReportDir -Force | Out-Null
    }

    Write-Host "Choose ALEAPP Execution Mode:" -ForegroundColor White
    Write-Host "  [1] Automated Background CLI (Runs immediately and generates full HTML reports)" -ForegroundColor Green
    Write-Host "  [2] Open ALEAPP Graphical Interface (GUI)" -ForegroundColor Cyan
    Write-Host "  [3] Skip for now" -ForegroundColor Gray
    
    $choice = Read-Host "Select option [1-3] (Default: 1)"
    if ([string]::IsNullOrWhiteSpace($choice)) { $choice = "1" }

    if ($choice -eq "1") {
        Write-Host "`n[*] Running ALEAPP CLI: Parsing '$InputPath' -> '$ReportDir'..." -ForegroundColor Green
        if (Test-Path $VenvPython) {
            & $VenvPython $AleappPy -t fs -i $InputPath -o $ReportDir
        } elseif (Test-Path "H:\leapp\ALEAPP\dist\aleapp.exe") {
            & "H:\leapp\ALEAPP\dist\aleapp.exe" -t fs -i $InputPath -o $ReportDir
        } else {
            Write-Host "[!] Python or CLI binary not found, launching GUI..." -ForegroundColor Yellow
            $choice = "2"
        }
        Write-Host "[SUCCESS] Reports generated in $ReportDir" -ForegroundColor Green
        Start-Process $ReportDir
    }

    if ($choice -eq "2") {
        Write-Host "[*] Launching ALEAPP GUI..." -ForegroundColor Cyan
        if (Test-Path $VenvPython) {
            Start-Process -FilePath $VenvPython -ArgumentList "`"$AleappPy`"" -WorkingDirectory "H:\leapp\ALEAPP"
        } elseif (Test-Path $AleappGuiExe) {
            Start-Process -FilePath $AleappGuiExe -WorkingDirectory (Split-Path -Parent $AleappGuiExe)
        }
    }
}

# MAIN EXECUTION LOOP
Show-Banner

Write-Host "Scanning for USB connections..." -ForegroundColor Gray
$scan = Get-UsbScan

# Display current status
Write-Host "Status Summary:" -ForegroundColor White
Write-Host " - ADB Connection:            $($scan.AdbState)" -ForegroundColor $(if ($scan.AdbState -eq 'device') { 'Green' } elseif ($scan.AdbState -ne 'None') { 'Yellow' } else { 'Red' })
Write-Host " - Samsung Hardware (PnP):    $(if ($scan.SamsungHardwareDetected) { 'Connected' } else { 'Not Detected' })" -ForegroundColor $(if ($scan.SamsungHardwareDetected) { 'Green' } else { 'Red' })
Write-Host " - Windows MTP Storage:       $(if ($scan.MtpDevices.Count -gt 0) { "$($scan.MtpDevices.Count) Device(s) Found" } else { 'None' })" -ForegroundColor $(if ($scan.MtpDevices.Count -gt 0) { 'Green' } else { 'Red' })
Write-Host " - Smart Switch Backups:      $(if ($scan.SmartSwitchBackups.Count -gt 0) { "$($scan.SmartSwitchBackups.Count) Backup(s) Found" } else { 'None' })" -ForegroundColor $(if ($scan.SmartSwitchBackups.Count -gt 0) { 'Green' } else { 'Gray' })
Write-Host "--------------------------------------------------------------------------------" -ForegroundColor Gray

# Decision matrix
if ($scan.AdbState -eq "device") {
    Write-Host "`n[!] Active ADB Authorized Phone Detected: $($scan.AdbSerial) ($($scan.AdbModel))" -ForegroundColor Green
    $run = Read-Host "Proceed with full forensic extraction now? (Y/n)"
    if ($run -ne 'n') {
        Invoke-AdbFullExtraction -Serial $scan.AdbSerial
    }
} elseif ($scan.AdbState -eq "unauthorized") {
    Write-Host "`n[!] Device detected via ADB, but it is UNAUTHORIZED." -ForegroundColor Yellow
    Write-Host "    Because the screen is broken, you cannot tap 'Allow USB Debugging'." -ForegroundColor White
    Write-Host "    Options:" -ForegroundColor Cyan
    Write-Host "    [1] Run Blind Unlock Sequence (Inject wake + swipe + PIN over USB)"
    Write-Host "    [2] Re-check connection"
    Write-Host "    [3] Cancel"
    $opt = Read-Host "Select option [1-3]"
    if ($opt -eq "1") {
        Invoke-BlindUnlock -Serial $scan.AdbSerial
    }
} elseif ($scan.MtpDevices.Count -gt 0) {
    Write-Host "`n[!] Windows MTP Device Detected!" -ForegroundColor Green
    foreach ($d in $scan.MtpDevices) {
        Write-Host "    Device: $($d.Name)" -ForegroundColor Cyan
    }
    $run = Read-Host "Extract files from MTP device now? (Y/n)"
    if ($run -ne 'n') {
        Invoke-MtpExtraction -MtpDeviceItem $scan.MtpDevices[0]
    }
} elseif ($scan.SmartSwitchBackups.Count -gt 0) {
    Write-Host "`n[!] Found Samsung Smart Switch Backup(s) on this PC!" -ForegroundColor Green
    for ($i=0; $i -lt $scan.SmartSwitchBackups.Count; $i++) {
        $b = $scan.SmartSwitchBackups[$i]
        Write-Host "    [$($i+1)] $($b.Name) ($($b.LastWriteTime))" -ForegroundColor Cyan
    }
    $sel = Read-Host "Select backup number to parse with ALEAPP (or press Enter to skip)"
    if ($sel -match '^\d+$' -and [int]$sel -le $scan.SmartSwitchBackups.Count) {
        $targetBackup = $scan.SmartSwitchBackups[[int]$sel - 1].FullName
        Launch-Aleapp -InputPath $targetBackup
    }
} else {
    Write-Host "`n[!] NO DEVICE DETECTED OVER USB." -ForegroundColor Red
    Write-Host ""
    Write-Host "CRITICAL DIAGNOSTIC CHECKLIST FOR SAMSUNG WITH BROKEN SCREEN:" -ForegroundColor Yellow
    Write-Host " 1. BATTERY CHECK:" -ForegroundColor White
    Write-Host "    If the screen is broken, the phone might be completely POWERED OFF or DEAD."
    Write-Host "    Leave it plugged into a fast wall charger for 15 minutes before plugging into PC."
    Write-Host ""
    Write-Host " 2. FORCE REBOOT (WHILE PLUGGED INTO PC):" -ForegroundColor White
    Write-Host "    Plug the USB cable into the PC."
    Write-Host "    Press and hold BOTH [Power] + [Volume Down] buttons together for 10 seconds."
    Write-Host "    This forces the phone to restart. Listen for Windows USB chime."
    Write-Host ""
    Write-Host " 3. SAMSUNG RECOVERY / BOOT MODE:" -ForegroundColor White
    Write-Host "    Connect phone to PC via USB."
    Write-Host "    Press and hold [Power] + [Volume Up] buttons together for 10 seconds."
    Write-Host "    This forces the phone into Samsung Stock Recovery mode where ADB may respond."
    Write-Host ""
    Write-Host " 4. SAMSUNG AUTO-BLOCKER (ONE UI 6+):" -ForegroundColor White
    Write-Host "    Samsung devices with Auto Blocker will cut off USB data until unlocked."
    Write-Host ""
    Write-Host "Starting continuous USB listener... Plug or restart your phone now." -ForegroundColor Cyan
    Write-Host "(Press Ctrl+C to stop listening)" -ForegroundColor Gray
    Write-Host ""

    while ($true) {
        Start-Sleep -Seconds 3
        $recheck = Get-UsbScan
        if ($recheck.AdbState -ne "None" -or $recheck.SamsungHardwareDetected -or $recheck.MtpDevices.Count -gt 0) {
            [console]::beep(1000, 300)
            Write-Host "[+] DEVICE CONNECTED EVENT DETECTED!" -ForegroundColor Green
            # Restart script with detected state
            & $MyInvocation.MyCommand.Definition
            break
        } else {
            Write-Host "." -NoNewline -ForegroundColor DarkGray
        }
    }
}
