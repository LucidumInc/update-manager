import multiprocessing

use_bind = "0.0.0.0:8000"
web_concurrency = min(multiprocessing.cpu_count(), 2)

# Gunicorn config variables
bind = use_bind
workers = web_concurrency
