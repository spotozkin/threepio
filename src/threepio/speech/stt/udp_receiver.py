"""UDP PCM audio receiver for ESP32->Mac mic streaming.

ESP32 streams 16kHz mono 16-bit PCM frames over UDP.
"""

from __future__ import annotations

import socket
import time
import wave
from pathlib import Path


def write_wav(
    path: Path,
    pcm: bytes,
    *,
    sample_rate: int = 16000,
    channels: int = 1,
    sampwidth: int = 2,
) -> Path:
    """Write raw PCM bytes to a WAV file. Returns the path."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(sampwidth)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm)
    return path


class UdpPcmReceiver:
    """Receive 16kHz mono 16-bit PCM over UDP from ESP32."""

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 40123,
        sample_rate: int = 16000,
        channels: int = 1,
        sampwidth: int = 2,
        frame_bytes: int = 3200,
    ) -> None:
        self.host = host
        self.port = port
        self.sample_rate = sample_rate
        self.channels = channels
        self.sampwidth = sampwidth
        self.frame_bytes = frame_bytes
        self._sock: socket.socket | None = None

    def start(self) -> None:
        """Open UDP socket and bind to host:port."""
        if self._sock is not None:
            return
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((self.host, self.port))

    def receive_seconds(self, seconds: float) -> bytes:
        """Collect raw PCM bytes for the given duration. Call start() first."""
        if self._sock is None:
            raise RuntimeError("UdpPcmReceiver not started; call start() first")
        target_bytes = int(
            seconds * self.sample_rate * self.channels * self.sampwidth
        )
        chunks: list[bytes] = []
        received = 0
        deadline = time.monotonic() + seconds
        self._sock.settimeout(0.5)
        while received < target_bytes and time.monotonic() < deadline:
            try:
                data = self._sock.recv(self.frame_bytes)
                if data:
                    chunks.append(data)
                    received += len(data)
            except socket.timeout:
                continue
            except OSError:
                break
        return b"".join(chunks)

    def close(self) -> None:
        """Close the UDP socket."""
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
