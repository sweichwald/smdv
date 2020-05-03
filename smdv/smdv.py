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
import os
import re
import sys
import json
import socket
import asyncio
import argparse
import subprocess
import collections
from functools import lru_cache

# 3rd party dependencies
import websockets

# import flask and http.client lazily
from .utils import limport
flask = limport('flask')
httpclient = limport('http.client')

# 3rd party CLI dependencies
# fuser
# pandoc

# Globals
ARGS = ""  # the smdv command line arguments
JSCLIENTS = set()  # jsclients wait for an update from the pyclient
PYCLIENTS = set()  # pyclients update the html body of the jsclient
WEBSOCKETS_SERVER = None  # websockets server
BACKMESSAGES = collections.deque()  # for communication between js and py
FORWARDMESSAGES = collections.deque()  # for communication between js and py
EVENT_LOOP = asyncio.get_event_loop()

MESSAGE = {}

# Templates
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


# Async functions (alphabetic)


# handle a message sent by one of the clients:
async def handle_message(client: websockets.WebSocketServerProtocol,
                         message: str):
    """ handle a message sent by one of the clients

    Args:
        message: the message to update the global message with
    """
    func = message.get("func")
    validate_message(message)
    if "cwd" in message:
        os.chdir(ARGS.home + message["cwd"])
    if not func:
        return
    if func == "back":
        if len(BACKMESSAGES) < 2:
            return
        if message.get("fileOpen"):
            message = BACKMESSAGES.popleft()
        else:
            FORWARDMESSAGES.appendleft(BACKMESSAGES.popleft())
            message = BACKMESSAGES.popleft()
        if len(FORWARDMESSAGES) > 20:
            FORWARDMESSAGES.pop()
        await handle_message(client, message)
        return
    if func == "dir":
        if (
            not message.get("filename")
            and MESSAGE.get("filename")
            and not message.pop("forceClose", False)
        ):
            message["filename"] = MESSAGE["filename"]
            message["fileCwd"] = MESSAGE["fileCwd"]
            message["fileBody"] = MESSAGE["fileBody"]
            message["fileEncoding"] = MESSAGE["fileEncoding"]
            message["fileEncoded"] = MESSAGE["fileEncoded"]
        if not message["cwdEncoded"]:
            message["cwdBody"] = dir2body(message["cwd"])
            message["cwdEncoded"] = True
    if func == "file":
        encode(message)
    if func in {"dir", "file"}:
        MESSAGE.update(message)
        await send_message_to_all_js_clients()
        return


# register websocket client
async def register_client(client: websockets.WebSocketServerProtocol):
    """ register a client

    This function registers a client (websocket) in either the set of
    javascript sockets or the list of python sockets.  The javascript
    socket should identify itself by sending the message 'js' on load.
    The Python socket on the other hand sends the html body, which
    will be transmitted to all connected javascript sockets.

    Args:
        client: the client (websocket) to register.

    """
    message = await client.recv()
    message = json.loads(message)
    clienttype = message.get("client", "")
    if clienttype == "js":
        JSCLIENTS.add(client)
        await client.send(json.dumps(MESSAGE))
    elif clienttype == "py":
        PYCLIENTS.add(client)
    else:
        raise ValueError("not a valid client identifier specified.")
    await handle_message(client, message)


# python websocket client
async def send_as_pyclient_async(message: dict):
    """ send a message to the smdv server as the python client

    Args:
        message: the message to send (in dictionary format)
    """
    message["client"] = "py"
    async with websockets.connect(
        f"ws://{ARGS.websocket_host}:{ARGS.websocket_port}"
    ) as websocket:
        await websocket.send(json.dumps(message))


# serve clients
async def serve_client(client: websockets.WebSocketServerProtocol, path: str):
    """ asynchronous websocket server to serve a websocket client

    Args:
        client: the client (websocket) to serve.
        path: the path over which to serve

    """
    await register_client(client)
    try:
        async for message in client:
            await handle_message(client, json.loads(message))
    finally:
        await unregister_client(client)


