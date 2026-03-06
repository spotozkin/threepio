"""Ring buffer for audio samples (float32 mono). Used for correlation-gated barge-in."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np


class RingBuffer:
    """
    Fixed-capacity ring buffer for float32 mono audio.
    capacity_ms: minimum capacity in milliseconds at the given sample rate.
    """

    def __init__(self, capacity_ms: int = 1200, sample_rate: int = 16000) -> None:
        import numpy as np

        n = max(1, int(capacity_ms * sample_rate / 1000))
        self._buf: np.ndarray = np.zeros(n, dtype=np.float32)
        self._n = n
        self._write_pos = 0
        self._size = 0
        self._sample_rate = sample_rate
        self._lock = threading.Lock()

    def append(self, samples: "np.ndarray") -> None:
        """Append float32 samples (mono)."""
        import numpy as np

        flat = np.asarray(samples, dtype=np.float32).flatten()
        if flat.size == 0:
            return
        with self._lock:
            for i in range(flat.size):
                self._buf[self._write_pos] = float(flat[i])
                self._write_pos = (self._write_pos + 1) % self._n
            self._size = min(self._size + flat.size, self._n)

    def read_last_ms(self, ms: int, sample_rate: int) -> "np.ndarray":
        """Return the last `ms` milliseconds as float32 array. Empty if insufficient data."""
        import numpy as np

        need = int(ms * sample_rate / 1000)
        if need <= 0:
            return np.array([], dtype=np.float32)
        with self._lock:
            take = min(need, self._size)
            if take == 0:
                return np.array([], dtype=np.float32)
            start = (self._write_pos - take + self._n) % self._n
            if start + take <= self._n:
                return self._buf[start : start + take].copy()
            part1 = self._buf[start : self._n]
            part2 = self._buf[0 : take - (self._n - start)]
            return np.concatenate([part1, part2])

    def read_last_samples(self, n: int) -> "np.ndarray":
        """Return the last `n` samples as float32 array. Fewer than n if buffer has less."""
        import numpy as np

        if n <= 0:
            return np.array([], dtype=np.float32)
        with self._lock:
            take = min(n, self._size)
            if take == 0:
                return np.array([], dtype=np.float32)
            start = (self._write_pos - take + self._n) % self._n
            if start + take <= self._n:
                return self._buf[start : start + take].copy()
            part1 = self._buf[start : self._n]
            part2 = self._buf[0 : take - (self._n - start)]
            return np.concatenate([part1, part2])
