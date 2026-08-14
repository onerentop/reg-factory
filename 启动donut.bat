@echo off
REM ============================================================
REM 启动 donut-browser（带 e2e 后门，绕过 browser_automation 付费墙）
REM
REM 用法:
REM   直接双击本脚本启动 donut（正式版 release 构建）
REM   - 必须先 cargo build --release --features e2e 编译出带后门的二进制
REM   - 后门 env 是进程级的，必须从本脚本启动才生效（桌面图标不会带）
REM
REM 数据目录:
REM   dev 构建   -> %LOCALAPPDATA%\DonutBrowserDev
REM   release    -> %LOCALAPPDATA%\DonutBrowser
REM   token 自动解密，common/donut_token.py 两个路径都兼容
REM ============================================================

REM 优先用 release 构建（正式版），没有则退回 debug
set "DONUT_EXE=F:\donutbrowser\src-tauri\target\release\donutbrowser.exe"
if not exist "%DONUT_EXE%" (
    set "DONUT_EXE=F:\donutbrowser\src-tauri\target\debug\donutbrowser.exe"
)

REM 后门 env（e2e_automation_enabled 需 TAURI_AUTOMATION=true，
REM can_use_browser_automation 另需 WAYFERN_TEST_TOKEN 非空）
set "TAURI_AUTOMATION=true"
set "WAYFERN_TEST_TOKEN=reg-factory"

echo [donut] 启动: %DONUT_EXE%
echo [donut] 后门: TAURI_AUTOMATION=true WAYFERN_TEST_TOKEN=reg-factory
start "" "%DONUT_EXE%"
