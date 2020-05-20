"""
run_websocket_server():
    entry point, mkfifo, start websocket server and monitorpipe
monitorpipe():
    connects read NAMED_PIPE, reconnects upon PIPE_LOST event
ReadPipeProtocol:
    buffers piped in content,
    queues and triggers processqueue when eof or \0 received,
    PIPE_LOST event on connection_lost
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
    which is responded to by citeproc,
    or citeproc is triggered upon changed bibinfo to distribute
    new bibdetails to all clients
citeproc_sub:
    cached subprocess pandoc call
uniqueciteprocdict
md2json
json2htmlblock:
    alru_cached block-wise conversion,
    relative links are rewritten as file:// links,
    onclick event allows pmpm.js to load .md links in pmpm
md2htmlblocks:
    --> md2json
    BIBQUEUE = (uniqueciteprocdict, hash, cwd) for citeproc
    --> json2htmlblock (asynchronously)
"""


import asyncio
from async_lru import alru_cache
import concurrent.futures
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

QUEUE = None
PROCESSING = False

BIBQUEUE = None
BIBPROCESSING = False
LASTBIB = None

NAMED_PIPE = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "pmpm_pipe"
PIPE_LOST = asyncio.Event()


def run_websocket_server():
    """ start and run the websocket server """
    global ARGS
    ARGS = parse_args()
    EVENT_LOOP.set_default_executor(
        concurrent.futures.ProcessPoolExecutor(max_workers=None))
    WEBSOCKETS_SERVER = websockets.serve(serve_client,
                                         "localhost",
                                         ARGS.port)
    EVENT_LOOP.run_until_complete(WEBSOCKETS_SERVER)
    if not NAMED_PIPE.is_fifo():
        os.mkfifo(NAMED_PIPE)
    EVENT_LOOP.create_task(monitorpipe())
    EVENT_LOOP.create_task(citeproc())
    EVENT_LOOP.run_forever()


