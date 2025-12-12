import time
from functools import wraps

_cache = {}

def cached_response(ttl=3600):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            key = (func.__name__, args, frozenset(kwargs.items()))
            now = time.time()

            if key in _cache:
                value, timestamp = _cache[key]
                if now - timestamp < ttl:
                    return value

            result = func(*args, **kwargs)
            _cache[key] = (result, now)
            return result

        return wrapper
    return decorator

