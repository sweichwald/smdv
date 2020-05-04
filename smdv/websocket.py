import asyncio
import collections
from functools import lru_cache
import json
import os
import re
import subprocess
import websockets

from .utils import parse_args


JSCLIENTS = set()  # jsclients wait for an update from the pyclient
PYCLIENTS = set()  # pyclients update the html body of the jsclient
BACKMESSAGES = collections.deque()  # for communication between js and py
FORWARDMESSAGES = collections.deque()  # for communication between js and py
MESSAGE = {}
EVENT_LOOP = asyncio.get_event_loop()


def run_websocket_server():
    """ start and run the websocket server """
    global WEBSOCKETS_SERVER
    global ARGS
    ARGS = parse_args()
    WEBSOCKETS_SERVER = websockets.serve(serve_client,
                                         ARGS.websocket_host,
                                         ARGS.websocket_port)
    EVENT_LOOP.run_until_complete(WEBSOCKETS_SERVER)
    EVENT_LOOP.run_forever()


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


async def unregister_client(client: websockets.WebSocketServerProtocol):
    """ unregister a client

    Args:
        client: the client (websocket) to unregister.

    """
    if client in JSCLIENTS:
        JSCLIENTS.remove(client)
    if client in PYCLIENTS:
        PYCLIENTS.remove(client)


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


# encode a message in the given encoding format
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


# convert text file to html
def txt2body(content: str) -> str:
    """ Convert text content to html

    Args:
        content: the content to encode as html
    """
    content = f"```\n{content}\n```"
    return md2body(content)


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
