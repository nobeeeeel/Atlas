from pathlib import Path

BRIDGE_DIR = Path(
    "/Users/nobel/Library/Application Support/"
    "net.metaquotes.wine.metatrader5/drive_c/"
    "Program Files/MetaTrader 5/MQL5/Files/Atlas"
)

BRIDGE_DIR.mkdir(parents=True, exist_ok=True)

COMMANDS_FILE = BRIDGE_DIR / "commands.json"
STATUS_FILE = BRIDGE_DIR / "status.json"
RUNTIME_FILE = BRIDGE_DIR / "runtime.json"