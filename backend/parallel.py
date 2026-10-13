"""Outside calls run side by side: several Reed searches, or several model calls for one request."""
from concurrent.futures import ThreadPoolExecutor

WORKERS = 8


def together(work, items, workers: int = WORKERS) -> list:
    """work(item) for every item, at the same time, results in the order of the items."""
    if not items:
        return []
    with ThreadPoolExecutor(max_workers=min(workers, len(items))) as pool:
        return list(pool.map(work, items))
