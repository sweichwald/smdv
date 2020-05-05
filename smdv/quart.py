import json
import os

from .utils import limport, parse_args, BASE_DIR

# import quart and websockets lazily
quart = limport('quart')
websockets = limport('websockets')


def run_quart_server():
    global ARGS
    ARGS = parse_args()
    """ start the quart server """
    create_app().run(
        debug=False, port=ARGS.port, host="localhost")


def create_app():
    """ quart app factory

    Returns:
        app: the quart app

    """
    app = quart.Quart(
        __name__, static_folder=ARGS.home, static_url_path="/@static")

    # index route for the smdv app
    @app.route("/", methods=["GET", "DELETE"])
    @app.route("/<path:path>/", methods=["GET"])
    async def index(path: str = "") -> str:
        """ the main (index) route of smdv

        Returns:
            html: the html representation of the requested path
        """
        if quart.request.method == "GET":
            try:
                cwd, filename = change_current_working_directory(path)
            except FileNotFoundError:
                return quart.abort(404)

            html = open(f'{BASE_DIR}/smdv.html', 'r').read()
            replacements = {
                '{SMDV-home-SMDV}': ARGS.home,
                '{SMDV-css-SMDV}': open(ARGS.css, 'r').read(),
                '{SMDV-port-SMDV}': ARGS.websocket_port,
            }
            for k, v in replacements.items():
                html = html.replace(k, v)

            if path.endswith("live_put") or path.endswith("live_put/"):
                return html

            if filename:
                if is_binary_file(filename):
                    return quart.redirect(
                        quart.url_for("static", filename=path))
                with open(filename, "r") as file:
                    await send_as_pyclient_async(
                        {
                            "func": "file",
                            "cwd": cwd,
                            "cwdEncoded": False,
                            "cwdBody": "",
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
            await send_as_pyclient_async(
                {
                    "func": "dir",
                    "cwd": cwd,
                    "cwdEncoded": False,
                    "cwdBody": "",
                    "filename": filename,
                    "fileBody": "",
                    "fileCwd": cwd,
                    "fileOpen": False,
                    "fileEncoding": "",
                    "fileEncoded": False,
                }
            )
            return html

        if quart.request.method == "DELETE":
            # TODO
            exit()

        # should never get here:
        return "failed.\n"

    return app


async def send_as_pyclient_async(message: dict):
    """ send a message to the smdv server as the python client

    Args:
        message: the message to send (in dictionary format)
    """
    message["client"] = "py"
    async with websockets.connect(
        f"ws://localhost:{ARGS.websocket_port}"
    ) as websocket:
        await websocket.send(json.dumps(message))


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
            and filename not in ["live_put"]):
        raise FileNotFoundError(f"Could not find file {fullpath}")
    if cwd != dirpath:
        os.chdir(dirpath)
    cwd = os.path.abspath(os.getcwd()) + "/"
    cwd = cwd[len(ARGS.home):]
    return cwd, filename
