"""Token + cost accounting and hard budget guards."""
from collections import defaultdict
from . import config


class CostTracker:
    def __init__(self, max_usd=config.MAX_USD_DEFAULT, max_calls=config.MAX_CALLS_DEFAULT):
        self.max_usd, self.max_calls = max_usd, max_calls
        self.calls = 0
        self.by_model = defaultdict(lambda: {"calls": 0, "input_tokens": 0, "output_tokens": 0, "usd": 0.0})
        self.unpriced = set()

    def record(self, spec, input_tokens: int, output_tokens: int):
        price = config.PRICES_PER_MTOK.get(spec.model) or config.PRICES_PER_MTOK.get(spec.provider)
        if price is None:
            self.unpriced.add(spec.label)
            price = (0.0, 0.0)
        usd = input_tokens / 1e6 * price[0] + output_tokens / 1e6 * price[1]
        m = self.by_model[spec.label]
        m["calls"] += 1; m["input_tokens"] += input_tokens; m["output_tokens"] += output_tokens; m["usd"] += usd
        self.calls += 1

    @property
    def usd(self) -> float:
        return sum(m["usd"] for m in self.by_model.values())

    def over_budget(self) -> bool:
        return self.usd >= self.max_usd or self.calls >= self.max_calls

    def report(self) -> dict:
        return {
            "calls": self.calls, "estimated_usd": round(self.usd, 4),
            "budget_usd": self.max_usd, "budget_calls": self.max_calls,
            "by_model": {k: {**v, "usd": round(v["usd"], 4)} for k, v in self.by_model.items()},
            "unpriced_models": sorted(self.unpriced),
        }
