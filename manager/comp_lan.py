import logging
import httplib
import json

from gevent import subprocess

import comp_wifi
from utils import shell


LOGGER = logging.getLogger('fqrouter.%s' % __name__)

picked_devices = {}
fqlan_process = None


def start():
    return [
        ('GET', 'pick-and-play/scan', handle_scan),
        ('POST', 'pick-and-play/forge-default-gateway', handle_forge_default_gateway),
        ('POST', 'pick-and-play/restore-default-gateway', handle_restore_default_gateway),
        ('GET', 'pick-and-play/is-started', handle_is_started)
    ]


def stop():
    global fqlan_process
    try:
        if fqlan_process:
            LOGGER.info('terminate fqlan: %s' % fqlan_process.pid)
            fqlan_process.terminate()
    except:
        LOGGER.exception('failed to terminate fqlan')
    fqlan_process = None


def is_alive():
    if fqlan_process:
        return fqlan_process.poll() is None
    return False


def handle_forge_default_gateway(environ, start_response):
    ip = environ['REQUEST_ARGUMENTS']['ip'].value
    mac = environ['REQUEST_ARGUMENTS']['mac'].value
    picked_devices[ip] = mac
    restart_fqlan()
    start_response(httplib.OK, [('Content-Type', 'text/plain')])
    return []


def handle_restore_default_gateway(environ, start_response):
    ip = environ['REQUEST_ARGUMENTS']['ip'].value
    if ip in picked_devices:
        del picked_devices[ip]
    restart_fqlan()
    start_response(httplib.OK, [('Content-Type', 'text/plain')])
    return [str(len(picked_devices))]


def handle_is_started(environ, start_response):
    is_started = is_alive()
    start_response(httplib.OK, [('Content-Type', 'text/plain')])
    yield 'TRUE' if is_started else 'FALSE'


def handle_scan(environ, start_response):
    try:
        scan_process = subprocess.Popen(
            [shell.PYTHON_PATH, '-m', 'fqlan',
             '--log-level', 'INFO',
             '--log-file', '/data/data/fq.router2/log/scan.log',
             '--lan-interface', comp_wifi.WIFI_INTERFACE,
             '--ifconfig-command', '/data/data/fq.router2/busybox',
             '--ip-command', '/data/data/fq.router2/busybox',
             'scan', '--hostname', '--mark', '0xcafe', '--factor', environ['REQUEST_ARGUMENTS']['factor'].value],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        _, output = scan_process.communicate()
    except:
        LOGGER.exception('failed to scan')
        start_response(httplib.INTERNAL_SERVER_ERROR, [('Content-Type', 'text/plain')])
        return
    try:
        start_response(httplib.OK, [('Content-Type', 'text/plain')])
        for line in output.splitlines():
            ip, mac, hostname = json.loads(line)
            yield str('%s,%s,%s,%s\n' % (ip, mac, hostname, 'TRUE' if ip in picked_devices else 'FALSE'))
    except:
        LOGGER.exception('failed to return scan results')


def restart_fqlan():
    global fqlan_process
    stop()
    if not picked_devices:
        LOGGER.info('no picked devices, fqlan will not start')
        return
    fqlan_process = shell.launch_python(
        'fqlan', ['--log-level', 'INFO',
                  '--log-file', '/data/data/fq.router2/log/fqlan.log',
                  '--lan-interface', comp_wifi.WIFI_INTERFACE,
                  '--ifconfig-command', '/data/data/fq.router2/busybox',
                  '--ip-command', '/data/data/fq.router2/busybox',
                  'forge'] + ['%s,%s' % (ip, mac) for ip, mac in picked_devices.items()], on_exit=stop)