# send updated body contents to javascript clients
async def send_message_to_all_js_clients():
    """ send a message to all js clients

    Args:
        message: dict: the message to send

    """
    if (not BACKMESSAGES) or (MESSAGE["cwd"] != BACKMESSAGES[0]["cwd"]):
        BACKMESSAGES.appendleft(
            {
                "client": "py",
                "func": "dir",
                "cwd": MESSAGE["cwd"],
                "cwdBody": MESSAGE["cwdBody"],
                "cwdEncoded": MESSAGE["cwdEncoded"],
                "filename": "",
                "fileBody": "",
                "fileCwd": "",
                "fileOpen": False,
                "fileEncoding": "",
                "fileEncoded": False,
            }
        )
        if len(BACKMESSAGES) > 20:
            BACKMESSAGES.pop()
    if JSCLIENTS:
        await asyncio.wait(
            [client.send(json.dumps(MESSAGE)) for client in JSCLIENTS])


# unregister websocket client
async def unregister_client(client: websockets.WebSocketServerProtocol):
    """ unregister a client

    Args:
        client: the client (websocket) to unregister.

    """
    if client in JSCLIENTS:
        JSCLIENTS.remove(client)
    if client in PYCLIENTS:
        PYCLIENTS.remove(client)


# Normal functions (alphabetic)

# function to change the current working directory
def change_current_working_directory(path: str) -> str:
    """ change the current working directory

    Args:
        path: filename or directory name. If a filename is given,
            the current directory will be changed to the containing
            folder
    """
    i = 1 if (path and path[0] == "/") else 0
    fullpath = os.path.join(ARGS.home, path[i:])
    filename = ""
    dirpath = fullpath
    if not os.path.isdir(fullpath):
        filename = os.path.basename(fullpath)
        dirpath = os.path.dirname(fullpath)
    if dirpath.endswith("/"):
        dirpath = dirpath[:-1]
    cwd = os.path.abspath(os.getcwd())
    if cwd.endswith("/"):
        cwd = cwd[:-1]
    if not os.path.isdir(dirpath):
        raise FileNotFoundError(f"Could not find directory {dirpath}")
    if (not os.path.exists(fullpath)
            and filename not in ["live_pipe", "live_put"]):
        raise FileNotFoundError(f"Could not find file {fullpath}")
    if cwd != dirpath:
        os.chdir(dirpath)
    cwd = os.path.abspath(os.getcwd()) + "/"
    cwd = cwd[len(ARGS.home):]
    return cwd, filename


