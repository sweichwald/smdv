import asyncio
import concurrent.futures
from functools import lru_cache
import json
import os
import re
import subprocess
import websockets

from .utils import parse_args

LRU_CACHE_SIZE = 8192

JSCLIENTS = set()

EVENT_LOOP = asyncio.get_event_loop()

DISTRIBUTING = None

NAMED_PIPE = os.environ.get("XDG_RUNTIME_DIR", "/tmp") + "/pmpm_pipe"
PIPE_LOST = asyncio.Event()


def run_websocket_server():
    """ start and run the websocket server """
    global ARGS
    ARGS = parse_args()
    EVENT_LOOP.set_default_executor(
        concurrent.futures.ThreadPoolExecutor(max_workers=None))
    WEBSOCKETS_SERVER = websockets.serve(serve_client,
                                         "localhost",
                                         ARGS.port)
    EVENT_LOOP.run_until_complete(WEBSOCKETS_SERVER)
    if not os.path.exists(NAMED_PIPE):
        os.mkfifo(NAMED_PIPE)
    EVENT_LOOP.create_task(monitorpipe())
    EVENT_LOOP.run_forever()


async def monitorpipe():
    EVENT_LOOP.create_task(
        EVENT_LOOP.connect_read_pipe(
            ReadPipeProtocol,
            os.fdopen(
                os.open(
                    NAMED_PIPE,
                    os.O_NONBLOCK | os.O_RDONLY),
                'rb')))
    await PIPE_LOST.wait()
    PIPE_LOST.clear()
    EVENT_LOOP.create_task(monitorpipe())


class ReadPipeProtocol(asyncio.Protocol):

    def __init__(self, *args, **kwargs):
        super(ReadPipeProtocol, self).__init__(*args, **kwargs)
        self._received = []

    def data_received(self, data):
        super(ReadPipeProtocol, self).data_received(data)
        self._received.append(data)
        if data.endswith(b'\0'):
            EVENT_LOOP.create_task(new_pipe_content(self._received))
            self._received = []

    def eof_received(self):
        EVENT_LOOP.create_task(new_pipe_content(self._received))

    def connection_lost(self, transport):
        super(ReadPipeProtocol, self).connection_lost(transport)
        PIPE_LOST.set()


async def new_pipe_content(instrlist):
    global DISTRIBUTING
    instr = b''.join(instrlist)
    if instr != b'':
        # filepath passed along
        content = instr.decode()
        if content.startswith('fpath:'):
            lines = content.split('\n')
            fpath = lines.pop(0)[6:]
            cwd = fpath.rsplit('/', 1)[0] + '/'
            content = '\n'.join(lines)
            fpath.replace(ARGS.home, '')
        else:
            fpath = "LIVE"
            cwd = ARGS.home + '/'
        if DISTRIBUTING:
            DISTRIBUTING.cancel()
        DISTRIBUTING = EVENT_LOOP.create_task(distribute_new_content(
            fpath,
            content,
            cwd))


async def distribute_new_content(fpath, content, cwd):
    message = {
        "fpath": fpath,
        "htmlblocks": await md2htmlblocks(content, cwd),
        }
    asyncio.shield(send_message_to_all_js_clients(message))


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
    global DISTRIBUTING
    fpath = message
    content = await EVENT_LOOP.run_in_executor(
        None, readfile, ARGS.home + fpath)
    if content:
        cwd = fpath.rsplit('/', 1)[0] + '/'
        fpath.replace(ARGS.home, '')
        if DISTRIBUTING:
            DISTRIBUTING.cancel()
        DISTRIBUTING = EVENT_LOOP.create_task(distribute_new_content(
            fpath,
            content,
            cwd))


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
def json2htmlblock(jsontxt, cwd, citeproc):
    call = ["pandoc",
            "--from", "json", "--to", "html5", "--"+ARGS.math]
    if citeproc:
        call.extend(["--filter", "pandoc-citeproc"])
    proc = subprocess.Popen(
        call,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL)
    stdout, stderr = proc.communicate(jsontxt.encode())
    html = urlRegex.sub(
        f'\\1="file://{cwd}\\2"',
        stdout.decode())
    return [hash(html), html]


async def jsonlist2htmlblocks(jsontxts, cwd, citeproc):
    blocking_tasks = [
        EVENT_LOOP.run_in_executor(None,
                                   json2htmlblock,
                                   jsontxt,
                                   cwd,
                                   citeproc)
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
        content)

    citeproc = 'bibliography' in jsonout['meta']

    blocks = jsonout['blocks']

    jsonlist = []
    for bid, b in enumerate(blocks):
        jsonout['blocks'] = [b]
        jsonstr = json.dumps(jsonout)
        jsonlist.append(jsonstr)

    htmlblocks = await jsonlist2htmlblocks(jsonlist, cwd, citeproc)

    return htmlblocks
