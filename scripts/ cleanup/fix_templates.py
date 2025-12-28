import os

root = "D:\\performance_eval"  # مسیر پروژه‌ت
count = 0
for path, _, files in os.walk(root):
    for name in files:
        if name.endswith((".html", ".js", ".css")):
            file_path = os.path.join(path, name)
            with open(file_path, "rb") as f:
                data = f.read()
            # حذف BOM از اول
            if data.startswith(b'\xef\xbb\xbf'):
                data = data[3:]
            # حذف U+FEFF از وسط متن
            clean_data = data.replace(b'\xef\xbb\xbf', b'')
            if clean_data != data:
                with open(file_path, "wb") as f:
                    f.write(clean_data)
                print("🧹 cleaned:", file_path)
                count += 1
print(f"✅ Done cleaning {count} file(s).")