# flask app factory
def create_app():
    """ flask app factory

    Returns:
        app: the flask app

    """

    app = flask.Flask(
        __name__, static_folder=ARGS.home, static_url_path="/@static")

    # stop the flask server
    def stop_flask_server() -> int:
        """ stop the flask server

        Returns:
            exit_status: exit status of the request (0: success, 1: failure)

        """
        func = flask.request.environ.get("werkzeug.server.shutdown")
        try:
            func()
            return 0
        except Exception:
            return 1

    # index route for the smdv app
    @app.route("/", methods=["GET", "PUT", "DELETE"])
    @app.route("/<path:path>/", methods=["GET"])
    def index(path: str = "") -> str:
        """ the main (index) route of smdv

        Returns:
            html: the html representation of the requested path
        """
        if flask.request.method == "GET":
            try:
                cwd, filename = change_current_working_directory(path)
            except FileNotFoundError:
                return flask.abort(404)

            html = open(f'{BASE_DIR}/smdv.html', 'r').read()
            replacements = {
                '{SMDV-home-SMDV}': ARGS.home,
                '{SMDV-css-SMDV}': open(ARGS.css, 'r').read(),
                '{SMDV-host-SMDV}': ARGS.websocket_host,
                '{SMDV-port-SMDV}': ARGS.websocket_port,
            }
            for k, v in replacements.items():
                html = html.replace(k, v)

            if filename:
                if is_binary_file(filename):
                    return flask.redirect(
                        flask.url_for("static", filename=path))
                with open(filename, "r") as file:
                    send_as_pyclient(
                        {
                            "func": "file",
                            "cwd": cwd,
                            "cwdBody": dir2body(cwd),
                            "cwdEncoded": True,
                            "filename": filename,
                            "fileBody": file.read(),
                            "fileCwd": cwd,
                            "fileOpen": True,
                            "fileEncoding": "",
                            "fileEncoded": False,
                        }
                    )
                    return html
            # this only happens if requested path is a directory
            send_as_pyclient(
                {
                    "func": "dir",
                    "cwd": cwd,
                    "cwdBody": dir2body(cwd),
                    "cwdEncoded": True,
                    "filename": filename,
                    "fileBody": "",
                    "fileCwd": cwd,
                    "fileOpen": False,
                    "fileEncoding": "",
                    "fileEncoded": False,
                }
            )
            return html

        if flask.request.method == "PUT":
            cwd = (
                os.path.abspath(
                    os.path.expanduser(os.getcwd()))[len(ARGS.home):] + "/"
            )
            send_as_pyclient(
                {
                    "func": "file",
                    "cwd": cwd,
                    "cwdBody": dir2body(cwd),
                    "cwdEncoded": True,
                    "filename": "live_put",
                    "fileBody": flask.request.data.decode(),
                    "fileCwd": cwd,
                    "fileOpen": True,
                    "fileEncoding": "md",
                    "fileEncoded": False,
                }
            )
            return ""

        if flask.request.method == "DELETE":
            exit_status = stop_flask_server()
            return "failed.\n" if exit_status else "success.\n"

        # should never get here:
        return "failed.\n"

    return app


# encode a string in the given encoding format
def encode(message: dict) -> dict:
    """ encode the body of a message. """
    if message.get("fileEncoded", False):
        return message  # don't encode again if the message is already encoded
    message["fileEncoded"] = True
    encoding = message.get("fileEncoding")
    filename = message.get("filename")
    if not encoding:
        if filename[0] == "." and "." not in filename[1:]:
            encoding = "txt"
        else:
            encoding = os.path.splitext(message.get("filename"))[1][1:]
            if not encoding:
                encoding = "md"
        message["fileEncoding"] = encoding
    if encoding == "md":
        message["fileBody"] = md2body(message["fileBody"])
        return message
    if encoding == "txt":
        message["fileBody"] = txt2body(message["fileBody"])
        return message
    if message["fileEncoding"] == "html":
        return message

    message["fileEncoding"] = "txt"
    message["fileEncoded"] = False
    return encode(message)


# convert a directory path to a markdown representation of the directory view
def dir2body(cwd: str) -> str:
    """ convert a directory path to a markdown representation of the directory view

    Args:
        cwd: str: the current working directory path to convert to html

    Returns:
        html: str: the resulting html
    """
    i = 1 if (cwd and cwd[0] == "/") else 0
    path = os.path.join(ARGS.home, cwd[i:])
    paths = sorted([p for p in os.listdir(path)], key=str.upper)
    paths = [os.path.join(path, p) for p in paths]

    def url(path):
        return path.replace(ARGS.home, f"http://127.0.0.1:{ARGS.port}")

    def link(i, t, p):
        return (f"{t}{i}&nbsp;{os.path.basename(p)}{t[0]}/{t[1:]}", url(p))

    dirlinks = [link("📁", "<b>", p) for p in paths if os.path.isdir(p)]
    filelinks = [link("📄", " ", p) for p in paths if not os.path.isdir(p)]
    dirhtml = [f'<a href="{url}">{name}</a>' for name, url in dirlinks]
    filehtml = [
        f'<a href="{url}">{name.replace("/","")}</a>'
        for name, url in filelinks
    ]
    html = "<br>\n".join(dirhtml + filehtml)
    return html


