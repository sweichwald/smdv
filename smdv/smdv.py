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


# run server in new subprocess
def run_server_in_subprocess():
    """ start the websocket server in a subprocess
    """
    args = {
        "--home": ARGS.home,
        "--port": ARGS.port,
        "--math": ARGS.math
    }
    args_list = [str(s) for kv in args.items() for s in kv]
    subprocess.Popen([f"smdv-websocket"] + args_list)


def stop_websocket_server():
    """ kills the websocket server

    TODO: find a way to do this more gracefully.

    Returns:
        exit_status: the exit status of the subprocess `fuser -k` system call
    """
    exit_status = subprocess.call(
        ["fuser", "-k", f"{ARGS.port}/tcp"])
    return exit_status


# get status for the smdv server
def request_server_status() -> str:
    """ request the smdv server status

    Returns:
        status: str: the smdv server status
    """
    connection = httpclient.HTTPConnection("localhost",
                                           ARGS.port)
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
        if ARGS.start:
            run_server_in_subprocess()
            return 0
        if ARGS.stop:
            return stop_websocket_server()
        if ARGS.status:
            print(request_server_status())
            return 0

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
