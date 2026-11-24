@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ============================================================
echo   Bambu Smart Tuner - 一键上传到 GitHub
echo ============================================================
echo.
echo 前提：你已经在 GitHub 上建好一个空仓库（不要勾 README / .gitignore / license）
echo 形如：https://github.com/你的用户名/bambu-smart-tuner.git
echo.
set /p URL=把仓库地址粘到这里后按回车：

if "%URL%"=="" (
    echo.
    echo 没填地址，已取消。
    pause
    exit /b 1
)

echo.
echo [1/3] 清理旧的 origin（如果有）
git remote remove origin >nul 2>&1

echo [2/3] 关联远程仓库
git remote add origin "%URL%"
if errorlevel 1 (
    echo.
    echo 关联失败，检查地址格式。已退出。
    pause
    exit /b 1
)

echo [3/3] 推送 main 分支
echo.
echo 如果弹出 GitHub 登录窗口，点 "Sign in with your browser"，
echo 浏览器里点 Authorize，就会自动完成，不用输密码。
echo.
git push -u origin main

if errorlevel 1 (
    echo.
    echo ------------------------------------------------------------
    echo 推送失败。常见原因：
    echo   1) 建仓库时勾了 README / .gitignore / license，远程已有提交
    echo      解决：先跑  git pull --rebase origin main  再重跑本脚本
    echo   2) 仓库地址写错，或仓库不是你的
    echo   3) 网络连不上 github.com
    echo ------------------------------------------------------------
) else (
    echo.
    echo ============================================================
    echo  上传完成！
    echo  仓库页面：%URL:.git=%
    echo ============================================================
    echo.
    echo 下一步：去仓库页右侧 Releases 新建 v1.0，把
    echo   release\BambuSmartTuner-v1.0-win64.zip
    echo 作为附件传上去。
)

echo.
pause
