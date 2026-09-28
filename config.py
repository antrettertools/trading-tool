"""Configuration loading for the AMT charting tool.

Loads config.json from the application root, falling back to config.example.json
defaults for any missing keys so the app always has a complete config object.
"""
from __future__ import annotations

import json
import os
from copy import deepcopy

APP_ROOT = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(APP_ROOT, "config.json")
EXAMPLE_PATH = os.path.join(APP_ROOT, "config.example.json")

DEFAULTS = {
    "alpaca": {
        "api_key": "",
        "api_secret": "",
        "base_url": "https://paper-api.alpaca.markets",
        "feed": "iex",
    },
    "default_ticker": "SPY",
    "default_timeframe": "1d",
    "paper_trading": {"starting_balance": 10000.0},
    "polling_interval_seconds": 30,
    "theme": {
        "background": "#131722",
        "grid": "#1e222d",
        "text": "#d1d4dc",
        "candle_up": "#26a69a",
        "candle_down": "#ef5350",
        "accent": "#2962ff",
        "poc": "#ffeb3b",
        "vah": "#26a69a",
        "val": "#ef5350",
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    out = deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


class Config:
    def __init__(self, data: dict):
        self._data = data

    def __getitem__(self, key):
        return self._data[key]

    def get(self, key, default=None):
        return self._data.get(key, default)

    @property
    def data(self) -> dict:
        return self._data

    @property
    def theme(self) -> dict:
        return self._data["theme"]

    @property
    def alpaca(self) -> dict:
        return self._data["alpaca"]

    @property
    def has_alpaca_keys(self) -> bool:
        a = self._data.get("alpaca", {})
        return bool(a.get("api_key")) and bool(a.get("api_secret")) and \
            "YOUR_" not in a.get("api_key", "")

    def save(self):
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2)


def load_config() -> Config:
    data = deepcopy(DEFAULTS)
    # layer in example file if present (used as documented defaults)
    for path in (EXAMPLE_PATH, CONFIG_PATH):
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = _deep_merge(data, json.load(f))
            except (json.JSONDecodeError, OSError):
                pass
    return Config(data)
