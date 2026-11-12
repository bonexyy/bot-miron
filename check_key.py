import base64

key = "MDFhMTVkZjEtZDI1ZC03YzJkLWJhNzQtMzYyMTdkNDk1MTA0OjVjMWUwZjc0LWI0MzAtNGUxOC05ODM1LWRkMTJlZjNiMDM3ZQ=="

# 1. Проверка на пробелы и переносы
if " " in key or "\n" in key or "\t" in key:
    print("❌ Ключ содержит пробелы или переносы строк!")
else:
    print("✅ Пробелов нет")

# 2. Проверка Base64 и содержимого
try:
    decoded = base64.b64decode(key).decode("utf-8")
    print(f"✅ Base64 валиден. Внутри: {decoded[:20]}...")
    if ":" not in decoded:
        print("⚠️ Внутри нет двоеточия — возможно, это не client_id:client_secret")
except Exception as e:
    print(f"❌ Ошибка декодирования Base64: {e}")