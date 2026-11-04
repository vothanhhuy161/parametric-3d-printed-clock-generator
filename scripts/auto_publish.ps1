$ErrorActionPreference = "Stop"

$repository = [System.IO.Path]::GetFullPath(
    (Join-Path $PSScriptRoot "..")
)
$expectedRemote = (
    "https://github.com/vothanhhuy161/" +
    "parametric-3d-printed-clock-generator"
)
$excludedPrefix = [System.IO.Path]::GetFullPath(
    (Join-Path $repository "3DPrintedClocksGithub")
).TrimEnd("\") + "\"
$quietPeriodSeconds = 3

function Invoke-Git {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$GitArguments
    )

    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $output = & git -C $repository @GitArguments 2>&1
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    if ($exitCode -ne 0) {
        throw "git $($GitArguments -join ' ') failed: $($output -join ' ')"
    }

    return @($output | ForEach-Object { $_.ToString() })
}

function Normalize-Remote {
    param([string]$Url)

    $normalized = $Url.Trim().TrimEnd("/")
    if ($normalized.EndsWith(".git", [System.StringComparison]::OrdinalIgnoreCase)) {
        $normalized = $normalized.Substring(0, $normalized.Length - 4)
    }
    if ($normalized.StartsWith("git@github.com:", [System.StringComparison]::OrdinalIgnoreCase)) {
        $normalized = "https://github.com/" + $normalized.Substring(15)
    }
    elseif ($normalized.StartsWith("ssh://git@github.com/", [System.StringComparison]::OrdinalIgnoreCase)) {
        $normalized = "https://github.com/" + $normalized.Substring(21)
    }

    return $normalized.ToLowerInvariant()
}