# check if a file is a binary
def is_binary_file(filename: str) -> bool:
    """ check if a file can be considered a binary file

    Args:
        filename: str: the filename of the file to check

    Returns:
        is_binary_string: bool: the truth value indicating wether the file is
            binary or not.
    """
    textchars = (
        bytearray([7, 8, 9, 10, 12, 13, 27])
        + bytearray(range(0x20, 0x7F))
        + bytearray(range(0x80, 0x100))
    )

    def is_binary_string(inbytes):
        return bool(inbytes.translate(None, textchars))

    if not os.path.exists(filename):
        return False

    if is_binary_string(open(filename, "rb").read(1024)):
        return True
    else:
        return False


@lru_cache(maxsize=10000)
def json2html(inputstr):
    return subprocess.run(
        ["pandoc", "--from", "json", "--to", "html5", "--mathml"],
        stdout=subprocess.PIPE,
        input=inputstr.encode()).stdout.decode()


urlRegex = re.compile('(href|src)=[\'"](?!/|https://|http://|#)(.*)[\'"]')


def md2body(content: str = "") -> str:
    """ convert markdown to html using pandoc markdown

    Args:
        content: the markdown string to convert

    Returns:
        html: str: the resulting html

    """
    # pandoc fix: make % shown as a single % (in stead of stopping conversion)
    # TODO: ?
    content = content.replace("%", "%%")

    if len(content) > 4 and content[:4] == 'cwd:':
        lines = content.split('\n')
        content = '\n'.join(lines[1:])
        cwd = '/' + lines[0][4:] + '/'
    else:
        cwd = os.path.abspath(os.getcwd()).replace(ARGS.home, "") + "/"

    jsonout = json.loads(subprocess.run(
        ["pandoc", "--from", "markdown+emoji", "--to", "json", "--mathml"],
        stdout=subprocess.PIPE,
        input=content.encode()).stdout)
    blocks = jsonout['blocks']

    htmlblocks = []

    markertag = '<a name=\\"#marker\\" id=\\"marker\\"></a>'
    marker = '<a name="#marker" id="marker"></a>'
    for b in blocks:
        jsonout['blocks'] = [b]
        jsontext = json.dumps(jsonout)
        html = "\n"
        if jsontext.find(markertag) >= 0:
            html += marker + '\n'
            jsontext = jsontext.replace(markertag, '')
        html += "\n" + json2html(jsontext)

        html = urlRegex.sub(
            f'\\1="http://{ARGS.host}:{ARGS.port}/@static{cwd}\\2"',
            html)

        htmlblocks.append([hash(html), html])

    return htmlblocks


# print a message (useful for logging)
def print_message(message: dict, **kwargs):
    """ print a message

    Args:
        message: the message to print nicely
        **kwargs: the keyword arguments to print/suppress (defaults are true)
    """
    indent = kwargs.pop("indent", 0)
    for k, v in message.items():
        if kwargs.get(k, True):
            if k == "fileBody" or k == "cwdBody":
                v = v[:20]
            print(f"{'    '*indent}{k}\t{repr(v)}")


# send a message to the websocket server at the python client
def send_as_pyclient(message: dict):
    """ send a message to the websocket server as the python client

    Args:
        message: the message to send (in dictionary format)
    """
    try:
        EVENT_LOOP.run_until_complete(send_as_pyclient_async(message))
    except RuntimeError:
        pass  # allows messages to be lost when sending many messages at once.


# send message to smdv to load filename or live_pipe
def update_filename():
    """ open filename in smdv """
    path = ARGS.filename.name
    if path == '<stdin>':
        cwd = os.path.abspath(
            os.path.expanduser(os.getcwd()))[len(ARGS.home):] + "/"
        filename = 'live_pipe'
    elif path.startswith(ARGS.home):
        path = path[len(ARGS.home):]
        cwd, filename = change_current_working_directory(path)
    content = ARGS.filename.read()
    message = {
        "func": "file",
        "cwd": cwd,
        "cwdBody": dir2body(cwd),
        "cwdEncoded": True,
        "filename": filename,
        "fileBody": content,
        "fileCwd": cwd,
        "fileOpen": True,
        "fileEncoding": "",
        "fileEncoded": False,
    }
    send_as_pyclient(message)


