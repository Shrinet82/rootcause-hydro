"""A deliberately small forecaster.

No trained model -- just an online least-squares fit over recent reservoir
volume samples. It answers one operational question: "at the current drain
rate, how many hours until the reservoir is empty?" That feeds a predictive
alert, which is far more useful than a threshold you only trip once it's
already too late. (Swap in Holt-Winters / Prophet post-hackathon.)
"""
from __future__ import annotations

from collections import deque


class ReservoirForecaster:
    def __init__(self, maxlen: int = 60):
        self._samples = deque(maxlen=maxlen)  # (minutes, volume_l)

    def observe(self, minutes: float, volume_l: float) -> None:
        self._samples.append((minutes, volume_l))

    def drain_rate_l_per_min(self):
        n = len(self._samples)
        if n < 5:
            return None
        xs = [p[0] for p in self._samples]
        ys = [p[1] for p in self._samples]
        mx = sum(xs) / n
        my = sum(ys) / n
        denom = sum((x - mx) ** 2 for x in xs)
        if denom == 0:
            return None
        slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom
        return slope  # negative when draining

    def hours_to_empty(self, current_volume_l: float) -> float:
        slope = self.drain_rate_l_per_min()
        if slope is None or slope >= -1e-6:
            return 999.0  # not draining (or refilling)
        minutes = current_volume_l / (-slope)
        return round(minutes / 60.0, 2)
