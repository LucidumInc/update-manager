import multiprocessing

use_bind = "0.0.0.0:8000"

cores = multiprocessing.cpu_count()
workers_per_core = 1
default_web_concurrency = workers_per_core * cores
web_concurrency = max(int(default_web_concurrency), 2)

# Gunicorn config variables
bind = use_bind
workers = web_concurrency