# check if a socket is in use
def socket_in_use(address: str) -> bool:
    """ check if a socket is in use

    Args:
        address: str: the address of the unix/inet socket

    Returns:
        in_use: bool: wether the socket is in use or not.
    """

    if ":" in address:  # inet socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        host, port = address.split(":")
        result = sock.connect_ex((host, int(port)))
        if result == 0:
            return True
        else:
            return False
        sock.close()
    else:  # unix socket
        if os.path.exists(address):
            return True
        return False


# convert text file to html
def txt2body(content: str) -> str:
    """ Convert text content to html

    Args:
        content: the content to encode as html
    """
    content = f"```\n{content}\n```"
    return md2body(content)


def validate_message(message: str):
    """ check if the message is a valid websocket message """
    if message.get("client", "func") in {"dir", "file"}:
        keys = {
            "client",
            "func",
            "cwd",
            "cwdBody",
            "cwdEncoded",
            "filename",
            "fileBody",
            "fileCwd",
            "fileOpen",
            "fileEncoding",
            "fileEncoded",
        }
        for key in keys:
            assert key in message, f"message {message} has no key '{key}'"
            assert key in keys, f"{key} is not a valid message key"


# run the flask server
def run_flask_server():
    global ARGS
    ARGS = parse_args()
    """ start the flask server """
    create_app().run(
        debug=False, port=ARGS.port, host=ARGS.host, threaded=True)


# websocket server
def run_websocket_server():
    """ start and run the websocket server """
    global WEBSOCKETS_SERVER
    global ARGS
    ARGS = parse_args()
    WEBSOCKETS_SERVER = websockets.serve(
        serve_client, ARGS.websocket_host, ARGS.websocket_port
    )
    EVENT_LOOP.run_until_complete(WEBSOCKETS_SERVER)
    EVENT_LOOP.run_forever()


# run server in new subprocess
def run_server_in_subprocess(server="flask"):
    """ start the websocket server in a subprocess

    Args:
        server: which server to run in subprocess ["flask", "websocket"]
    """
    args = {
        "--home": ARGS.home,
        "--port": ARGS.port,
        "--websocket-port": ARGS.websocket_port,
        "--host": ARGS.host,
        "--websocket-host": ARGS.websocket_host,
        "--css": ARGS.css,
    }
    args_list = [str(s) for kv in args.items() for s in kv]
    subprocess.Popen([f"smdv-{server}"] + args_list)


def stop_flask_server():
    """ stop the smdv server by sending a DELETE request

    Returns:
        exit_status: the exit status (0=success, 1=failure)
    """
    connection = httpclient.HTTPConnection(ARGS.host, ARGS.port)
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
def request_server_status(server: str = "flask") -> str:
    """ request the smdv server status

    Args:
        server: the server to ask the status for ["flask", "websocket"]

    Returns:
        status: str: the smdv server status
    """
    if server == "flask":
        connection = httpclient.HTTPConnection(ARGS.host,
                                               ARGS.port)
    elif server == "websocket":
        connection = httpclient.HTTPConnection(ARGS.websocket_host,
                                               ARGS.websocket_port)
    else:
        raise ValueError(
            "request_server_status expects a server value of "
            "'flask' or 'server'"
        )
    try:
        connection.connect()
        server_status = "running"
    except ConnectionRefusedError:
        server_status = "stopped"
    finally:
        connection.close()
    return server_status


