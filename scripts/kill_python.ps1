$names = 'python','python3','pythonw','py'
$killed = @()
foreach ($name in $names) {
    try {
        $procs = Get-Process -Name $name -ErrorAction SilentlyContinue
        if ($procs) {
            foreach ($p in $procs) {
                Write-Host ("Killing $($p.ProcessName) PID $($p.Id)")
                try {
                    Stop-Process -Id $p.Id -Force -ErrorAction Stop
                    Write-Host ("Stopped PID $($p.Id)")
                    $killed += $p.Id
                } catch {
                    Write-Host ("Failed to stop PID $($p.Id): $($_.Exception.Message)")
                }
            }
        }
    } catch {
        # ignore
    }
}
$remaining = Get-Process -Name python,python3,pythonw,py -ErrorAction SilentlyContinue
if ($remaining) {
    Write-Host 'Remaining python processes:'
    $remaining | Format-Table -AutoSize
} else {
    if ($killed.Count -eq 0) { Write-Host 'No python processes found' } else { Write-Host 'No remaining python processes' }
}
