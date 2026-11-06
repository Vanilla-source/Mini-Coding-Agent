# 冻结版本（考前 2~3 天执行）
#
#   powershell -ExecutionPolicy Bypass -File scripts\freeze.ps1 -Tag v1.0-exam
#
# 做三件事：
#   1. 提交当前改动并打 tag（版本可追溯）
#   2. 打一个干净的 zip 快照（不含 .venv / runs / .env）
#   3. 计算 sha256，写 FREEZE.md 作为"考前冻结"的证据

param(
    [string]$Tag = "v1.0-exam",
    [string]$Message = "frozen for classroom exam"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "==> 1/5 检查 git 仓库" -ForegroundColor Cyan
if (-not (Test-Path ".git")) {
    Write-Host "    当前目录还不是 git 仓库，执行 git init" -ForegroundColor Yellow
    git init | Out-Null
    git add -A
    git -c user.name="agent" -c user.email="agent@local" commit -m "init: project skeleton" | Out-Null
}

Write-Host "==> 2/5 提交当前改动" -ForegroundColor Cyan
git add -A
$pending = git status --porcelain
if ($pending) {
    git -c user.name="agent" -c user.email="agent@local" commit -m $Message | Out-Null
    Write-Host "    已提交 $((($pending -split "`n").Count)) 项改动"
} else {
    Write-Host "    工作区干净，无需提交"
}

$commit = (git rev-parse --short HEAD).Trim()
Write-Host "    当前 commit: $commit"

Write-Host "==> 3/5 打标签 $Tag" -ForegroundColor Cyan
$existing = git tag --list $Tag
if ($existing) {
    git tag -d $Tag | Out-Null
}
git tag -a $Tag -m $Message
Write-Host "    已创建 tag: $Tag"

Write-Host "==> 4/5 生成干净快照" -ForegroundColor Cyan
$stage = Join-Path $env:TEMP ("freeze-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
New-Item -ItemType Directory -Path $stage | Out-Null

$include = @("agent", "scripts", "eval", "requirements.txt", "README.md", ".gitignore", ".env.example")
foreach ($item in $include) {
    if (Test-Path $item) {
        Copy-Item -Path $item -Destination $stage -Recurse -Force
    }
}
# 清掉快照里的缓存与私有数据
Get-ChildItem -Path $stage -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path $stage -Recurse -File -Filter ".env" -ErrorAction SilentlyContinue |
    Remove-Item -Force -ErrorAction SilentlyContinue

$zip = Join-Path $Root ("coding-agent-" + $Tag + ".zip")
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $zip -Force
Remove-Item $stage -Recurse -Force -ErrorAction SilentlyContinue

$hash = (Get-FileHash -Path $zip -Algorithm SHA256).Hash
Write-Host "    快照: $zip"
Write-Host "    sha256: $hash"

Write-Host "==> 5/5 写 FREEZE.md" -ForegroundColor Cyan
$now = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$py = (python --version 2>&1)
@"
# 版本冻结记录

- 冻结时间：$now
- Git tag：$Tag
- Git commit：$commit
- 快照文件：$(Split-Path -Leaf $zip)
- SHA256：$hash
- Python：$py

## 约定

自上述时间起，Agent **核心源码不再修改**。此后允许变更的仅为：
`.env`（密钥）、命令行参数、日志输出格式等非核心逻辑。

课堂考核期间不得修改 Agent 核心源码。
"@ | Set-Content -Path (Join-Path $Root "FREEZE.md") -Encoding UTF8

git add FREEZE.md
git -c user.name="agent" -c user.email="agent@local" commit -m "docs: freeze record $Tag" | Out-Null

Write-Host ""
Write-Host "完成。冻结版本已就绪：$Tag @ $commit" -ForegroundColor Green
Write-Host "提交材料里请附上这个 zip 与 FREEZE.md。" -ForegroundColor Green
