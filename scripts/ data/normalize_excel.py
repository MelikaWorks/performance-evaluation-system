"""
normalize_excel.py — v2 (keeps name columns)
Usage:
  python normalize_excel.py D:\performance_eval\employees.xlsx --sheet Sheet1 --out D:\performance_eval\employees_normalized.xlsx
"""
import argparse
import re
import sys
import pandas as pd

# Required columns for importer (unchanged)
REQUIRED = ["personnel_code","organization","unit","unit_code","team_code","role_level","job_role","email","hire_date"]

# Optional columns we now preserve if found
OPTIONAL = ["first_name","last_name","full_name"]

HEADER_ALIASES = {
    "personnel_code": ["personnel_code","personnel id","employee id","emp_id","کد پرسنلی","کد_پرسنلی","شماره پرسنلی","کدپرسنلی","پرسنل کد"],
    "organization":   ["organization","org","سازمان","شرکت","نام سازمان"],
    "unit":           ["unit","unit_name","department","بخش","واحد","نام واحد"],
    "unit_code":      ["unit_code","unit code","dept_code","کد واحد","کد_واحد","کدبخش"],
    "team_code":      ["team_code","team code","گروه","کد تیم","کد_تیم","تیم کد","زیرگروه","زیر گروه"],
    "role_level":     ["role_level","role level","سطح نقش","سطح","نقش","سمت کدی","کد نقش","کد_نقش"],
    "job_role":       ["job_role","job role","position","title","سمت","شرح شغل","عنوان شغلی"],
    "email":          ["email","e-mail","ایمیل","پست الکترونیک"],
    "hire_date":      ["hire_date","hire date","start_date","employment_date","تاریخ استخدام","شروع به کار","تاریخ شروع"],

    # Optional name fields
    "first_name":     ["first_name","firstname","first name","نام","اسم"],
    "last_name":      ["last_name","lastname","last name","نام خانوادگی","فامیل","شهرت"],
    "full_name":      ["full_name","fullname","full name","نام و نام خانوادگی","نام‌ونام‌خانوادگی","نام و فامیل"],
}

ROLE_NAME_TO_CODE = {
    "مدیر": "01", "رییس": "02", "رئیس": "02", "سرپرست": "03", "کارمند": "04",
    "manager": "01", "head": "02", "chief": "02", "supervisor": "03", "staff": "04", "employee": "04",
}

def _norm(s): return re.sub(r"\s+", " ", str(s).strip()).lower()

def guess_columns(cols):
    col_map = {}
    remaining = set(cols)
    # cover REQUIRED + OPTIONAL
    for target in REQUIRED + OPTIONAL:
        aliases = HEADER_ALIASES.get(target, [])
        found = None
        for cand in aliases:
            for c in list(remaining):
                if _norm(c) == _norm(cand):
                    found = c; break
            if found: break
        if not found:
            for c in list(remaining):
                if any(_norm(a) in _norm(c) for a in aliases):
                    found = c; break
        if found:
            col_map[target] = found
            remaining.discard(found)
    return col_map

def zpad2(x):
    if pd.isna(x): return x
    s = str(x).strip().replace(".0","")
    return s.zfill(2) if s.isdigit() else s

def normalize_role_level(x):
    if pd.isna(x): return x
    s = str(x).strip()
    d = re.sub(r"[^0-9]", "", s)
    if d in {"1","01"}: return "01"
    if d in {"2","02"}: return "02"
    if d in {"3","03"}: return "03"
    if d in {"4","04"}: return "04"
    s_norm = _norm(s)
    for name, code in ROLE_NAME_TO_CODE.items():
        if _norm(name) == s_norm or _norm(name) in s_norm:
            return code
    return zpad2(s)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("excel")
    ap.add_argument("--sheet", default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    try:
        df = pd.read_excel(args.excel, sheet_name=args.sheet, dtype=str)
    except Exception as e:
        print(f"[ERROR] Could not read Excel: {e}"); sys.exit(2)

    col_map = guess_columns(list(df.columns))
    print("=== Header Mapping (detected) ===")
    for k in REQUIRED + OPTIONAL:
        print(f"{k:>15}  <-  {col_map.get(k, 'NOT FOUND')}")

    out_cols = REQUIRED + [c for c in OPTIONAL if c in col_map]  # keep only found optionals
    out = pd.DataFrame(columns=out_cols)

    # fill required
    for k in REQUIRED:
        src = col_map.get(k)
        out[k] = df[src] if src else None

    # fill optional if found
    for k in OPTIONAL:
        src = col_map.get(k)
        if src: out[k] = df[src]

    # normalize
    out["personnel_code"] = out["personnel_code"].astype(str).str.strip()
    out["unit_code"]      = out["unit_code"].astype(str).str.strip()
    out["role_level"]     = out["role_level"].map(normalize_role_level)
    out["team_code"]      = out["team_code"].map(zpad2)

    # quick hints (non-blocking)
    issues = []
    invalid_roles = out[~out["role_level"].isin(["01","02","03","04"])]
    if len(invalid_roles): issues.append(f"[ROLE] invalid role_level rows: {list(invalid_roles.index+2)[:20]}{' ...' if len(invalid_roles)>20 else ''}")
    invalid_mgr = out[(out["role_level"]=="01") & (out["team_code"]!="00")]
    if len(invalid_mgr): issues.append(f"[TEAM] managers need team_code=00 rows: {list(invalid_mgr.index+2)[:20]}{' ...' if len(invalid_mgr)>20 else ''}")
    invalid_nonmgr = out[out["role_level"].isin(["02","03","04"]) & (out["team_code"]=="00")]
    if len(invalid_nonmgr): issues.append(f"[TEAM] non-managers cannot have team_code=00 rows: {list(invalid_nonmgr.index+2)[:20]}{' ...' if len(invalid_nonmgr)>20 else ''}")

    out_path = args.out or re.sub(r"\.xlsx?$", "", args.excel) + "_normalized.xlsx"
    try:
        out.to_excel(out_path, index=False)
    except Exception as e:
        print(f"[ERROR] Could not write output: {e}"); sys.exit(3)

    print(f"\n[OK] Wrote normalized file: {out_path}")
    if issues:
        print("=== Issues (top) ==="); [print("-", i) for i in issues]
    print("Tip: run excel_validator.py for strict checks.")
if __name__ == "__main__":
    main()
