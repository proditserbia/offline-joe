"""Storage diagnostics for Offline Joe (MS4 hardware: root SD + NVMe SSD)."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class StorageInfo:
    mount: str
    total_gb: float
    used_gb: float
    free_gb: float
    percent: float
    mounted: bool


def probe_storage(mounts: list[str] | None = None) -> list[StorageInfo]:
    """Return disk usage information for each mount in *mounts*.

    Defaults to checking ``/`` (root, SD card) and ``/mnt/ssd`` (NVMe SSD).
    """
    import psutil

    if mounts is None:
        mounts = ["/", "/mnt/ssd"]

    results: list[StorageInfo] = []
    for mount in mounts:
        if not os.path.ismount(mount):
            results.append(
                StorageInfo(
                    mount=mount,
                    total_gb=0.0,
                    used_gb=0.0,
                    free_gb=0.0,
                    percent=0.0,
                    mounted=False,
                )
            )
            continue
        try:
            du = psutil.disk_usage(mount)
            gb = 1024 ** 3
            results.append(
                StorageInfo(
                    mount=mount,
                    total_gb=round(du.total / gb, 1),
                    used_gb=round(du.used / gb, 1),
                    free_gb=round(du.free / gb, 1),
                    percent=du.percent,
                    mounted=True,
                )
            )
        except Exception:
            results.append(
                StorageInfo(
                    mount=mount,
                    total_gb=0.0,
                    used_gb=0.0,
                    free_gb=0.0,
                    percent=0.0,
                    mounted=False,
                )
            )
    return results