def parse_args(args=None) -> argparse.Namespace:
    """ populate the smdv command line arguments

    Args:
        args: the arguments to parse

    Returns:
        parsed_args: the parsed arguments

    """
    # Argument parser
    parser = argparse.ArgumentParser(
        description="smdv: a Simple MarkDown Viewer")
    parser.add_argument(
        "filename",
        type=argparse.FileType('r'),
        nargs="?",
        default=(None if sys.stdin.isatty() else sys.stdin),
        help="path or file to open with smdv",
    )
    parser.add_argument(
        "-H",
        "--home",
        default=os.environ.get("SMDV_DEFAULT_HOME", os.path.expanduser("~")),
        help="set the root folder of the smdv server",
    )
    parser.add_argument(
        "-p",
        "--port",
        default=os.environ.get("SMDV_DEFAULT_PORT", "9876"),
        help="port on which smdv is served.",
    )
    parser.add_argument(
        "-w",
        "--websocket-port",
        default=os.environ.get("SMDV_DEFAULT_WEBSOCKET_PORT", "9877"),
        help="port for websocket communication",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("SMDV_DEFAULT_HOST", "localhost"),
        help=("host on which smdv is served "
              "(for now, only localhost is supported)"),
        choices=["localhost", "127.0.0.1"],
    )
    parser.add_argument(
        "--websocket-host",
        default=os.environ.get("SMDV_DEFAULT_WEBSOCKET_HOST", "localhost"),
        help=("host for websocket communication "
              "(for now, only localhost is supported)"),
        choices=["localhost", "127.0.0.1"],
    )
    parser.add_argument(
        "--css",
        default=os.environ.get(
            "SMDV_DEFAULT_CSS",
            f"{BASE_DIR}/smdv.css",
        ),
        help="location of a local markdown css file",
    )
    single_shot_arguments = parser.add_mutually_exclusive_group()
    single_shot_arguments.add_argument(
        "--server-status",
        action="store_true",
        default=os.environ.get("SMDV_DEFAULT_SERVER_STATUS", False),
        help="ask status of the smdv server",
    )
    single_shot_arguments.add_argument(
        "--websocket-server-status",
        action="store_true",
        default=os.environ.get("SMDV_DEFAULT_WEBSOCKET_SERVER_STATUS", False),
        help="ask status of the smdv server",
    )
    single_shot_arguments.add_argument(
        "--start-server",
        action="store_true",
        default=os.environ.get("SMDV_DEFAULT_START_SERVER", False),
        help="start the smdv server (without doing anything else)",
    )
    single_shot_arguments.add_argument(
        "--stop-server",
        action="store_true",
        default=os.environ.get("SMDV_DEFAULT_STOP_SERVER", False),
        help="stop the smdv server (without doing anything else)",
    )
    single_shot_arguments.add_argument(
        "--start-websocket-server",
        action="store_true",
        default=os.environ.get("SMDV_DEFAULT_START_WEBSOCKET_SERVER", False),
        help="start the smdv websocket server (without doing anything else)",
    )
    single_shot_arguments.add_argument(
        "--stop-websocket-server",
        action="store_true",
        default=os.environ.get("SMDV_DEFAULT_STOP_WEBSOCKET_SERVER", False),
        help="stop the smdv websocket server (without doing anything else)",
    )
    single_shot_arguments.add_argument(
        "--stop",
        action="store_true",
        default=os.environ.get("SMDV_DEFAULT_STOP", False),
        help="stop smdv running in the background (kills both servers)",
    )
    single_shot_arguments.add_argument(
        "--start",
        action="store_true",
        default=os.environ.get("SMDV_DEFAULT_START", False),
        help="start smdv (both servers)",
    )
    parsed_args = parser.parse_args(args=args)
    if parsed_args.home.endswith("/"):
        parsed_args.home = parsed_args.home[:-1]
    if not os.path.isdir(parsed_args.home):
        raise ValueError(
            f"invalid home location given from smdv: {parsed_args.home}")
    return parsed_args


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
            run_server_in_subprocess(server="flask")
            return 0
        if ARGS.stop_server:
            return stop_flask_server()
        if ARGS.server_status:
            print(request_server_status(server="flask"))
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
            run_server_in_subprocess(server="flask")
            run_server_in_subprocess(server="websocket")
            return 0
        if ARGS.stop:
            exit_status1 = stop_flask_server()
            exit_status2 = stop_websocket_server()
            return exit_status1 + exit_status2

        # if filename argument was given, sync filename or stdin to smdv
        if ARGS.filename:
            update_filename()
            return 0

        # only happens when no arguments are supplied,
        # nor anything was piped into smdv:
        return 0

    except Exception as e:
        print(e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    exit(main())
