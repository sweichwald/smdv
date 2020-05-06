import argparse
import importlib
import os
import sys


BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class limport:

    def __init__(self, package):
        self._package = package

    def __getattr__(self, get):
        if isinstance(self._package, str):
            self._package = importlib.import_module(self._package)
        return getattr(self._package, get)


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
        help="file to open with smdv",
    )
    parser.add_argument(
        "-H",
        "--home",
        default=os.environ.get("SMDV_DEFAULT_HOME", os.path.expanduser("~")),
        help="set the root folder of the smdv server",
    )
    parser.add_argument(
        "-w",
        "--port",
        default=os.environ.get("SMDV_DEFAULT_PORT", "9877"),
        help="port for websocket communication",
    )
    parser.add_argument(
        "--math",
        default="mathml",
        choices=["mathml", "katex"],
        help="whether to use pandoc's mathml or katex math mode",
    )
    single_shot_arguments = parser.add_mutually_exclusive_group()
    single_shot_arguments.add_argument(
        "--status",
        action="store_true",
        default=os.environ.get("SMDV_DEFAULT_SERVER_STATUS", False),
        help="ask status of the smdv server",
    )
    single_shot_arguments.add_argument(
        "--start",
        action="store_true",
        default=os.environ.get("SMDV_DEFAULT_START_SERVER", False),
        help="start the smdv server (without doing anything else)",
    )
    single_shot_arguments.add_argument(
        "--stop",
        action="store_true",
        default=os.environ.get("SMDV_DEFAULT_STOP_SERVER", False),
        help="stop the smdv server (without doing anything else)",
    )
    parsed_args = parser.parse_args(args=args)
    if parsed_args.home.endswith("/"):
        parsed_args.home = parsed_args.home[:-1]
    if not os.path.isdir(parsed_args.home):
        raise ValueError(
            f"invalid home location given from smdv: {parsed_args.home}")
    return parsed_args
