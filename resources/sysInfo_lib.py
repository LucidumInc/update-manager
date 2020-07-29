#!/usr/bin/python
#Author: nulige
# -*- coding: UTF-8 -*-
import re
import sys
import time
import socket
import platform
import subprocess
import pickle
import struct
import os,time
import psutil


CARBON_SERVER = '127.0.0.1'
CARBON_PICKLE_PORT = 2004
DELAY = 20
CPU_CHECK_DELAY = 2
def get_cpu_usage():
    """
    """
    cpuCmd = 'top -b -n1 | grep -i \'Cpu\''
    idleCpu = os.popen(str(cpuCmd)).read().split(',')[3].strip().split()[0]
    cpuUsage = 100 - float(idleCpu)
    return str(cpuUsage);

def get_mem_usage():
    """
    """
    memCmd = 'free -m | sed -n \'2p\''
    memInfo = os.popen(str(memCmd)).read().split()
    memUsed = float(memInfo[2])
    memTotal = float(memInfo[1])
    memPercent = round(memUsed * 100/ memTotal,2)
    return str(memPercent);

def get_disk_usage():
    """
    """
    diskCmd = 'df | grep /dev/sda1'
    diskUsage = os.popen(str(diskCmd)).read().strip().split()[4][:-1]
    return diskUsage;

def get_cpu_usage_psutil():
    """
    """
    cpuUsage = psutil.cpu_percent(interval=None)
    time.sleep(CPU_CHECK_DELAY)
    cpuUsage = psutil.cpu_percent(interval=None)
    return str(cpuUsage);

def get_mem_usage_psutil():
    """
    """
    info = psutil.virtual_memory()
    memPercent = info.percent
    return str(memPercent);

def get_disk_usage_psutil():
    """
    """
    info = psutil.disk_usage('/')
    diskUsage = info.percent
    return diskUsage;

def run(sock, delay):
    """Make the client go go go"""
    metricPrefix = 'server.system'
    #while True:
    now = int(time.time())
    tuples = ([])
    lines = []
    #We're gonna report all three loadavg values
    cpu = get_cpu_usage_psutil();
    mem = get_mem_usage_psutil();
    disk = get_disk_usage_psutil();
    tuples.append((metricPrefix + '.cpu_usage', (now,cpu)))
    tuples.append((metricPrefix + '.mem_usage', (now,mem)))
    tuples.append((metricPrefix + '.disk_usage', (now,disk)))
    lines.append(metricPrefix + ".cpu_usage %s %d" % (cpu, now))
    lines.append(metricPrefix + ".mem_usage %s %d" % (mem, now))
    lines.append(metricPrefix + ".disk_usage %s %d" % (disk, now))
    message = '\n'.join(lines) + '\n' #all lines must end in a newline
    print("sending pickle message")
    print('-' * 80)
    print(message)
    package = pickle.dumps(tuples, 1)
    size = struct.pack('!L', len(package))
    sock.sendall(size)
    sock.sendall(package)
    
    #time.sleep(delay)

def main():
    """Wrap it all up together"""
    delay = DELAY
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg.isdigit():
            delay = int(arg)
        else:
            sys.stderr.write("Ignoring non-integer argument. Using default: %ss\n" % delay)

    sock = socket.socket()
    try:
        sock.connect( (CARBON_SERVER, CARBON_PICKLE_PORT) )
    except socket.error:
        raise SystemExit("Couldn't connect to %(server)s on port %(port)d, is carbon-cache.py running?" % { 'server':CARBON_SERVER, 'port':CARBON_PICKLE_PORT })

    try:
        run(sock, delay)
    except KeyboardInterrupt:
        sys.stderr.write("\nExiting on CTRL-c\n")
        sys.exit(0)

if __name__ == "__main__":
    main()
