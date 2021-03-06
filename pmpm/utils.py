import argparse
import importlib
import os
from pathlib import Path


BASE_DIR = Path(__file__).parent


class limport:

    def __init__(self, package):
        self._package = package

    def __getattr__(self, get):
        if isinstance(self._package, str):
            self._package = importlib.import_module(self._package)
        return getattr(self._package, get)


def parse_args(args=None, websocket=False) -> argparse.Namespace:
    """ populate the pmpm command line arguments

    Args:
        args: the arguments to parse

    Returns:
        parsed_args: the parsed arguments

    """
    # Argument parser
    parser = argparse.ArgumentParser(
        description=("pmpm: pandoc markdown preview machine, "
                     "a simple markdown previewer"))
    parser.add_argument(
        "-H",
        "--home",
        default=os.environ.get("PMPM_DEFAULT_HOME", "~"),
        help="set the root folder of the pmpm server",
    )
    parser.add_argument(
        "-p",
        "--port",
        default=os.environ.get("PMPM_DEFAULT_PORT", "9877"),
        help="port for websocket communication",
    )
    parser.add_argument(
        "--math",
        default="mathml",
        choices=["mathml", "katex"],
        help="whether to use pandoc's mathml or katex math mode",
    )
    if not websocket:
        single_shot_arguments = parser.add_mutually_exclusive_group()
        single_shot_arguments.add_argument(
            "--status",
            action="store_true",
            default=os.environ.get("PMPM_DEFAULT_SERVER_STATUS", False),
            help="ask status of the pmpm server",
        )
        single_shot_arguments.add_argument(
            "--start",
            action="store_true",
            default=os.environ.get("PMPM_DEFAULT_START_SERVER", False),
            help="start the pmpm server (without doing anything else)",
        )
        single_shot_arguments.add_argument(
            "--stop",
            action="store_true",
            default=os.environ.get("PMPM_DEFAULT_STOP_SERVER", False),
            help="stop the pmpm server (without doing anything else)",
        )
    parsed_args = parser.parse_args(args=args)
    parsed_args.home = Path(parsed_args.home).expanduser().resolve()
    if not parsed_args.home.is_dir():
        raise ValueError(
            f"invalid home location given from pmpm: {parsed_args.home}")
    return parsed_args


def citeblock_generator(json_input, lookup_key):
    if isinstance(json_input, dict):
        if json_input.get("t", False) == "Cite":
            yield {"t": "Para", "c": [json_input]}
        else:
            for k, v in json_input.items():
                yield from citeblock_generator(v, lookup_key)
    elif isinstance(json_input, list):
        for item in json_input:
            yield from citeblock_generator(item, lookup_key)
