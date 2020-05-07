import asyncio
import concurrent.futures
from functools import lru_cache
import json
import os
import re
import time
import subprocess
import websockets

from .utils import parse_args


N_WORKERS_PANDOC = 16
LRU_CACHE_SIZE = 2048

JSCLIENTS = set()  # jsclients wait for an update from the pyclient
EVENT_LOOP = asyncio.get_event_loop()
NAMED_PIPE = os.environ.get("XDG_RUNTIME_DIR", "/tmp") + "/smdv_pipe"


def run_websocket_server():
    """ start and run the websocket server """
    global ARGS
    ARGS = parse_args()
    EVENT_LOOP.set_default_executor(
        concurrent.futures.ThreadPoolExecutor(max_workers=N_WORKERS_PANDOC))
    WEBSOCKETS_SERVER = websockets.serve(serve_client,
                                         "localhost",
                                         ARGS.port)
    EVENT_LOOP.create_task(asyncio.start_unix_server(piper, NAMED_PIPE))
    EVENT_LOOP.run_until_complete(WEBSOCKETS_SERVER)
    EVENT_LOOP.run_forever()


async def piper(reader, writer):
    instr = await reader.read(-1)
    if instr != b'':
        # filepath passed along
        content = instr.decode()
        if content.startswith('fpath:'):
            lines = content.split('\n')
            fpath = lines.pop(0)[6:]
            cwd = fpath.rsplit('/', 1)[0] + '/'
            content = '\n'.join(lines)
        else:
            fpath = "LIVE"
            cwd = ARGS.home + '/'
        message = {
            "fpath": fpath.replace(ARGS.home, ''),
            "htmlblocks": await md2htmlblocks(content, cwd),
            }
        EVENT_LOOP.create_task(send_message_to_all_js_clients(message))


async def serve_client(client: websockets.WebSocketServerProtocol, path: str):
    """ asynchronous websocket server to serve a websocket client

    Args:
        client: the client (websocket) to serve.
        path: the path over which to serve

    """
    await register_client(client)
    try:
        async for message in client:
            await handle_message(client, message)
    finally:
        EVENT_LOOP.create_task(unregister_client(client))


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
    JSCLIENTS.add(client)


async def unregister_client(client: websockets.WebSocketServerProtocol):
    """ unregister a client

    Args:
        client: the client (websocket) to unregister.

    """
    if client in JSCLIENTS:
        JSCLIENTS.remove(client)


def readfile(fpath):
    try:
        with open(fpath, 'r') as f:
            content = f.read()
    except (FileNotFoundError, IsADirectoryError):
        return None
    return content


async def handle_message(client: websockets.WebSocketServerProtocol,
                         message: str):
    """ handle a message sent by one of the clients
    """
    fpath = ARGS.home + message
    content = await EVENT_LOOP.run_in_executor(None, readfile, fpath)
    if content:
        cwd = fpath.rsplit('/', 1)[0] + '/'
        message = {
            "fpath": fpath.replace(ARGS.home, ''),
            "htmlblocks": await md2htmlblocks(content, cwd),
            }
        EVENT_LOOP.create_task(send_message_to_all_js_clients(message))


# send updated body contents to javascript clients
async def send_message_to_all_js_clients(message):
    """ send a message to all js clients

    Args:
        message: dict: the message to send

    """
    if JSCLIENTS:
        jsonmessage = json.dumps(message)
        for client in JSCLIENTS:
            EVENT_LOOP.create_task(client.send(jsonmessage))


def md2json(content):
    proc = subprocess.Popen(
        ["pandoc",
         "--from", "markdown+emoji", "--to", "json", "--"+ARGS.math],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL)
    stdout, stderr = proc.communicate(content.encode())
    return json.loads(stdout)


urlRegex = re.compile('(href|src)=[\'"](?!/|https://|http://|#)(.*)[\'"]')


@lru_cache(maxsize=LRU_CACHE_SIZE)
def json2htmlblock(jsontxt, cwd):
    proc = subprocess.Popen(
        ["pandoc",
         "--from", "json", "--to", "html5", "--"+ARGS.math],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL)
    stdout, stderr = proc.communicate(jsontxt.encode())
    html = urlRegex.sub(
        f'\\1="file://{cwd}\\2"',
        stdout.decode())
    return [hash(html), html]


async def jsonlist2htmlblocks(jsontxts, cwd):
    blocking_tasks = [
        EVENT_LOOP.run_in_executor(None, json2htmlblock, jsontxt, cwd)
        for jsontxt in jsontxts]
    return await asyncio.gather(*blocking_tasks)


async def md2htmlblocks(content, cwd) -> str:
    """ convert markdown to html using pandoc markdown

    Args:
        content: the markdown string to convert

    Returns:
        html: str: the resulting html

    """
    # pandoc fix: make % shown as a single % (in stead of stopping conversion)
    # TODO: ?
    content = content.replace("%", "%%")

    jsonout = await EVENT_LOOP.run_in_executor(
        None,
        md2json,
        content.replace('CuRsOr', ''))
    blocks = jsonout['blocks']

    cursorpos = None
    if 'CuRsOr' in content:
        cursorcut = await EVENT_LOOP.run_in_executor(
            None,
            md2json,
            content.split('CuRsOr')[0])
        cursorpos = max(0, len(cursorcut['blocks']) - 2)

    jsonlist = []
    for bid, b in enumerate(blocks):
        jsonout['blocks'] = [b]
        jsonstr = json.dumps(jsonout)
        jsonlist.append(jsonstr)
    htmlblocks = await jsonlist2htmlblocks(jsonlist, cwd)

    if cursorpos:
        htmlblocks.insert(cursorpos + 1, [hash(time.time()), ''])

    return htmlblocks
