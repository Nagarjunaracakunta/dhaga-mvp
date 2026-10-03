"""Read raw CSVs. Everything is loaded as strings; typing happens in validation."""
import pandas as pd
from pathlib import Path
from . import config


def load_csv(path: Path, required_columns: list[str]) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    df.columns = [c.strip() for c in df.columns]
    missing = [c for c in required_columns if c not in df.columns]
    if missing:
        raise ValueError(f"{path.name}: missing columns {missing}")
    return df


def load_products(data_dir: Path = config.DATA_DIR) -> pd.DataFrame:
    return load_csv(data_dir / "products.csv", config.PRODUCT_COLUMNS)


def load_orders(data_dir: Path = config.DATA_DIR) -> pd.DataFrame:
    return load_csv(data_dir / "orders.csv", config.ORDER_COLUMNS)


def load_returns(data_dir: Path = config.DATA_DIR) -> pd.DataFrame:
    return load_csv(data_dir / "returns.csv", config.RETURN_COLUMNS)
