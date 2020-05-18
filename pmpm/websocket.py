"""
run_websocket_server():
    entry point, mkfifo, start websocket server and monitorpipe
monitorpipe():
    connects read NAMED_PIPE, reconnects upon PIPE_LOST event
ReadPipeProtocol:
    buffers piped in content,
    queues and triggers processqueue when eof or \0 received,
    PIPE_LOST on connection_lost
progressbar
processqueue:
    processes queue when triggered and not yet PROCESSING
    --> new_pipe_content or new_filepath_request
new_pipe_content:
    decodes input, resolves filepath if given
    --> process_new_content
new_filepath_request:
    retrieves file
    --> process_new_content
process_new_content:
    compiles message to distribute to JSCLIENTS;
serve_client / register_client / unregister_client:
    handles JSCLIENTS
    --> handle_message
readfile
handle_message:
    JSCLIENTS send either
        filepath request: queue and trigger processqueue
    or
        citeproc: trigger citeproc
send_message_to_all_js_clients
citeproc:
    `--filter pandoc-citeproc` is sloow,
    thus JSCLIENTS request bibliographic information only when needed,
    which is responded to by citeproc
md2json
json2htmlblock:
    alru_cached block-wise conversion,
    relative links are rewritten as file:// links,
    onclick event allows pmpm.js to load .md links in pmpm
md2htmlblocks:
    --> md2json
    CACHE.json and cwd (for citeproc)
    --> json2htmlblock (asynchronously)
"""


import asyncio
from async_lru import alru_cache
from collections import namedtuple
from itertools import count
import json
import os
from pathlib import Path
import re
import subprocess
import traceback
import uvloop
import websockets
from .utils import citeblock_generator, parse_args


LRU_CACHE_SIZE = 8192

JSCLIENTS = set()

asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
EVENT_LOOP = asyncio.get_event_loop()

CACHE = namedtuple('CACHE', ['cwd', 'json'])

QUEUE = None
PROCESSING = False

NAMED_PIPE = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "pmpm_pipe"
PIPE_LOST = asyncio.Event()


def run_websocket_server():
    """ start and run the websocket server """
    global ARGS
    ARGS = parse_args()
    WEBSOCKETS_SERVER = websockets.serve(serve_client,
                                         "localhost",
                                         ARGS.port)
    EVENT_LOOP.run_until_complete(WEBSOCKETS_SERVER)
    if not NAMED_PIPE.is_fifo():
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
            self._queue()

    def eof_received(self):
        self._queue()

    def _queue(self):
        global QUEUE
        QUEUE = ('pipe', self._received)
        EVENT_LOOP.create_task(processqueue())
        self._received = []

    def connection_lost(self, transport):
        super(ReadPipeProtocol, self).connection_lost(transport)
        PIPE_LOST.set()


async def progressbar():
    for k in count(1):
        await asyncio.sleep(.382)
        EVENT_LOOP.create_task(
            send_message_to_all_js_clients(
                {
                    "status": ' · '*k
                    }))


async def processqueue():
    global PROCESSING
    global QUEUE
    if not PROCESSING and QUEUE:
        try:
            PROCESSING = EVENT_LOOP.create_task(progressbar())
            q = QUEUE
            QUEUE = None
            if q[0] == 'pipe':
                await new_pipe_content(q[1])
            elif q[0] == 'filepath':
                await new_filepath_request(q[1])
        except Exception as e:
            message = {
                "error": str(e)
                }
            traceback.print_exc()
            EVENT_LOOP.create_task(send_message_to_all_js_clients(message))
        finally:
            PROCESSING.cancel()
            await asyncio.sleep(.382)
            PROCESSING = False
            EVENT_LOOP.create_task(processqueue())


