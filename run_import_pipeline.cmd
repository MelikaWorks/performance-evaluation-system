@echo off
REM === Configuration (edit these 3 lines to your paths) ===================
set PROJECT_DIR=D:\performance_eval
set VENV_ACT=%PROJECT_DIR%\.venv\Scripts\activate.bat
set EXCEL_PATH=%PROJECT_DIR%\employees_normalized.xlsx
set SHEET_NAME=Sheet1
set ORG_NAME="Seven Diamonds"
set ORG_HEAD_PCODE=220001

REM === Activate virtual environment ======================================
call "%VENV_ACT%"
if errorlevel 1 (
  echo [ERROR] Could not activate venv. Check VENV_ACT path.
  goto :end
)

cd /d "%PROJECT_DIR%"
echo [INFO] Current dir: %cd%

REM === 1) Dry-run import to validate data =================================
echo.
echo [STEP] Dry-run import to validate Excel structure and mapping...
python manage.py import_employees_structured "%EXCEL_PATH%" --sheet="%SHEET_NAME%" --set-unit-managers --dry-run --org=%ORG_NAME%
if errorlevel 1 (
  echo [ERROR] Dry-run failed. Fix Excel and re-run.
  goto :end
)

REM === 2) Report supervisor gaps BEFORE real import =======================
echo.
echo [STEP] Reporting supervisor gaps (pre-import baseline)...
python manage.py report_supervisor_gaps --org=%ORG_NAME%

REM === Prompt to continue =================================================
echo.
set /p CONT=Proceed with real import? (y/n): 
if /I not "%CONT%"=="y" (
  echo [INFO] Aborted by user.
  goto :end
)

REM === 3) Real import with org head fallback ==============================
echo.
echo [STEP] Real import with Unit.manager sync...
python manage.py import_employees_structured "%EXCEL_PATH%" --sheet="%SHEET_NAME%" --set-unit-managers --org-head=%ORG_HEAD_PCODE% --org=%ORG_NAME%
if errorlevel 1 (
  echo [ERROR] Real import failed.
  goto :end
)

REM === 4) Build links in phases ==========================================
echo.
echo [STEP] Build DIRECT + UNIT_MANAGER links...
python manage.py build_links_direct_unit --org=%ORG_NAME%

echo.
echo [STEP] Build links from ReportingLine (SECTION_HEAD + SUPERVISOR)...
python manage.py build_links_from_reporting --org=%ORG_NAME%

echo.
echo [STEP] Build ORG_HEAD links for managers...
python manage.py build_links_org_head_for_managers --org=%ORG_NAME% --head-pcode=%ORG_HEAD_PCODE%

REM === 5) Final supervisor sync and gap report ===========================
echo.
echo [STEP] Sync primary supervisor for display/reporting...
python manage.py sync_primary_supervisor --org=%ORG_NAME%

echo.
echo [STEP] Reporting supervisor gaps (post-import)...
python manage.py report_supervisor_gaps --org=%ORG_NAME%

echo.
echo [DONE] All steps completed.
:end
