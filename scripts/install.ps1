<#
.SYNOPSIS
  小喵 QQ 机器人 —— 全新电脑上的自动安装脚本。

.DESCRIPTION
  做四件事：
    1. 下载 kirara-ai 的 Windows quickstart 包（约 210MB）并解压到 <仓库>\kirara
    2. 下载 NapCat.Shell.Windows.Node.zip（约 118MB）并解压到 <仓库>\napcat
    3. 用 kirara 自带的 Python 装三个插件（onebot 适配器 / scheduler / api_collection）
    4. 调用 bot\provision.py --offline 把配置灌进去

  下载失败时的兜底：手动把两个 zip 放进 <仓库>\downloads\ 再重跑本脚本，
  脚本会优先用本地已有的包，不会重复下载。

.NOTES
  用法（在仓库根目录）：
      powershell -ExecutionPolicy Bypass -File scripts\install.ps1
  或直接双击 scripts\安装.cmd
#>

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$Root = Split-Path -Parent $PSScriptRoot
$DL   = Join-Path $Root "downloads"
New-Item -ItemType Directory -Force -Path $DL | Out-Null

function Say($m)  { Write-Host $m -ForegroundColor Cyan }
function Warn($m) { Write-Host $m -ForegroundColor Yellow }
function Die($m)  { Write-Host $m -ForegroundColor Red; exit 1 }

# ---------- 0. .env ----------
$EnvFile = Join-Path $Root ".env"
if (-not (Test-Path $EnvFile)) {
    Copy-Item (Join-Path $Root ".env.example") $EnvFile
    Warn "[!] 已生成 .env —— 请用记事本打开填入 DEEPSEEK_API_KEY，然后重跑本脚本"
    Warn "    文件位置：$EnvFile"
    exit 2
}
$KeyLine = (Get-Content $EnvFile | Where-Object { $_ -match '^\s*DEEPSEEK_API_KEY=' }) -join ''
if (-not $KeyLine -or $KeyLine -match '在这里填' -or $KeyLine -match '=\s*$') {
    Die "[!] .env 里的 DEEPSEEK_API_KEY 还没填。申请地址：https://platform.deepseek.com/"
}
Say "[ok] .env 已就绪"

