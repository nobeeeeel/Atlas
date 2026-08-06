from backend.app.bridge.schemas import Command, Status, Runtime
from backend.app.bridge.protocol import (
    COMMANDS_FILE,
    STATUS_FILE,
    RUNTIME_FILE,
)
from backend.app.bridge.writer import write_json


def main():
    print("Initializing Atlas runtime...")

    write_json(Command(), COMMANDS_FILE)
    write_json(Status(), STATUS_FILE)
    write_json(Runtime(), RUNTIME_FILE)

    print("Runtime initialized successfully!")


if __name__ == "__main__":
    main()