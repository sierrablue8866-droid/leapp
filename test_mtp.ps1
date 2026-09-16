$s = New-Object -ComObject Shell.Application
foreach ($i in $s.Namespace(17).Items()) {
    Write-Host "Found Item: $($i.Name) | Path: $($i.Path)"
    $f = $i.GetFolder
    if ($f) {
        foreach ($sub in $f.Items()) {
            Write-Host "  Sub-Folder: $($sub.Name)"
        }
    }
}
