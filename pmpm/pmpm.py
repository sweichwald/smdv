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

""" pmpm: pandoc markdown preview machine, a simple markdown previewer """

import subprocess

from .utils import limport, parse_args

# import http.client lazily
httpclient = limport('http.client')


def run_server_in_subprocess(port, home, math):
    """ start the websocket server in a subprocess
    """
    subprocess.Popen(["pmpm-websocket",
                      "--port", port,
                      "--home", home,
                      "--math", math])


def stop_websocket_server(port):
    """ kills the websocket server

    TODO: find a way to do this more gracefully.

    Returns:
        exit_status: the exit status of the subprocess `fuser -k` system call
    """
    exit_status = subprocess.call(
        ["fuser", "-k", f"{port}/tcp"])
    return exit_status


# get status for the pmpm server
def request_server_status(port) -> str:
    """ request the pmpm server status

    Returns:
        status: str: the pmpm server status
    """
    connection = httpclient.HTTPConnection("localhost",
                                           port)
    try:
        connection.connect()
        server_status = "running"
    except ConnectionRefusedError:
        server_status = "stopped"
    finally:
        connection.close()
    return server_status


def main():
    """ The main pmpm program

    Returns:
        exit_status: the exit status of pmpm.
    """
    try:
        ARGS = parse_args()
        # first do single-shot pmpm flags:
        if ARGS.start:
            if request_server_status(ARGS.port) != "running":
                run_server_in_subprocess(
                    ARGS.port, ARGS.home, ARGS.math)
            return 0
        if ARGS.stop:
            return stop_websocket_server(ARGS.port)
        if ARGS.status:
            print(request_server_status(ARGS.port))
            return 0

        # if filename argument was given, sync filename or stdin to pmpm
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
        # nor anything was piped into pmpm:
        return 0

    except Exception as e:
        print(e)
        return 1


if __name__ == "__main__":
    exit(main())