async def new_pipe_content(instrlist):
    instr = b''.join(instrlist)
    # filepath passed along
    content = instr.decode()
    if content.startswith('<!-- filepath:'):
        lines = content.split('\n')
        # given path is relative to home or absolute
        fpath = ARGS.home / lines.pop(0)[14:-4]
        content = '\n'.join(lines)
    else:
        fpath = ARGS.home / "LIVE"
    # absolute fpath
    fpath = fpath.resolve()
    await process_new_content(fpath, content)


async def new_filepath_request(fpath):
    content = await EVENT_LOOP.run_in_executor(None,
                                               readfile,
                                               fpath)
    await process_new_content(fpath, content)


async def process_new_content(fpath, content):
    message = {
        "filepath": str(fpath.relative_to(ARGS.home)),
        "htmlblocks": await md2htmlblocks(content, fpath.parent),
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
    with fpath.open('r') as f:
        content = f.read()
    return content


async def handle_message(client: websockets.WebSocketServerProtocol,
                         message: str):
    """ handle a message sent by one of the clients
    """
    if message.startswith('filepath:'):
        global QUEUE
        QUEUE = ('filepath', ARGS.home / message[9:])
        EVENT_LOOP.create_task(processqueue())
    elif message.startswith('citeproc'):
        EVENT_LOOP.run_in_executor(None,
                                   citeproc,
                                   client)


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


# FLR: md2json with `--filter pandoc-citeproc` is slooow
# thus this workaround to speed things up
def citeproc(client=None):
    # TODO: obviously need to speed up (lru_cache)
    #       check for timestamp of involved bibfiles for lru_cache hashes
    jsonf = CACHE.json
    jsonf['blocks'] = list(citeblock_generator(CACHE.json['blocks'], 'Cite'))
    call = ["pandoc",
            "--from", "json", "--to", "html5",
            "--filter", "pandoc-citeproc",
            "--"+ARGS.math]
    proc = subprocess.Popen(
        call,
        cwd=CACHE.cwd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL)
    stdout, stderr = proc.communicate(json.dumps(jsonf).encode())
    if client:
        EVENT_LOOP.create_task(client.send(json.dumps(stdout.decode())))
    else:
        EVENT_LOOP.create_task(send_message_to_all_js_clients(stdout.decode()))


async def md2json(content, cwd):
    proc = await asyncio.subprocess.create_subprocess_exec(
        "pandoc",
        "--from", "markdown+emoji",
        "--to", "json",
        "--"+ARGS.math,
        cwd=cwd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL)
    stdout, stderr = await proc.communicate(content.encode())
    return json.loads(stdout)


urlRegex = re.compile('(href|src)=[\'"](?!/|https://|http://|#)(.*)[\'"]')


@alru_cache(maxsize=LRU_CACHE_SIZE)
async def json2htmlblock(jsontxt, cwd, outtype):
    proc = await asyncio.subprocess.create_subprocess_exec(
        "pandoc",
        "--from", "json",
        "--to", outtype,
        "--"+ARGS.math,
        cwd=cwd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL)
    stdout, stderr = await proc.communicate(jsontxt.encode())
    html = urlRegex.sub(
        f'\\1="file://{cwd}/\\2" onclick="return localLinkClickEvent(this);"',
        stdout.decode())
    return [hash(html), html]


async def md2htmlblocks(content, cwd) -> str:
    """ convert markdown to html using pandoc markdown

    Args:
        content: the markdown string to convert

    Returns:
        html: str: the resulting html

    """
    global CACHE

    outtype = "html5"
    if content.startswith("<!-- revealjs -->\n"):
        content = content[18:]
        outtype = "revealjs"

    jsonout = await md2json(content, cwd)

    CACHE.cwd = cwd
    CACHE.json = jsonout

    jsonlist = (
        json.dumps({"blocks": [j],
                    "meta": {},
                    "pandoc-api-version": jsonout['pandoc-api-version']})
        for j in jsonout['blocks'])

    htmlblocks = [await json2htmlblock(j, cwd, outtype)
                  for j in jsonlist]

    return htmlblocks
