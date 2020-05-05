#!/usr/bin/env python3

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

""" smdv: a simple markdown viewer """

# Imports

# python standard library
import subprocess
import sys

from .utils import limport, parse_args

# import http.client lazily
httpclient = limport('http.client')

# 3rd party CLI dependencies
# fuser
# pandoc

# Globals
ARGS = ""  # the smdv command line arguments
WEBSOCKETS_SERVER = None  # websockets server


# run server in new subprocess
def run_server_in_subprocess(server="quart"):
    """ start the websocket server in a subprocess

    Args:
        server: which server to run in subprocess ["quart", "websocket"]
    """
    args = {
        "--home": ARGS.home,
        "--port": ARGS.port,
        "--websocket-port": ARGS.websocket_port,
        "--css": ARGS.css,
        "--math": ARGS.math
    }
    args_list = [str(s) for kv in args.items() for s in kv]
    subprocess.Popen([f"smdv-{server}"] + args_list)


def stop_quart_server():
    """ stop the smdv server by sending a DELETE request

    Returns:
        exit_status: the exit status (0=success, 1=failure)
    """
    connection = httpclient.HTTPConnection("localhost", ARGS.port)
    try:
        connection.connect()
        connection.request("DELETE", "/")
        response = connection.getresponse().read().decode().strip()
        exit_code = 0 if response == "success." else 1
    except Exception as e:
        print(e)
        exit_code = 1
    finally:
        connection.close()
        return exit_code


def stop_websocket_server():
    """ kills the websocket server

    TODO: find a way to do this more gracefully.

    Returns:
        exit_status: the exit status of the subprocess `fuser -k` system call
    """
    exit_status = subprocess.call(
        ["fuser", "-k", f"{ARGS.websocket_port}/tcp"])
    return exit_status


# get status for the smdv server
def request_server_status(server: str = "quart") -> str:
    """ request the smdv server status

    Args:
        server: the server to ask the status for ["quart", "websocket"]

    Returns:
        status: str: the smdv server status
    """
    if server == "quart":
        connection = httpclient.HTTPConnection("localhost",
                                               ARGS.port)
    elif server == "websocket":
        connection = httpclient.HTTPConnection("localhost",
                                               ARGS.websocket_port)
    else:
        raise ValueError(
            "request_server_status expects a server value of "
            "'quart' or 'server'"
        )
    try:
        connection.connect()
        server_status = "running"
    except ConnectionRefusedError:
        server_status = "stopped"
    finally:
        connection.close()
    return server_status


def main():
    """ The main smdv program

    Returns:
        exit_status: the exit status of smdv.
    """
    global ARGS
    try:
        ARGS = parse_args()

        # first do single-shot smdv flags:
        if ARGS.start_server:
            run_server_in_subprocess(server="quart")
            return 0
        if ARGS.stop_server:
            return stop_quart_server()
        if ARGS.server_status:
            print(request_server_status(server="quart"))
            return 0

        if ARGS.start_websocket_server:
            run_server_in_subprocess(server="websocket")
            return 0
        if ARGS.stop_websocket_server:
            return stop_websocket_server()
        if ARGS.websocket_server_status:
            print(request_server_status(server="websocket"))
            return 0

        if ARGS.start:
            run_server_in_subprocess(server="quart")
            run_server_in_subprocess(server="websocket")
            return 0
        if ARGS.stop:
            exit_status1 = stop_quart_server()
            exit_status2 = stop_websocket_server()
            return exit_status1 + exit_status2

        # if filename argument was given, sync filename or stdin to smdv
        if ARGS.filename:
            connection = httpclient.HTTPConnection("localhost",
                                                   ARGS.port)
            path = ARGS.filename.name
            if path.startswith(ARGS.home):
                path = path[len(ARGS.home):]
                if not path.endswith('/'):
                    path += '/'
                connection = httpclient.HTTPConnection("localhost",
                                                       ARGS.port)
                connection.request("GET", path)
            elif path == '<stdin>':
                connection.request("PUT", "/", ARGS.filename.read())
            return connection.getresponse().code != 200

        # only happens when no arguments are supplied,
        # nor anything was piped into smdv:
        return 0

    except Exception as e:
        print(e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    exit(main())
