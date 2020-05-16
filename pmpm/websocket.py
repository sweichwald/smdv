import asyncio
import concurrent.futures
from functools import lru_cache
import json
import os
from pathlib import Path
import re
import subprocess
import traceback
import websockets

from .utils import parse_args

LRU_CACHE_SIZE = 8192

JSCLIENTS = set()

EVENT_LOOP = asyncio.get_event_loop()

DISTRIBUTING = None
LATEST_META_CWD = None

NAMED_PIPE = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "pmpm_pipe"

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
        if DISTRIBUTING:
            DISTRIBUTING.cancel()
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
        DISTRIBUTING = EVENT_LOOP.create_task(distribute_new_content(
            fpath,
            content))


async def distribute_new_content(fpath, content):
    try:
        message = {
            "filepath": str(os.path.relpath(fpath, ARGS.home)),
            "htmlblocks": await md2htmlblocks(content, fpath.parent),
            }
    except concurrent.futures.CancelledError:
        return
    except Exception as e:
        message = {
            "error": str(e)
            }
        traceback.print_exc()
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
    with fpath.open('r') as f:
        content = f.read()
    return content


async def handle_message(client: websockets.WebSocketServerProtocol,
                         message: str):
    """ handle a message sent by one of the clients
    """
    global DISTRIBUTING

    if message.startswith('filepath:'):
        if DISTRIBUTING:
            DISTRIBUTING.cancel()
        fpath = ARGS.home / message[9:]
        try:
            content = await EVENT_LOOP.run_in_executor(None,
                                                    readfile,
                                                    fpath)
        except (FileNotFoundError, IsADirectoryError) as e:
            DISTRIBUTING = EVENT_LOOP.create_task(send_message_to_all_js_clients({
                "error": str(e)
                }))
            traceback.print_exc()
            return
        DISTRIBUTING = EVENT_LOOP.create_task(distribute_new_content(
            fpath,
            content))
    elif message.startswith('citeproc:') and LATEST_META_CWD:
        if DISTRIBUTING:
            DISTRIBUTING.cancel()
        DISTRIBUTING = EVENT_LOOP.create_task(citeproc(message[9:]))


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


def md2json(content, cwd):
    proc = subprocess.Popen(
        ["pandoc",
         "--from", "markdown+emoji",
         "--to", "json",
         "--"+ARGS.math],
        cwd=cwd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL)
    stdout, stderr = proc.communicate(content.encode())
    return json.loads(stdout)


urlRegex = re.compile('(href|src)=[\'"](?!/|https://|http://|#)(.*)[\'"]')


@lru_cache(maxsize=LRU_CACHE_SIZE)
def json2htmlblock(jsontxt, cwd, outtype):
    call = ["pandoc",
            "--from", "json", "--to", outtype, "--"+ARGS.math]
    proc = subprocess.Popen(
        call,
        cwd=cwd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL)
    stdout, stderr = proc.communicate(jsontxt.encode())
    html = urlRegex.sub(
        f'\\1="file://{cwd}/\\2" onclick="return localLinkClickEvent(this);"',
        stdout.decode())
    return [hash(html), html]


async def jsonlist2htmlblocks(jsontxts, cwd, outtype):
    blocking_tasks = [
        EVENT_LOOP.run_in_executor(None,
                                   json2htmlblock,
                                   jsontxt,
                                   cwd,
                                   outtype)
        for jsontxt in jsontxts]
    return await asyncio.gather(*blocking_tasks)


@lru_cache(maxsize=LRU_CACHE_SIZE)
def citeproc_cached(bibcontent, split_marker, cwd):
    proc = subprocess.Popen(
        ["pandoc",
            "--filter", "pandoc-citeproc",
            "--from", "markdown+emoji", "--to", "html5", "--"+ARGS.math],
        cwd=cwd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL)
    stdout, stderr = proc.communicate(bibcontent.encode())

    html = stdout.decode()
    if split_marker:
        html = html.split(split_marker)[1]

    return html

async def citeproc(citerequest):
    global LATEST_META_CWD

    meta, cwd = LATEST_META_CWD

    try:
        # req must be of the form
        # req = {
        #
        #    'textcites': ['[@item1]', '[@item1,@item2]'],
        #    'citekeys':  ['@item1', '@item2'],
        # }
        # assume both are ordered lists
        # if the latter is empty (or LATEST_META sets suppress-bibliography)
        # no bibliography will be sent
        req = json.loads(citerequest)
        bibfile = meta['bibliography']['c'][0]['c']
        linkcitations = meta['link-citations']['c']
        fakeTextcites = '\n\n'.join(req['textcites'])

        # TODO: More efficient with json input?
        if 'citekeys' in req:
            fakeCitekeys = '\n\n@'.join(req['citekeys'])
            bibcontent = ("---\n"
                        f"bibliography: {bibfile}\n"
                        f"link-citations: {linkcitations}\n"
                        "suppress-bibliography: false\n"
                        "---\n"
                        f"@{fakeCitekeys}\n\n"
                        "<!--CITEKEYSENDMARKER-->\n\n"
                        f"{fakeTextcites}")
            print(bibcontent)
        else:
            suppressbibliography = 'true';
            bibcontent = ("---\n"
                        f"bibliography: {bibfile}\n"
                        f"link-citations: {linkcitations}\n"
                        "suppress-bibliography: true\n"
                        "---\n"
                        f"{fakeTextcites}")
            print(bibcontent)
        message = citeproc_cached(
            bibcontent,
            '\n<!--CITEKEYSENDMARKER-->\n' if 'citekeys' in req else None,
            cwd)
    except concurrent.futures.CancelledError:
        return
    except Exception as e:
        message = {
            "error": str(e)
            }
        traceback.print_exc()
    # TODO: Multi-clients are problematic, each will send their own citeproc request.
    #       Send result just to the client who did the request?
    asyncio.shield(send_message_to_all_js_clients(message))

async def md2htmlblocks(content, cwd) -> str:
    """ convert markdown to html using pandoc markdown

    Args:
        content: the markdown string to convert

    Returns:
        html: str: the resulting html

    """
    global LATEST_META_CWD

    jsonout = await EVENT_LOOP.run_in_executor(
        None,
        md2json,
        content,
        cwd)
    blocks = jsonout['blocks']

    # FLR: md2json with `--filter pandoc-citeproc` is slooow
    # thus this workaround to speed things up
    LATEST_META_CWD = [jsonout['meta'], cwd]

    jsonlist = []
    for bid, b in enumerate(blocks):
        jsonout['blocks'] = [b]
        jsonstr = json.dumps(jsonout)
        jsonlist.append(jsonstr)

    outtype = "html5"
    if content.startswith("<!-- revealjs -->\n"):
        outtype = "revealjs"

    htmlblocks = await jsonlist2htmlblocks(jsonlist, cwd, outtype)

    return htmlblocks