# ---------- 1. 找最新发布包 ----------
function Get-Asset($Repo, $Pattern) {
    try {
        $r = Invoke-RestMethod "https://api.github.com/repos/$Repo/releases/latest" `
             -Headers @{ "User-Agent" = "xiaomiao-qq-bot-installer" } -TimeoutSec 40
    } catch {
        Warn "    访问 GitHub API 失败（$Repo）：$($_.Exception.Message)"
        return $null
    }
    $a = $r.assets | Where-Object { $_.name -match $Pattern } | Select-Object -First 1
    if (-not $a) { Warn "    $Repo 最新版里没找到匹配 $Pattern 的文件"; return $null }
    Say "    找到 $($a.name)  $([math]::Round($a.size/1MB,1)) MB  (tag $($r.tag_name))"
    return $a
}

function Get-Zip($Repo, $Pattern, $LocalName) {
    $Local = Join-Path $DL $LocalName
    if (Test-Path $Local) { Say "    已存在本地包，跳过下载：$LocalName"; return $Local }
    $a = Get-Asset $Repo $Pattern
    if (-not $a) { return $null }
    Say "    下载中（可能需要几分钟）..."
    Invoke-WebRequest $a.browser_download_url -OutFile $Local -UseBasicParsing
    return $Local
}

function Expand-ZipSmart($Zip, $Dest) {
    # 解压到临时目录，再把内容搬到 Dest（兼容"包里套一层目录"和"包就是根"两种情况）
    if (Test-Path $Dest) { Warn "    $Dest 已存在，跳过解压"; return }
    $Tmp = "$Dest.extract"
    if (Test-Path $Tmp) { Remove-Item $Tmp -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $Tmp | Out-Null
    Say "    解压中：$(Split-Path $Zip -Leaf)"
    $tar = Get-Command tar -ErrorAction SilentlyContinue
    if ($tar) { & tar -xf $Zip -C $Tmp } else { Expand-Archive -Path $Zip -DestinationPath $Tmp -Force }
    if ($LASTEXITCODE -ne 0 -and -not $tar) { Die "解压失败：$Zip" }
    $items = Get-ChildItem $Tmp
    if ($items.Count -eq 1 -and $items[0].PSIsContainer) { Move-Item $items[0].FullName $Dest }
    else { Move-Item $Tmp $Dest; return }
    Remove-Item $Tmp -Recurse -Force -ErrorAction SilentlyContinue
}

Say "[1/4] kirara-ai 主体"
$KiraraZip = Get-Zip "lss233/kirara-ai" "Windows-quickstart.*\.zip" "kirara-quickstart.zip"
if (-not $KiraraZip) {
    Warn "    自动下载失败。请手动到 https://github.com/lss233/kirara-ai/releases 下载"
    Warn "    Windows-quickstart-*.zip，改名为 kirara-quickstart.zip 放进 $DL 后重跑。"
} else { Expand-ZipSmart $KiraraZip (Join-Path $Root "kirara") }

Say "[2/4] NapCat 协议端"
$NapZip = Get-Zip "NapNeko/NapCatQQ" "NapCat\.Shell\.Windows\.Node\.zip" "NapCat.Shell.Windows.Node.zip"
if (-not $NapZip) {
    Warn "    自动下载失败。请手动到 https://github.com/NapNeko/NapCatQQ/releases 下载"
    Warn "    NapCat.Shell.Windows.Node.zip 放进 $DL 后重跑。"
} else { Expand-ZipSmart $NapZip (Join-Path $Root "napcat") }

# ---------- 3. 找嵌入式 Python，装插件 ----------
Say "[3/4] 安装 kirara 插件"
$Py = Get-ChildItem (Join-Path $Root "kirara") -Directory -Filter "WPy64-*" -ErrorAction SilentlyContinue |
      Select-Object -First 1
if ($Py) {
    $PyExe = Join-Path $Py.FullName "python\python.exe"
    if (Test-Path $PyExe) {
        $pkgs = @("chatgpt-mirai-qq-bot-onebot-adapter",
                  "chatgpt-mirai-qq-bot-scheduler",
                  "chatgpt-mirai-qq-bot-api-collection")
        & $PyExe -m pip install --disable-pip-version-check @pkgs
        if ($LASTEXITCODE -ne 0) {
            Warn "    pip 安装失败。兜底方案：先启动 kirara，在 WebUI 的插件市场里搜索安装这三个插件："
            Warn "    onebot-adapter / scheduler / api-collection，然后重跑 provision。"
        } else { Say "    插件安装完成" }
    } else { Warn "    找不到 $PyExe" }
} else { Warn "    没找到 kirara 的嵌入式 Python，插件请通过 WebUI 插件市场安装" }

# ---------- 4. 灌配置 ----------
Say "[4/4] 写入配置"
$AnyPy = if ($PyExe -and (Test-Path $PyExe)) { $PyExe } else { "python" }
& $AnyPy (Join-Path $Root "bot\provision.py") --offline

Write-Host ""
Say "================ 安装结束 ================"
Say "下一步："
Say "  1) 双击 scripts\一键启动.cmd"
Say "  2) 首次启动 kirara 会让你在 http://127.0.0.1:8080 设置管理密码，"
Say "     请设成 .env 里 KIRARA_WEBUI_PASSWORD 的值"
Say "  3) 再跑一次：scripts\配置.cmd  （把工作流写进去）"
Say "  4) NapCat 窗口里扫码登录你的 QQ 小号"
Say "  5) 在 QQ 里发一句『发个表情包』验收"
Say "=========================================="
