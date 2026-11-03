@echo off
setlocal EnableDelayedExpansion

cd /d "%~dp0"

if not exist venv/Scripts/activate (
    echo Virtual environment not found!
    echo Creating virtual environment...
    python -m venv venv
    echo Virtual environment created!
    echo(
    pause
    cls
)

:menu
cls

echo ---------------------------------------
echo -          Welcome Back               -
echo ---------------------------------------
echo -     App Management:                 -
echo -                                     -
echo -       1 -^> Run App                  -
echo -       2 -^> Install Packages         -
echo -       3 -^> UnInstall Packages       -
echo -       4 -^> Create Requirements File -
echo -       5 -^> Clear Python Cache       -
echo -       6 -^> ^Exit                     -
echo ---------------------------------------

echo(
echo(

echo Enter your choice:
set /p choice_input=

if "!choice_input!" EQU "1" (
    goto RunApp
)

if "!choice_input!" EQU "2" (
    goto InstallPackages
)

if "!choice_input!" EQU "3" (
    goto UnInstallPackages
)

if "!choice_input!" EQU "4" (
    goto CreatingRequirementsFile
)

if "!choice_input!" EQU "5" (
    set "CLEAR_CACHE_SENT_FROM_MENU=1"
    goto ClearPythonCache
)

if "!choice_input!" EQU "6" (
    goto ExitApp
)

cls
goto menu

REM  === Run Section ===

:RunApp

cls
echo(
echo [+] Running App...
echo(

set "CLEAR_CACHE_SENT_FROM_MENU=0"
set "CLEAR_CACHE_RETURN_TO_THIS_SUBMENU=RunAppContinue_1"
goto ClearPythonCache
:RunAppContinue_1
timeout /t 1 /nobreak >nul

if not exist main.py (
    echo Error: Launch file not found!
    echo     It should be named "main.py"
    pause
    goto menu
)

venv\Scripts\python.exe main.py
pause
goto menu

REM  === Install Section ===

:InstallPackages
cls

echo ------------------------------
echo -   0 -^> Return To Menu      -
echo ------------------------------
echo -   Install Packages Tab     -
echo ------------------------------
echo(

echo Enter libraries (space separated):
set /p libraries_input=

if "!libraries_input!" EQU "" (
    echo No input provided
    pause
    goto InstallPackages
)

if "!libraries_input!" EQU "0" (
    goto menu
)

cls

set "SUCCESS_LIST="
set "FAILED_LIST="
set "TABLE_DATA="

for %%L in (!libraries_input!) do (
    echo Installing %%L...

    venv\Scripts\python.exe -m pip install %%L >nul 2>&1

    if !errorlevel! EQU 0 (
        set "TABLE_DATA=!TABLE_DATA!%%L,INSTALLED;"
        set "SUCCESS_LIST=!SUCCESS_LIST! %%L"
    ) else (
        set "TABLE_DATA=!TABLE_DATA!%%L,FAILED;"
        set "FAILED_LIST=!FAILED_LIST!, %%L"
    )
)

if defined FAILED_LIST set "FAILED_LIST=!FAILED_LIST:~2!"

cls

set "TMP_FILE=%temp%\pip_%RANDOM%_result_%RANDOM%.txt"
echo !TABLE_DATA! > "!TMP_FILE!"

powershell -NoProfile -Command ^
"$input = Get-Content '!TMP_FILE!' -Raw; ^
$items = $input.Trim(';').Split(';'); ^
Write-Host '----------------------------------------' -ForegroundColor Cyan; ^
Write-Host ('{0,-25} {1}' -f 'Library','Status') -ForegroundColor Cyan; ^
Write-Host '----------------------------------------' -ForegroundColor Cyan; ^
foreach($i in $items){ ^
    if([string]::IsNullOrWhiteSpace($i)){ continue } ^
    $parts = $i.Split(','); ^
    $lib = $parts[0]; ^
    $status = $parts[1]; ^
    if($status -eq 'INSTALLED'){ ^
        Write-Host ('{0,-25} INSTALLED' -f $lib) -ForegroundColor Green ^
    } else { ^
        Write-Host ('{0,-25} NOT INSTALLED' -f $lib) -ForegroundColor Red ^
    } ^
} ^
Write-Host '----------------------------------------' -ForegroundColor Cyan"

del "%TMP_FILE%" >nul 2>&1

echo(

if defined FAILED_LIST (
    echo Packages !FAILED_LIST! could not install.
    if defined SUCCESS_LIST (
        echo Others installed successfully.
    )
) else (
    echo All packages installed successfully.
)

echo(

pause
goto menu

REM === UnInstall Section ===

:UnInstallPackages
cls

echo ------------------------------
echo -   0 -^> Return To Menu      -
echo ------------------------------
echo -   UnInstall Packages Tab   -
echo ------------------------------

echo(

echo Enter libraries (space separated):
set /p libraries_input=

if "!libraries_input!" EQU "" (
    echo No input provided
    pause
    goto UnInstallPackages
)

if "!libraries_input!" EQU "0" (
    goto menu
)

cls

set "SUCCESS_LIST="
set "FAILED_LIST="
set "TABLE_DATA="

for %%L in (!libraries_input!) do (
    echo Uninstalling %%L...

    venv\Scripts\python.exe -m pip uninstall %%L -y >nul 2>&1

    if !errorlevel! EQU 0 (
        set "TABLE_DATA=!TABLE_DATA!%%L,UNINSTALLED;"
        set "SUCCESS_LIST=!SUCCESS_LIST! %%L"
    ) else (
        set "TABLE_DATA=!TABLE_DATA!%%L,FAILED;"
        set "FAILED_LIST=!FAILED_LIST!, %%L"
    )
)

if defined FAILED_LIST set "FAILED_LIST=!FAILED_LIST:~2!"

cls

set "TMP_FILE=%temp%\pip_%RANDOM%_result_%RANDOM%.txt"
echo !TABLE_DATA! > "!TMP_FILE!"

powershell -NoProfile -Command ^
"$input = Get-Content '!TMP_FILE!' -Raw; ^
$items = $input.Trim(';').Split(';'); ^
Write-Host '----------------------------------------' -ForegroundColor Cyan; ^
Write-Host ('{0,-25} {1}' -f 'Library','Status') -ForegroundColor Cyan; ^
Write-Host '----------------------------------------' -ForegroundColor Cyan; ^
foreach($i in $items){ ^
    if([string]::IsNullOrWhiteSpace($i)){ continue } ^
    $parts = $i.Split(','); ^
    $lib = $parts[0]; ^
    $status = $parts[1]; ^
    if($status -eq 'UNINSTALLED'){ ^
        Write-Host ('{0,-25} UNINSTALLED' -f $lib) -ForegroundColor Green ^
    } else { ^
        Write-Host ('{0,-25} FAILED' -f $lib) -ForegroundColor Red ^
    } ^
} ^
Write-Host '----------------------------------------' -ForegroundColor Cyan"

del "%TMP_FILE%" >nul 2>&1

echo(

if defined FAILED_LIST (
    echo Packages !FAILED_LIST! could not uninstall.
    if defined SUCCESS_LIST (
        echo Others uninstalled successfully.
    )
) else (
    echo All packages uninstalled successfully.
)

echo(

pause
goto menu

REM === Clear Python Cache Section ===

:ClearPythonCache

if "!CLEAR_CACHE_SENT_FROM_MENU!" EQU "1" (
    cls
    echo(
    echo [+] Clearing Python cache...
    echo(
)

set "CLEAR_CACHE_TARGET=__pycache__"

for /d /r %%D in (*) do (
    if /i "%%~nxD" EQU "!CLEAR_CACHE_TARGET!" (
        rmdir /s /q "%%D"
    )
)

if "!CLEAR_CACHE_SENT_FROM_MENU!" EQU "1" (
    echo(
    echo [+] Cache cleared successfully.
    echo(
    pause
    goto menu
)

goto %CLEAR_CACHE_RETURN_TO_THIS_SUBMENU%

REM  === Exit Section ===

:ExitApp
cls

echo(
echo Goodbye ^<3
echo(

pause
exit

:CreatingRequirementsFile
cls
set "REQ_STAT=0"
set "REQ_TMP=%TEMP%\requirements_%RANDOM%_%RANDOM%.txt"
venv\Scripts\python.exe -m pip freeze > "!REQ_TMP!"

if errorlevel 1 (
    set "REQ_STAT=1"
    del "!REQ_TMP!" > NUL 2>&1
) else (
    move /y "!REQ_TMP!" "requirements.txt">nul 2>&1

    if errorlevel 1 (
        set "REQ_STAT=1"
        del "!REQ_TMP!" > NUL 2>&1
    )
)

if (!REQ_STAT! EQU 1) (
    echo [-] Failed to create requirements.txt
) else (
    echo [+] requirements.txt created successfully
)

echo(
pause
goto menu