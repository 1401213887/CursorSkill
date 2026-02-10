@echo off
REM S1SharedDocSkill 测试运行脚本
REM 用法: run_tests.bat [options]
REM 选项:
REM   --skip-integration  跳过集成测试（不访问真实共享盘）
REM   --verbose           详细输出

setlocal EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
set "SRC_DIR=%SCRIPT_DIR%..\src"
set "SKIP_INTEGRATION="
set "VERBOSE=-v"

REM 解析参数
:parse_args
if "%~1"=="" goto :run_tests
if /i "%~1"=="--skip-integration" (
    set "SKIP_INTEGRATION=1"
    shift
    goto :parse_args
)
if /i "%~1"=="--verbose" (
    set "VERBOSE=-v"
    shift
    goto :parse_args
)
shift
goto :parse_args

:run_tests
echo ============================================
echo S1SharedDocSkill 单元测试
echo ============================================
echo.

REM 设置环境变量
if defined SKIP_INTEGRATION (
    echo [INFO] 跳过集成测试（不访问真实共享盘）
    set "SKIP_INTEGRATION_TESTS=1"
) else (
    echo [INFO] 包含集成测试（将尝试访问 W:\S1UnrealSharedDoc）
    set "SKIP_INTEGRATION_TESTS="
)
echo.

REM 切换到测试目录
pushd "%SCRIPT_DIR%"

REM 运行所有测试
echo [1/3] 运行路径验证测试...
python -m pytest test_path_guard.py %VERBOSE% --tb=short
if errorlevel 1 (
    echo [WARN] 路径验证测试有失败项
)
echo.

echo [2/3] 运行文档存储测试...
python -m pytest test_doc_store.py %VERBOSE% --tb=short
if errorlevel 1 (
    echo [WARN] 文档存储测试有失败项
)
echo.

echo [3/3] 运行代码 Review 测试...
python -m pytest test_review.py %VERBOSE% --tb=short
if errorlevel 1 (
    echo [WARN] 代码 Review 测试有失败项
)
echo.

popd

echo ============================================
echo 测试完成
echo ============================================

endlocal
