"""
excel_validator.py — v2 (accepts optional name fields)
Usage:
  python excel_validator.py D:\performance_eval\employees_normalized.xlsx Sheet1
"""
import sys
import pandas as pd

REQUIRED_COLS = ["personnel_code","organization","unit","unit_code","team_code","role_level","job_role","email","hire_date"]
OPTIONAL_COLS = ["first_name","last_name","full_name"]

def validate_df(df):
    errors, warns = [], []

    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing: errors.append(f"[SCHEMA] Missing required columns: {missing}")

    missing_opt = [c for c in OPTIONAL_COLS if c not in df.columns]
    if missing_opt and len(missing_opt) < len(OPTIONAL_COLS):
        warns.append(f"[SCHEMA] Optional name columns not fully present: {missing_opt}")

    if errors: return errors + warns

    def zpad2(x):
        try:
            s = str(x).strip()
            if s.isdigit(): return s.zfill(2)
            return s
        except: return x

    df["role_level"] = df["role_level"].map(zpad2)
    df["team_code"]  = df["team_code"].map(zpad2)

    invalid_roles = df[~df["role_level"].isin(["01","02","03","04"])]
    if len(invalid_roles):
        errors.append(f"[RULE] Invalid role_level values at rows: {list(invalid_roles.index+2)}")

    invalid_team_for_manager = df[(df["role_level"]=="01") & (df["team_code"]!="00")]
    if len(invalid_team_for_manager):
        errors.append(f"[RULE] Managers must have team_code=00 at rows: {list(invalid_team_for_manager.index+2)}")

    invalid_team_for_nonmgr = df[df["role_level"].isin(["02","03","04"]) & (df["team_code"]=="00")]
    if len(invalid_team_for_nonmgr):
        errors.append(f"[RULE] Non-managers cannot have team_code=00 at rows: {list(invalid_team_for_nonmgr.index+2)}")

    mask_tmp = df["team_code"]=="99"
    if mask_tmp.any():
        warns.append(f"[WARN] Found temporary team_code=99 at rows: {list(df[mask_tmp].index+2)}")

    if df["personnel_code"].duplicated().any():
        dup_rows = list(df[df["personnel_code"].duplicated(keep=False)].index+2)
        errors.append(f"[RULE] Duplicate personnel_code at rows: {dup_rows}")

    for col in ["unit_code","role_level","team_code","personnel_code"]:
        null_rows = list(df[df[col].isna()].index+2)
        if null_rows:
            errors.append(f"[RULE] Null values in {col} at rows: {null_rows}")

    return errors + warns

def main():
    if len(sys.argv) < 3:
        print("Usage: python excel_validator.py <excel_path> <sheet_name>"); sys.exit(2)
    excel_path, sheet = sys.argv[1], sys.argv[2]
    try:
        df = pd.read_excel(excel_path, sheet_name=sheet, dtype=str)
    except Exception as e:
        print(f"[ERROR] Could not read Excel: {e}"); sys.exit(1)

    msgs = validate_df(df)
    if not msgs:
        print("[OK] Validation passed. No blocking issues found."); sys.exit(0)
    else:
        print("=== Validation Report ==="); [print("-", m) for m in msgs]
        blocking = any(m.startswith("[SCHEMA]") or m.startswith("[RULE]") for m in msgs)
        sys.exit(1 if blocking else 0)

if __name__ == "__main__":
    main()
