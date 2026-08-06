from fastapi import FastAPI

from backend.app.bridge.protocol import COMMANDS_FILE, STATUS_FILE
from backend.app.bridge.reader import read_json
from backend.app.bridge.schemas import Command, Status
from backend.app.bridge.writer import write_json


app = FastAPI(
    title="Atlas",
    version="0.1.0",
)


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "Welcome to Atlas"}


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "running",
        "version": "0.1.0",
        "strategy": "nyao",
        "environment": "demo",
    }


@app.get("/api/v1/nyao/command")
def get_nyao_command() -> dict:
    command_data = read_json(COMMANDS_FILE)

    if not command_data:
        command = Command()
        write_json(command, COMMANDS_FILE)
        return command.model_dump(mode="json")

    return Command.model_validate(command_data).model_dump(mode="json")


@app.put("/api/v1/nyao/command")
def update_nyao_command(command: Command) -> dict:
    # Increment the command version so Nyao can detect a new command.
    existing = read_json(COMMANDS_FILE)
    previous_version = int(existing.get("command_version", 0))

    updated_command = command.model_copy(
        update={"command_version": previous_version + 1}
    )

    write_json(updated_command, COMMANDS_FILE)
    return updated_command.model_dump(mode="json")


@app.get("/api/v1/nyao/status")
def get_nyao_status() -> dict:
    status_data = read_json(STATUS_FILE)

    if not status_data:
        return Status(connected=False).model_dump(mode="json")

    return Status.model_validate(status_data).model_dump(mode="json")


@app.post("/api/v1/nyao/status")
def receive_nyao_status(status: Status) -> dict[str, object]:
    write_json(status, STATUS_FILE)

    return {
        "accepted": True,
        "timestamp": status.timestamp,
    }