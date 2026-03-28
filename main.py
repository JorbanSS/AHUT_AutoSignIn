from pathlib import Path

from app.runner import run_forever


CONFIG_PATH = Path(__file__).with_name("config.json")


if __name__ == "__main__":
    raise SystemExit(run_forever(CONFIG_PATH))