function Test-SourcePath {
    param([string]$Path)

    $fullPath = [System.IO.Path]::GetFullPath($Path)
    if ($fullPath.StartsWith(
        $excludedPrefix,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        return $false
    }

    if ($fullPath.Equals(
        (Join-Path $repository "README.md"),
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        return $true
    }

    if ([System.IO.Path]::GetExtension($fullPath) -ine ".py") {
        return $false
    }

    $relativePath = $fullPath.Substring($repository.Length).TrimStart("\")
    $excludedDirectory = '(^|\\)(\.git|\.venv|venv|env|generated_clock|GeneratedClock|__pycache__)(\\|$)'
    return $relativePath -notmatch $excludedDirectory
}

function Get-ChangedSourcePaths {
    $paths = @()
    $paths += Invoke-Git -GitArguments @("diff", "--name-only")
    $paths += Invoke-Git -GitArguments @("diff", "--cached", "--name-only")
    $paths += Invoke-Git -GitArguments @("ls-files", "--others", "--exclude-standard")

    $sourcePaths = @(
        $paths |
            Where-Object { $_ -and (Test-SourcePath (Join-Path $repository $_)) } |
            Sort-Object -Unique
    )
    return $sourcePaths
}

function Read-ConventionalCommitSubject {
    while ($true) {
        $subject = Read-Host (
            "Enter a Conventional Commit subject (for example, " +
            "feat(clock): add moon phase support; Enter to cancel)"
        )
        if ([string]::IsNullOrWhiteSpace($subject)) {
            return $null
        }
        if (
            $subject.Length -le 72 -and
            $subject -cmatch (
                '^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)' +
                '(\([a-z0-9][a-z0-9._/-]*\))?!?: [a-z].*$'
            )
        ) {
            return $subject
        }

        Write-Warning (
            "Use Conventional Commits: type(scope): imperative description, " +
            "lowercase after the colon, maximum 72 characters."
        )
    }
}

function Add-ChangelogEntry {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Subject
    )

    $type = ($Subject -split ":", 2)[0] -replace '\(.*\)$', '' -replace '!$', ''
    $category = switch ($type) {
        "feat" { "Added" }
        "fix" { "Fixed" }
        "docs" { "Changed" }
        "style" { "Changed" }
        "refactor" { "Changed" }
        "perf" { "Changed" }
        "test" { "Changed" }
        "build" { "Changed" }
        "ci" { "Changed" }
        "chore" { "Changed" }
        "revert" { "Changed" }
        default { throw "Unsupported Conventional Commit type: $type" }
    }

    $changelogPath = Join-Path $repository "CHANGELOG.md"
    if (Test-Path -LiteralPath $changelogPath) {
        $content = [System.IO.File]::ReadAllText($changelogPath)
        $lines = [System.Collections.Generic.List[string]]::new()
        foreach ($line in ($content -split "\r?\n")) {
            $lines.Add($line)
        }
    }
    else {
        $lines = [System.Collections.Generic.List[string]]::new()
        foreach ($line in @(
            "# Changelog",
            "",
            "All notable changes to this project are documented in this file.",
            "",
            "This changelog follows Keep a Changelog and Conventional Commits.",
            "",
            "## [Unreleased]",
            ""
        )) {
            $lines.Add($line)
        }
    }

    $unreleasedIndex = -1
    for ($index = 0; $index -lt $lines.Count; $index++) {
        if ($lines[$index] -match '^## \[Unreleased\]\s*$') {
            $unreleasedIndex = $index
            break
        }
    }
    if ($unreleasedIndex -lt 0) {
        throw "CHANGELOG.md must contain a '## [Unreleased]' section."
    }

    $sectionEnd = $lines.Count
    for ($index = $unreleasedIndex + 1; $index -lt $lines.Count; $index++) {
        if ($lines[$index] -match '^## \[') {
            $sectionEnd = $index
            break
        }
    }

    $categoryIndex = -1
    for ($index = $unreleasedIndex + 1; $index -lt $sectionEnd; $index++) {
        if ($lines[$index] -eq "### $category") {
            $categoryIndex = $index
            break
        }
    }

    if ($categoryIndex -ge 0) {
        $insertIndex = $categoryIndex + 1
        if ($insertIndex -lt $lines.Count -and $lines[$insertIndex] -eq "") {
            $insertIndex++
        }
        $lines.Insert($insertIndex, "- $Subject")
    }
    else {
        $insertIndex = $sectionEnd
        while (
            $insertIndex -gt ($unreleasedIndex + 1) -and
            $lines[$insertIndex - 1] -eq ""
        ) {
            $insertIndex--
        }
        $block = [string[]]@("", "### $category", "", "- $Subject", "")
        $lines.InsertRange($insertIndex, $block)
    }

    [System.IO.File]::WriteAllText(
        $changelogPath,
        (
            ($lines -join [System.Environment]::NewLine).TrimEnd() +
            [System.Environment]::NewLine
        ),
        [System.Text.UTF8Encoding]::new($false)
    )
}

function Publish-ChangedSource {
    try {
        $branch = (Invoke-Git -GitArguments @("branch", "--show-current") | Select-Object -First 1).Trim()
        if ($branch -ne "main") {
            Write-Host "Auto-publish skipped: switch to the main branch first."
            return
        }

        $remote = (Invoke-Git -GitArguments @("remote", "get-url", "origin") | Select-Object -First 1).Trim()
        if ((Normalize-Remote $remote) -ne (Normalize-Remote $expectedRemote)) {
            Write-Host "Auto-publish skipped: origin is not this application's GitHub repository."
            return
        }

        $stagedPaths = @(
            Invoke-Git -GitArguments @("diff", "--cached", "--name-only")
        )
        $unrelatedStagedPaths = @(
            $stagedPaths | Where-Object {
                $_ -and -not (Test-SourcePath (Join-Path $repository $_))
            }
        )
        if ($unrelatedStagedPaths.Count -gt 0) {
            Write-Warning (
                "Auto-publish skipped because unrelated files are already staged: " +
                ($unrelatedStagedPaths -join ", ")
            )
            return
        }

        $sourcePaths = @(Get-ChangedSourcePaths)
        if ($sourcePaths.Count -eq 0) {
            Write-Host "No tracked or new Python/README changes to publish."
            return
        }

        Write-Host "Detected source changes:"
        foreach ($sourcePath in $sourcePaths) {
            Write-Host "  $sourcePath"
        }
        $subject = Read-ConventionalCommitSubject
        if ($null -eq $subject) {
            Write-Host "Commit cancelled; source files were left unchanged."
            return
        }

        $authorName = (
            Invoke-Git -GitArguments @("config", "user.name") |
                Select-Object -First 1
        )
        $authorEmail = (
            Invoke-Git -GitArguments @("config", "user.email") |
                Select-Object -First 1
        )
        if (
            [string]::IsNullOrWhiteSpace($authorName) -or
            [string]::IsNullOrWhiteSpace($authorEmail)
        ) {
            Write-Warning (
                "Configure your Git author first with git config user.name and " +
                "git config user.email. No commit was created."
            )
            return
        }

        $null = Invoke-Git -GitArguments (@("add", "--all", "--") + $sourcePaths)
        Add-ChangelogEntry -Subject $subject
        $null = Invoke-Git -GitArguments @("add", "--", "CHANGELOG.md")

        $stagedPaths = @(
            Invoke-Git -GitArguments @("diff", "--cached", "--name-only")
        )
        if ($stagedPaths.Count -eq 0) {
            Write-Host "No source changes remain to commit."
            return
        }
        $unexpectedStagedPaths = @(
            $stagedPaths | Where-Object {
                $_ -and
                $_ -ne "CHANGELOG.md" -and
                -not (Test-SourcePath (Join-Path $repository $_))
            }
        )
        if ($unexpectedStagedPaths.Count -gt 0) {
            Write-Warning (
                "Commit cancelled because unrelated files became staged: " +
                ($unexpectedStagedPaths -join ", ")
            )
            return
        }

        $null = Invoke-Git -GitArguments @(
            "commit",
            "-m",
            $subject,
            "-m",
            "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
        )
        Write-Host "Source changes recorded in CHANGELOG.md and committed locally."

        $answer = Read-Host "Push this commit to your GitHub repository now? [y/N]"
        if ($answer.Trim().ToLowerInvariant() -notin @("y", "yes")) {
            Write-Host "Commit kept locally; push skipped."
            return
        }

        $null = Invoke-Git -GitArguments @("push", "origin", "main")
        Write-Host "Saved source changes pushed to GitHub."
    }
    catch {
        Write-Warning (
            "Auto-publish stopped without overwriting remote history: " +
            $_.Exception.Message
        )
    }
}

$watchers = [System.Collections.Generic.List[System.IO.FileSystemWatcher]]::new()
$sourceIdentifiers = [System.Collections.Generic.List[string]]::new()

try {
    Write-Host "Auto-publish watcher starting."

    $pythonWatcher = [System.IO.FileSystemWatcher]::new($repository, "*.py")
    $pythonWatcher.IncludeSubdirectories = $true
    $pythonWatcher.NotifyFilter = (
        [System.IO.NotifyFilters]::LastWrite -bor
        [System.IO.NotifyFilters]::FileName -bor
        [System.IO.NotifyFilters]::DirectoryName
    )

    $readmeWatcher = [System.IO.FileSystemWatcher]::new(
        $repository,
        "README.md"
    )
    $readmeWatcher.IncludeSubdirectories = $false
    $readmeWatcher.NotifyFilter = (
        [System.IO.NotifyFilters]::LastWrite -bor
        [System.IO.NotifyFilters]::FileName
    )

    $watchers.Add($pythonWatcher)
    $watchers.Add($readmeWatcher)

    foreach ($watcher in $watchers) {
        foreach ($eventName in @("Changed", "Created", "Deleted", "Renamed")) {
            $identifier = "ClockAutoPublish-$([guid]::NewGuid().ToString('N'))"
            $sourceIdentifiers.Add($identifier)
            Register-ObjectEvent `
                -InputObject $watcher `
                -EventName $eventName `
                -SourceIdentifier $identifier | Out-Null
        }
    }

    foreach ($watcher in $watchers) {
        $watcher.EnableRaisingEvents = $true
    }

    Write-Host "Auto-publish watcher ready."
    Write-Host "Watching Python source and root README.md; upstream library is excluded."
    Write-Host "Changes are committed after $quietPeriodSeconds seconds of inactivity."

    $pendingChange = $false
    $lastChange = [DateTime]::UtcNow
    while ($true) {
        $eventRecord = Wait-Event -Timeout 1
        if ($null -ne $eventRecord) {
            $changedPath = $eventRecord.SourceEventArgs.FullPath
            if ($changedPath -and (Test-SourcePath $changedPath)) {
                $pendingChange = $true
                $lastChange = [DateTime]::UtcNow
            }
            Remove-Event -EventIdentifier $eventRecord.EventIdentifier
        }

        if (
            $pendingChange -and
            (([DateTime]::UtcNow - $lastChange).TotalSeconds -ge $quietPeriodSeconds)
        ) {
            $pendingChange = $false
            Publish-ChangedSource
        }
    }
}
catch {
    Write-Error "Auto-publish watcher stopped: $_"
    exit 1
}
finally {
    foreach ($identifier in $sourceIdentifiers) {
        Unregister-Event -SourceIdentifier $identifier -ErrorAction SilentlyContinue
    }
    foreach ($watcher in $watchers) {
        $watcher.Dispose()
    }
}
