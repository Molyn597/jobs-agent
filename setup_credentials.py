import getpass
import winreg


def setup():
    print("=" * 60)
    print("🔒 Bezpečné uložení přihlašovacích údajů k Jobs.cz do Windows")
    print("=" * 60)

    email = input("Zadej svůj e-mail k Jobs.cz (např. user@example.com): ").strip()

    password = getpass.getpass("Zadej své heslo k Jobs.cz (při psaní zůstane skryté): ")

    if not password:
        print("❌ Heslo nebylo zadáno.")
        return

    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, r"Environment", 0, winreg.KEY_SET_VALUE
        )
        winreg.SetValueEx(key, "JOBS_CZ_EMAIL", 0, winreg.REG_SZ, email)
        winreg.SetValueEx(key, "JOBS_CZ_PASSWORD", 0, winreg.REG_SZ, password)
        winreg.CloseKey(key)
        print("\n✅ HOTOVO! Údaje byly úspěšně a bezpečně uloženy do systému Windows.")
    except Exception as e:
        print(f"\n❌ Chyba při ukládání: {e}")


if __name__ == "__main__":
    setup()
