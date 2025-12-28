import os
import ast
import csv

project_root = "D:/performance_eval"  # مسیر پروژه‌ات

def find_imports_in_file(file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=file_path)
    except Exception:
        return set()
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                imports.add(n.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module.split(".")[0])
    return imports

all_py_files = []
all_imports = set()

for root, _, files in os.walk(project_root):
    for f in files:
        if f.endswith(".py"):
            full = os.path.join(root, f)
            all_py_files.append(full)
            all_imports |= find_imports_in_file(full)

unused = []
for f in all_py_files:
    name = os.path.splitext(os.path.basename(f))[0]
    if (
        name not in all_imports
        and name not in ["__init__", "manage", "settings", "urls", "wsgi", "asgi"]
        and "migrations" not in f
        and "tests" not in f
    ):
        unused.append(f)

# ذخیره در CSV
with open("unused_files.csv", "w", newline="", encoding="utf-8") as csvfile:
    writer = csv.writer(csvfile)
    writer.writerow(["Unused Python Files"])
    for f in unused:
        writer.writerow([f])

print("✅ لیست فایل‌های مشکوک به بلااستفاده در unused_files.csv ذخیره شد")