async def monitorpipe():
    EVENT_LOOP.create_task(EVENT_LOOP.connect_read_pipe(
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
        self._received = []

    def data_received(self, data):
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
        PIPE_LOST.set()


async def progressbar():
    for k in count(1):
        await asyncio.sleep(.382)
        EVENT_LOOP.create_task(
            send_message_to_all_js_clients(
                {"status": ' 🞄 '*k}))


async def processqueue():
    global PROCESSING
    global QUEUE
    if not PROCESSING and QUEUE:
        try:
            PROCESSING = EVENT_LOOP.create_task(progressbar())
            q, QUEUE = QUEUE, None
            if q[0] == 'pipe':
                await new_pipe_content(q[1])
            # assume it can only be a filepath request then
            else:
                await new_filepath_request(q[1])
        except Exception as e:
            message = {"error": str(e)}
            traceback.print_exc()
            EVENT_LOOP.create_task(send_message_to_all_js_clients(message))
        finally:
            PROCESSING.cancel()
            await asyncio.sleep(.382)
            PROCESSING = False
            EVENT_LOOP.create_task(processqueue())


async def new_pipe_content(instrlist):
    instr = b''.join(instrlist)
    content = instr.decode()
    # filepath passed along
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
    htmlblocks, supbib, refsectit, bibid = await md2htmlblocks(content,
                                                               fpath.parent)
    message = {
        "filepath": str(fpath.relative_to(ARGS.home)),
        "htmlblocks": htmlblocks,
        "suppress-bibliography": supbib,
        "reference-section-title": refsectit,
        "bibid": bibid,
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
            EVENT_LOOP.create_task(handle_message(client, message))
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
    # assume it can only be a citeproc request then
    else:
        EVENT_LOOP.create_task(citeproc())


async def send_message_to_all_js_clients(message):
    """ send updated body contents to javascript clients

    Args:
        message: dict: the message to send

    """
    if JSCLIENTS:
        jsonmessage = json.dumps(message)
        for client in JSCLIENTS:
            EVENT_LOOP.create_task(client.send(jsonmessage))


async def citeproc():
    global BIBPROCESSING
    global BIBQUEUE
    if not BIBPROCESSING and BIBQUEUE:
        try:
            q, BIBQUEUE, BIBPROCESSING = BIBQUEUE, None, True
            citehtml = await EVENT_LOOP.create_task(citeproc_sub(*q))
            EVENT_LOOP.create_task(
                send_message_to_all_js_clients({'html': citehtml,
                                                'bibid': q[1]}))
        finally:
            BIBPROCESSING = False
        EVENT_LOOP.create_task(citeproc())


@alru_cache(maxsize=LRU_CACHE_SIZE)
async def citeproc_sub(jsondump, bibid, cwd):
    if jsondump and bibid:
        call = ["pandoc",
                "--from", "json", "--to", "html5",
                "--filter", "pandoc-citeproc",
                "--"+ARGS.math]
        proc = await asyncio.subprocess.create_subprocess_exec(
            *call,
            cwd=cwd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL)
        stdout, stderr = await proc.communicate(jsondump.encode())
        return stdout.decode()
    return None


async def uniqueciteprocdict(jsondict, cwd):
    # keep only the blocks and bib-relevant metadata
    metakeys = {'bibliography',
                'csl',
                'link-citations',
                'nocite',
                'references'}
    bibinfo = {'pandoc-api-version': jsondict['pandoc-api-version']}
    bibinfo['meta'] = {k: jsondict['meta'][k]
                       for k in jsondict['meta'].keys() & metakeys}
    # copy citeblocks only
    bibinfo['blocks'] = list(
        citeblock_generator(jsondict['blocks'], 'Cite'))

    # no bibliography or bibentries given
    if not bibinfo['meta']:
        return (None, None)

    # add bibliography_mtimes_ to uniqueify
    bibliography = bibinfo['meta'].get('bibliography', None)
    if bibliography:
        if bibliography['t'] == 'MetaInlines':
            bibfiles = [cwd / bibliography['c'][0]['c']]
        else:
            bibfiles = [cwd / b['c'][0]['c']
                        for b in bibliography['c']]
        bibinfo['bibliography_mtimes_'] = [b.stat().st_mtime
                                           for b in bibfiles]

    # add csl_mtime_ to uniqueify
    try:
        bibinfo['csl_mtime_'] = (
            cwd / bibinfo['meta']['csl']['c'][0]['c']
            ).stat().st_mtime
    except (FileNotFoundError, IndexError, KeyError, TypeError):
        pass

    info = json.dumps(bibinfo)
    return info, hash(info)


@alru_cache(maxsize=LRU_CACHE_SIZE)
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
    return json.loads(stdout.decode())


@alru_cache(maxsize=LRU_CACHE_SIZE)
async def json2htmlblock(jsontxt, cwd, outtype):
    return await EVENT_LOOP.run_in_executor(
        None, json2htmlblock_sub, jsontxt, cwd, outtype)


urlRegex = re.compile('(href|src)=[\'"](?!/|https://|http://|#)(.*)[\'"]')


def json2htmlblock_sub(jsontxt, cwd, outtype):
    proc = subprocess.Popen(
        ["pandoc",
         "--from", "json",
         "--to", outtype,
         "--"+ARGS.math],
        cwd=cwd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL)
    stdout, stderr = proc.communicate(jsontxt.encode())
    html = urlRegex.sub(
        f'\\1="file://{cwd}/\\2" onclick="return localLinkClickEvent(this);"',
        stdout.decode())
    return [hash(html), html]


# do not cache --> checkforbibdifferences
async def md2htmlblocks(content, cwd):
    """ convert markdown to html using pandoc markdown

    Args:
        content: the markdown string to convert

    Returns:
        html: str: the resulting html

    """
    outtype = "html5"
    if content.startswith("<!-- revealjs -->\n"):
        content = content[18:]
        outtype = "revealjs"

    jsonout = await EVENT_LOOP.create_task(md2json(content, cwd))

    global BIBQUEUE
    BIBQUEUE = *(await uniqueciteprocdict(jsonout, cwd)), cwd
    bibid = BIBQUEUE[1]
    EVENT_LOOP.create_task(citeproc())

    jsonlist = (
        json.dumps({"blocks": [j],
                    "meta": {},
                    "pandoc-api-version": jsonout['pandoc-api-version']})
        for j in jsonout['blocks'])

    htmlblocks = await asyncio.gather(*(
        json2htmlblock(j, cwd, outtype)
        for j in jsonlist))

    try:
        supbib = jsonout['meta']['suppress-bibliography']['c'] is True
    except KeyError:
        supbib = False

    try:
        refsectit = jsonout['meta']['reference-section-title']['c'][0]['c']
    except (IndexError, KeyError):
        refsectit = ''

    return (htmlblocks,
            supbib,
            refsectit,
            bibid)
