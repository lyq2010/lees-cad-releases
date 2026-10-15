# Windows can compare two/four compiler processes in an explicitly authorized run.
# macOS retains its existing two-process memory budget.
function Get-BuildJobs([bool]$WindowsHost, [ValidateSet(2, 4)][int]$WindowsJobs = 4,
                       [int]$LogicalCpus = [Environment]::ProcessorCount) {
    $budget = if ($WindowsHost) { $WindowsJobs } else { 2 }
    return [math]::Max(1, [math]::Min($LogicalCpus, $budget))
}
