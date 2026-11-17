"""
Library Manager — manage all project dependencies from one place.
Usage: python lib_manager.py
"""
import sys
import subprocess
import importlib.util
from datetime import datetime

# ── Package Registry ──────────────────────────────────────────────────────────
# Format: "pip-name": ("import-name", "description")

PACKAGES = {
    "smartapi-python":    ("SmartApi",          "Angel One SmartAPI client"),
    "pyotp":              ("pyotp",              "TOTP generator for 2FA login"),
    "python-dotenv":      ("dotenv",             "Load credentials from .env file"),
    "logzero":            ("logzero",            "Logging for SmartAPI"),
    "websocket-client":   ("websocket",          "WebSocket feed for live prices"),
    "google-generativeai":("google.generativeai","Gemini AI (deprecated, kept for deps)"),
    "google-genai":       ("google.genai",       "Gemini AI analysis (Option 3) — new SDK"),
    "schedule":           ("schedule",           "Bot scheduling (run at set times)"),
    "requests":           ("requests",           "HTTP requests"),
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def is_installed(import_name):
    """Check if a package is importable."""
    try:
        if "." in import_name:
            parts = import_name.split(".")
            spec = importlib.util.find_spec(parts[0])
        else:
            spec = importlib.util.find_spec(import_name)
        return spec is not None
    except (ModuleNotFoundError, ValueError):
        return False


def get_version(pip_name):
    """Get installed version of a package."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "show", pip_name],
            capture_output=True, text=True
        )
        for line in result.stdout.splitlines():
            if line.startswith("Version:"):
                return line.split(":", 1)[1].strip()
    except Exception:
        pass
    return "unknown"


def pip_run(*args):
    """Run a pip command and stream output."""
    subprocess.run([sys.executable, "-m", "pip"] + list(args))


def print_header(title):
    print("\n" + "=" * 55)
    print(f"  {title}")
    print("=" * 55)


def print_status_table():
    """Print status of all packages."""
    print_header("PACKAGE STATUS")
    print(f"  {'Package':<25} {'Status':<12} {'Version':<12} Description")
    print("  " + "-" * 70)
    missing = []
    for pip_name, (import_name, desc) in PACKAGES.items():
        installed = is_installed(import_name)
        status    = "✅ Installed" if installed else "❌ Missing"
        version   = get_version(pip_name) if installed else "—"
        print(f"  {pip_name:<25} {status:<20} {version:<12} {desc}")
        if not installed:
            missing.append(pip_name)
    print()
    return missing


# ── Menu Actions ─────────────────────────────────────────────────────────────

def action_status():
    missing = print_status_table()
    if missing:
        print(f"  ⚠️  {len(missing)} package(s) missing: {', '.join(missing)}")
        print("  Run option [2] to install all missing packages.\n")
    else:
        print("  ✅ All packages installed.\n")


def action_install_missing():
    missing = [p for p, (i, _) in PACKAGES.items() if not is_installed(i)]
    if not missing:
        print("\n✅ Nothing to install — all packages already present.\n")
        return
    print(f"\n📦 Installing {len(missing)} missing package(s): {', '.join(missing)}\n")
    pip_run("install", *missing)
    print("\n✅ Done. Run status check [1] to verify.\n")


def action_install_all():
    pkgs = list(PACKAGES.keys())
    print(f"\n📦 Installing all {len(pkgs)} packages...\n")
    pip_run("install", *pkgs)
    print("\n✅ Done.\n")


def action_update_all():
    pkgs = list(PACKAGES.keys())
    print(f"\n🔄 Updating all {len(pkgs)} packages...\n")
    pip_run("install", "--upgrade", *pkgs)
    print("\n✅ All packages updated.\n")


def action_install_one():
    print("\nEnter package name to install (e.g. pandas): ", end="")
    pkg = input().strip()
    if not pkg:
        print("❌ No package name entered.\n")
        return
    print(f"\n📦 Installing {pkg}...\n")
    pip_run("install", pkg)
    # Add to requirements.txt if not already there
    with open("requirements.txt", "r") as f:
        existing = f.read().splitlines()
    if pkg not in existing:
        with open("requirements.txt", "a") as f:
            f.write(f"\n{pkg}")
        print(f"✅ Added '{pkg}' to requirements.txt\n")


def action_uninstall_one():
    print("\nEnter package name to uninstall: ", end="")
    pkg = input().strip()
    if not pkg:
        print("❌ No package name entered.\n")
        return
    confirm = input(f"⚠️  Uninstall '{pkg}'? (yes/no): ").strip().lower()
    if confirm == "yes":
        pip_run("uninstall", pkg, "-y")
        print(f"✅ '{pkg}' uninstalled.\n")
    else:
        print("Cancelled.\n")


def action_export_requirements():
    print("\n📄 Exporting installed packages to requirements.txt...\n")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "freeze"],
        capture_output=True, text=True
    )
    with open("requirements.txt", "w") as f:
        f.write(f"# Generated: {datetime.now().strftime('%d %b %Y %H:%M')}\n")
        f.write(result.stdout)
    print("✅ requirements.txt updated with all installed packages.\n")


def action_pip_upgrade():
    print("\n🔄 Upgrading pip...\n")
    pip_run("install", "--upgrade", "pip")
    print()


# ── Main Menu ─────────────────────────────────────────────────────────────────

MENU = [
    ("Check package status",              action_status),
    ("Install missing packages",          action_install_missing),
    ("Install all project packages",      action_install_all),
    ("Update all packages",               action_update_all),
    ("Install a new package",             action_install_one),
    ("Uninstall a package",               action_uninstall_one),
    ("Export requirements.txt",           action_export_requirements),
    ("Upgrade pip",                       action_pip_upgrade),
]


def main():
    while True:
        print_header("LIBRARY MANAGER — Angel One Trading Bot")
        for i, (label, _) in enumerate(MENU, 1):
            print(f"  [{i}] {label}")
        print("  [0] Exit")
        print()
        print("Choose an option: ", end="")

        choice = input().strip()

        if choice == "0":
            print("\nBye!\n")
            break
        elif choice.isdigit() and 1 <= int(choice) <= len(MENU):
            MENU[int(choice) - 1][1]()
        else:
            print("\n❌ Invalid choice. Try again.\n")


if __name__ == "__main__":
    main()
