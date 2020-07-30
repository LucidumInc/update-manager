flock -xn /tmp/sysInfoMonitor.lock -c "/usr/bin/python /home/demo/current/crontabTask/sysInfo_lib.py > /home/demo/current/crontabTask/sysInfo.log 2>&1"
