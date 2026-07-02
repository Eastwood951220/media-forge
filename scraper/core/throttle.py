import random
import time


def random_sleep(min_seconds: float, max_seconds: float) -> None:
    delay = random.uniform(min_seconds, max_seconds)
    print(f"[Delay] sleep {delay:.2f}s")
    time.sleep(delay)


def fixed_sleep(seconds: float, reason: str | None = None) -> None:
    if reason:
        print(f"[Wait] {reason}, sleep {seconds:.0f}s")
    else:
        print(f"[Wait] sleep {seconds:.0f}s")

    time.sleep(seconds)
