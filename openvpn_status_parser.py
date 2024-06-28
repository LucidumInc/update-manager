import re
from datetime import datetime

def parse_openvpn_log(log_text: str) -> dict:
    """
    TODO:
    """

    log_data = {
        'updated': None,
        'client_list': [],
        'routing_table': [],
        'global_stats': {},
    }

    if isinstance(log_text, bytes):
        log_text = log_text.decode('utf-8')

    lines = log_text.split('\n')
    section = None

    for line in lines:
        line = line.strip()

        if not line or line == 'END':
            continue

        if line.startswith('OpenVPN CLIENT LIST'):
            section = 'client_list'
        elif line.startswith('Updated'):
            log_data['updated'] = datetime.strptime(line.split(',')[1], '%Y-%m-%d %H:%M:%S')
        elif line.startswith('Common Name'):
            section = 'client_list_headers'
        elif line.startswith('ROUTING TABLE'):
            section = 'routing_table'
        elif line.startswith('Virtual Address'):
            section = 'routing_table_headers'
        elif line.startswith('GLOBAL STATS'):
            section = 'global_stats'
        elif line.startswith('Max bcast/mcast queue length'):
            log_data['global_stats']['max_bcast_mcast_queue_length'] = int(line.split(',')[1])
        else:
            if section == 'client_list':
                fields = line.split(',')
                if len(fields) == 5:
                    client = {
                        'name': fields[0],
                        'real_address': fields[1],
                        'bytes_received': int(fields[2]),
                        'bytes_sent': int(fields[3]),
                        'connected_since': fields[4],
                        'status': 'connected'
                    }
                    log_data['client_list'].append(client)
            elif section == 'routing_table':
                fields = line.split(',')
                if len(fields) == 4:
                    route = {
                        'virtual_address': fields[0],
                        'name': fields[1],
                        'real_address': fields[2],
                        'last_ref': fields[3],
                    }
                    log_data['routing_table'].append(route)

    return log_data
