import asyncio
from async_lru import alru_cache
import collections
import json
import os
import re
import websockets

from .utils import parse_args


N_JOBS_PANDOC = 10
SEM = asyncio.Semaphore(N_JOBS_PANDOC)


JSCLIENTS = set()  # jsclients wait for an update from the pyclient
BACKMESSAGES = collections.deque()  # for communication between js and py
FORWARDMESSAGES = collections.deque()  # for communication between js and py
MESSAGE = {}
EVENT_LOOP = asyncio.get_event_loop()
NAMED_PIPE = os.environ.get("XDG_RUNTIME_DIR", "/tmp") + "/smdv_pipe"


def run_websocket_server():
    """ start and run the websocket server """
    global ARGS
    ARGS = parse_args()
    WEBSOCKETS_SERVER = websockets.serve(serve_client,
                                         "localhost",
                                         ARGS.port)
    EVENT_LOOP.run_until_complete(asyncio.gather(
        WEBSOCKETS_SERVER,
        asyncio.start_unix_server(piper, NAMED_PIPE)
        ))
    EVENT_LOOP.run_forever()


async def piper(a, b):
    instr = await a.read(-1)
    if instr != b'':
        # filepath passed along
        content = instr.decode()
        if len(content) > 6 and content[:6] == 'fpath:':
            lines = content.split('\n')
            content = '\n'.join(lines[1:])
            fpath = lines[0][6:]
            cwd = fpath.rsplit('/', 1)[0] + '/'
        else:
            fpath = "LIVE"
            cwd = ARGS.home + '/'
        message = {
            "fpath": fpath.replace(ARGS.home, ''),
            "htmlblocks": await md2htmlblocks(content, cwd),
            }
        await send_message_to_all_js_clients(message)


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
    JSCLIENTS.add(client)
    await handle_message(client, message)


async def unregister_client(client: websockets.WebSocketServerProtocol):
    """ unregister a client

    Args:
        client: the client (websocket) to unregister.

    """
    if client in JSCLIENTS:
        JSCLIENTS.remove(client)


async def handle_message(client: websockets.WebSocketServerProtocol,
                         message: str):
    """ handle a message sent by one of the clients
    """
    try:
        fpath = ARGS.home + message
        with open(fpath, 'r') as f:
            content = f.read()
    except (FileNotFoundError, IsADirectoryError):
        return
    if content:
        cwd = fpath.rsplit('/', 1)[0] + '/'
        message = {
            "fpath": fpath.replace(ARGS.home, ''),
            "htmlblocks": await md2htmlblocks(content, cwd),
            }
        await send_message_to_all_js_clients(message)


# send updated body contents to javascript clients
async def send_message_to_all_js_clients(message):
    """ send a message to all js clients

    Args:
        message: dict: the message to send

    """
    if JSCLIENTS:
        jsonmessage = json.dumps(message)
        # TODO
        await asyncio.wait(
            [client.send(jsonmessage) for client in JSCLIENTS])


async def md2json(content):
    proc = await asyncio.create_subprocess_exec(
        "pandoc",
        "--from", "markdown+emoji", "--to", "json", "--"+ARGS.math,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE)
    stdout, stderr = await proc.communicate(content.encode())
    return json.loads(stdout)


async def json2html(jsontxt):
    proc = await asyncio.create_subprocess_exec(
        "pandoc",
        "--from", "json", "--to", "html5", "--"+ARGS.math,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE)
    stdout, stderr = await proc.communicate(jsontxt.encode())
    return stdout.decode()


@alru_cache(maxsize=1000)
async def json2html_safe(jsontxt):
    async with SEM:
        return await json2html(jsontxt)


async def jsonlist2html(jsontxts):
    return await asyncio.gather(*(
        asyncio.ensure_future(json2html_safe(block))
        for block in jsontxts))


urlRegex = re.compile('(href|src)=[\'"](?!/|https://|http://|#)(.*)[\'"]')


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

    jsonout = await md2json(content)
    blocks = jsonout['blocks']

    marker = '<a name="#marker" id="marker"></a>'
    markertag = '<a name=\\"#marker\\" id=\\"marker\\"></a>'
    markerpos = None

    jsonlist = []
    for bid, b in enumerate(blocks):
        jsonout['blocks'] = [b]
        jsonstr = json.dumps(jsonout)
        if jsonstr.find(markertag) >= 0:
            jsonstr = jsonstr.replace(markertag, '')
            markerpos = bid
        jsonlist.append(jsonstr)
    htmls = [
        urlRegex.sub(
            f'\\1="file://{cwd}\\2"',
            html)
        for html in await jsonlist2html(jsonlist)]

    htmlblocks = [[hash(html), html] for html in htmls]
    if markerpos:
        htmlblocks.insert(markerpos, [hash(marker), marker])

    return htmlblocks
