from fastapi import FastAPI

from backend.app.bridge.protocol import COMMANDS_FILE, STATUS_FILE
from backend.app.bridge.reader import read_json
from backend.app.bridge.schemas import Command, Status
from backend.app.bridge.writer import write_json
from fastapi.responses import HTMLResponse

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
    
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard() -> str:
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">

    <title>Atlas Dashboard</title>

    <style>
        :root {
            color-scheme: dark;
            font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        }

        * {
            box-sizing: border-box;
        }

        body {
            margin: 0;
            background:
                radial-gradient(circle at top, #172033 0%, #0a0e17 45%, #06080d 100%);
            color: #f5f7fb;
            min-height: 100vh;
        }

        .container {
            width: min(1180px, calc(100% - 32px));
            margin: 0 auto;
            padding: 34px 0 60px;
        }

        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 20px;
            margin-bottom: 28px;
        }

        .brand h1 {
            margin: 0;
            font-size: 32px;
            letter-spacing: 0.08em;
        }

        .brand p {
            margin: 8px 0 0;
            color: #9da8bb;
        }

        .connection {
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 10px 14px;
            background: rgba(255,255,255,0.05);
            border: 1px solid rgba(255,255,255,0.09);
            border-radius: 999px;
        }

        .dot {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            background: #f05f67;
            box-shadow: 0 0 14px rgba(240,95,103,0.7);
        }

        .dot.connected {
            background: #4dd889;
            box-shadow: 0 0 14px rgba(77,216,137,0.7);
        }

        .grid {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 16px;
        }

        .card {
            background: rgba(20, 27, 43, 0.88);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 18px;
            padding: 20px;
            box-shadow: 0 18px 50px rgba(0,0,0,0.22);
        }

        .card-label {
            color: #8f9bb0;
            font-size: 13px;
            text-transform: uppercase;
            letter-spacing: 0.08em;
        }

        .card-value {
            margin-top: 10px;
            font-size: 29px;
            font-weight: 700;
        }

        .positive {
            color: #4dd889;
        }

        .negative {
            color: #ff6b73;
        }

        .section {
            margin-top: 18px;
        }

        .section-title {
            margin: 0 0 14px;
            font-size: 17px;
        }

        .score-layout {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 16px;
        }

        .score {
            font-size: 40px;
            font-weight: 750;
            margin: 8px 0 14px;
        }

        .bar {
            width: 100%;
            height: 10px;
            background: rgba(255,255,255,0.07);
            border-radius: 999px;
            overflow: hidden;
        }

        .bar-fill {
            height: 100%;
            width: 0%;
            border-radius: inherit;
            transition: width 0.35s ease;
        }

        .buy-fill {
            background: linear-gradient(90deg, #278f63, #55e89a);
        }

        .sell-fill {
            background: linear-gradient(90deg, #b33f52, #ff6d78);
        }

        .controls {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 14px;
        }

        .control {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 12px;
        }

        button {
            border: 0;
            border-radius: 11px;
            padding: 10px 16px;
            font-size: 14px;
            font-weight: 650;
            cursor: pointer;
            transition: transform 0.15s ease, opacity 0.15s ease;
        }

        button:hover {
            transform: translateY(-1px);
        }

        button:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }

        .enabled-button {
            background: #245f44;
            color: #baffd4;
        }

        .disabled-button {
            background: #642d38;
            color: #ffd1d5;
        }

        .footer {
            margin-top: 18px;
            color: #778298;
            font-size: 13px;
            text-align: right;
        }

        @media (max-width: 850px) {
            .grid {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }

            .controls,
            .score-layout {
                grid-template-columns: 1fr;
            }
        }

        @media (max-width: 520px) {
            .header {
                align-items: flex-start;
                flex-direction: column;
            }

            .grid {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>

<body>
<div class="container">
    <div class="header">
        <div class="brand">
            <h1>ATLAS</h1>
            <p>Adaptive Trading Learning and Analysis System</p>
        </div>

        <div class="connection">
            <span id="connection-dot" class="dot"></span>
            <span id="connection-text">Connecting to Nyao...</span>
        </div>
    </div>

    <div class="grid">
        <div class="card">
            <div class="card-label">Balance</div>
            <div id="balance" class="card-value">$0.00</div>
        </div>

        <div class="card">
            <div class="card-label">Equity</div>
            <div id="equity" class="card-value">$0.00</div>
        </div>

        <div class="card">
            <div class="card-label">Floating P/L</div>
            <div id="profit" class="card-value">$0.00</div>
        </div>
        <div class="card">
            <div class="card-label">Realized P/L</div>
            <div id="realized-profit" class="card-value">$0.00</div>
        </div>

        <div class="card">
            <div class="card-label">Open Positions</div>
            <div id="positions" class="card-value">0</div>
        </div>
    </div>

    <div class="section score-layout">
        <div class="card">
            <div class="card-label">Buy score</div>
            <div id="buy-score" class="score">0.00</div>

            <div class="bar">
                <div id="buy-bar" class="bar-fill buy-fill"></div>
            </div>
        </div>

        <div class="card">
            <div class="card-label">Sell score</div>
            <div id="sell-score" class="score">0.00</div>

            <div class="bar">
                <div id="sell-bar" class="bar-fill sell-fill"></div>
            </div>
        </div>
    </div>

    <div class="section card">
        <h2 class="section-title">Nyao Controls</h2>

        <div class="controls">
            <div class="control">
                <span>New Trading</span>
                <button id="trading-button" onclick="toggleTrading()">Loading</button>
            </div>

            <div class="control">
                <span>Buy Entries</span>
                <button id="buy-button" onclick="toggleBuy()">Loading</button>
            </div>

            <div class="control">
                <span>Sell Entries</span>
                <button id="sell-button" onclick="toggleSell()">Loading</button>
            </div>
            <div class="control">
                <span>Realized P/L Baseline</span>
                <button onclick="resetRealizedProfit()">
                    Reset Now
                </button>
            </div>
        </div>
    </div>

    <div id="footer" class="footer">
        Waiting for Nyao status...
    </div>
</div>

<script>
    let startingBalance = null;

    const storedStartingBalance =
        localStorage.getItem("atlasStartingBalance");

    if (storedStartingBalance !== null) {
        const parsedStartingBalance =
            Number(storedStartingBalance);

        if (Number.isFinite(parsedStartingBalance)) {
            startingBalance = parsedStartingBalance;
        }
    }
    let currentCommand = {
        enabled: true,
        enable_buy_orders: true,
        enable_sell_orders: true,
        command_version: 1
    };

    function money(value) {
        return new Intl.NumberFormat("en-SG", {
            style: "currency",
            currency: "USD",
            minimumFractionDigits: 2
        }).format(Number(value || 0));
    }

    function updateButton(element, enabled) {
        element.textContent = enabled ? "Enabled" : "Disabled";
        element.className = enabled ? "enabled-button" : "disabled-button";
    }

    async function loadStatus() {
        try {
            const response = await fetch("/api/v1/nyao/status", {
                cache: "no-store"
            });

            if (!response.ok) {
                throw new Error(`Status request failed: ${response.status}`);
            }

            const status = await response.json();

            document.getElementById("balance").textContent =
                money(status.balance);

            document.getElementById("equity").textContent =
                money(status.equity);
                
            const currentBalance =
                Number(status.balance || 0);

            if (
                startingBalance === null &&
                currentBalance > 0
            ) {
                startingBalance = currentBalance;

                localStorage.setItem(
                    "atlasStartingBalance",
                    String(startingBalance)
                );
            }

            const realizedProfit =
                startingBalance === null
                    ? 0
                    : currentBalance - startingBalance;

            const realizedProfitElement =
                document.getElementById("realized-profit");

            realizedProfitElement.textContent =
                money(realizedProfit);

            realizedProfitElement.className =
                "card-value " +
                (
                    realizedProfit > 0
                        ? "positive"
                        : realizedProfit < 0
                            ? "negative"
                : ""
    );

            const profit = Number(status.floating_profit || 0);
            const profitElement = document.getElementById("profit");

            profitElement.textContent = money(profit);
            profitElement.className =
                "card-value " + (profit > 0 ? "positive" : profit < 0 ? "negative" : "");

            document.getElementById("positions").textContent =
                status.open_positions ?? 0;

            const buyScore = Number(status.buy_score || 0);
            const sellScore = Number(status.sell_score || 0);

            document.getElementById("buy-score").textContent =
                buyScore.toFixed(2);

            document.getElementById("sell-score").textContent =
                sellScore.toFixed(2);

            document.getElementById("buy-bar").style.width =
                `${Math.max(0, Math.min(100, buyScore * 10))}%`;

            document.getElementById("sell-bar").style.width =
                `${Math.max(0, Math.min(100, sellScore * 10))}%`;

            const connected = Boolean(status.connected);

            document.getElementById("connection-dot").className =
                connected ? "dot connected" : "dot";

            document.getElementById("connection-text").textContent =
                connected
                    ? `Nyao connected · ${status.symbol}`
                    : "Nyao disconnected";

            document.getElementById("footer").textContent =
                `Last status: ${status.timestamp}`;
        } catch (error) {
            document.getElementById("connection-dot").className = "dot";
            document.getElementById("connection-text").textContent =
                "Unable to reach Nyao";

            console.error(error);
        }
    }

    async function loadCommand() {
        try {
            const response = await fetch("/api/v1/nyao/command", {
                cache: "no-store"
            });

            if (!response.ok) {
                throw new Error(`Command request failed: ${response.status}`);
            }

            currentCommand = await response.json();

            updateButton(
                document.getElementById("trading-button"),
                currentCommand.enabled
            );

            updateButton(
                document.getElementById("buy-button"),
                currentCommand.enable_buy_orders
            );

            updateButton(
                document.getElementById("sell-button"),
                currentCommand.enable_sell_orders
            );
        } catch (error) {
            console.error(error);
        }
    }

    async function saveCommand() {
        const buttons = document.querySelectorAll("button");
        buttons.forEach(button => button.disabled = true);

        try {
            const response = await fetch("/api/v1/nyao/command", {
                method: "PUT",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    enabled: currentCommand.enabled,
                    enable_buy_orders: currentCommand.enable_buy_orders,
                    enable_sell_orders: currentCommand.enable_sell_orders,
                    command_version: currentCommand.command_version || 1
                })
            });

            if (!response.ok) {
                const body = await response.text();
                throw new Error(`Command update failed: ${body}`);
            }

            currentCommand = await response.json();
            await loadCommand();
        } catch (error) {
            alert(error.message);
            console.error(error);
        } finally {
            buttons.forEach(button => button.disabled = false);
        }
    }

    async function toggleTrading() {
        currentCommand.enabled = !currentCommand.enabled;
        await saveCommand();
    }

    async function toggleBuy() {
        currentCommand.enable_buy_orders =
            !currentCommand.enable_buy_orders;

        await saveCommand();
    }

    async function toggleSell() {
        currentCommand.enable_sell_orders =
            !currentCommand.enable_sell_orders;

        await saveCommand();
    }

    async function resetRealizedProfit() {
        try {
            const response = await fetch(
                "/api/v1/nyao/status",
                {
                    cache: "no-store"
                }
            );

            if (!response.ok) {
                throw new Error(
                    `Unable to read current balance: ${response.status}`
                );
            }

            const status = await response.json();
            const currentBalance =
                Number(status.balance || 0);

            if (
                !Number.isFinite(currentBalance) ||
                currentBalance <= 0
            ) {
                throw new Error(
                    "Current balance is not available."
                );
            }

            startingBalance = currentBalance;

            localStorage.setItem(
                "atlasStartingBalance",
                String(startingBalance)
            );

            await loadStatus();
        } catch (error) {
            alert(error.message);
            console.error(error);
        }
    }

    async function refreshDashboard() {
        await Promise.all([
            loadStatus(),
            loadCommand()
        ]);
    }

    refreshDashboard();
    setInterval(loadStatus, 1000);
    setInterval(loadCommand, 3000);
</script>
</body>
</html>
"""