"""
Command line utilities.
"""
import argparse
import os
import pathlib
import signal
import sys

import xarray as xr
from dask.diagnostics import ProgressBar

format_plugins = []


# TODO should we use attrs for this sort of stuff?
class FormatPlugin:
    """
    Encapsulates the necessary information for a format plugin to be
    used in sgkit.
    """

    def __init__(
        self,
        format_name,
        import_func=None,
        import_args=None,
        export_func=None,
        export_args=None,
        sniff_func=None,
    ):
        self.format_name = format_name
        self.import_func = import_func
        self.import_args = import_args
        self.export_func = export_func
        self.export_args = export_args
        self.sniff_func = sniff_func


try:
    import sgkit_plink  # NOQA

    # TODO if we agree on this interface, then the data format module
    # would agree to implement a function that returns this information,
    # so we'd do something like:
    # format_plugins.append(sgkit_plink.get_format_plugin())

    # For now:
    format_plugins.append(
        FormatPlugin(
            format_name="plink",
            import_func=sgkit_plink.read_plink,
            import_args=[
                # TODO we'd have another simple dataclass for this.
                ("bim_sep", "\t", "Separator used when parsing BIM files"),
                ("fam_sep", "\t", "Separator used when parsing FAM files"),
            ],
        )
    )

except ImportError:
    # TODO logging.info("plink module not found")
    pass

# from . import read_plink


def set_sigpipe_handler():
    if os.name == "posix":
        # Set signal handler for SIGPIPE to quietly kill the program.
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)


# This function is useful when we're testing as it avoids mocking
# sys.exit, which can be tricky.
def sys_exit(message):
    sys.exit(message)


def load_dataset(path):
    """
    Attempt to load an sgkit dataset from the specified path, or
    fail with a meaningful error message.
    """
    # We need to do this because the xr.open_zarr function doesn't
    # give very good error messages.
    path = pathlib.Path(path)
    if not path.exists():
        sys_exit(f"Path {path} does not exist")
    try:
        # We need to convert back to a string because xarray doesn't
        # support pathlib.
        return xr.open_zarr(str(path))
    except ValueError as ve:
        sys_exit(f"Error opening dataset {path}: {ve}")


def run_list(args):
    ds = load_dataset(args.sgkit_dataset)
    # TODO do something more sophisticated.
    print(ds)


def add_import_command(subparsers, plugin):

    parser = subparsers.add_parser(
        f"import-{plugin.format_name}",
        help=f"Convert data in {plugin.format_name} to sgkit",
    )
    parser.add_argument("input", help="The input data in {plugin.format_name} format")
    parser.add_argument("output", help="The path to store the converted dataset")
    for name, default, help_text in plugin.import_args:
        # TODO might be nice to define short args form as well.
        parser.add_argument(f"--{name}", default=default, help=help_text)

    def run(args):

        # TODO progress bar here - there will be formats where this
        # is a lot of work.
        # Yah, we need a dataclass for args all right, this is horrible!
        import_args = {name: getattr(args, name) for name, _, _ in plugin.import_args}
        ds = plugin.import_func(args.input, **import_args)
        # TODO progress bar here
        ds.to_zarr(args.output, mode="w")

    parser.set_defaults(runner=run)


def add_sgkit_dataset_argument(parser):
    parser.add_argument("sgkit_dataset", help="The path for an sgkit dataset")


def add_list_arguments(parser):
    add_sgkit_dataset_argument(parser)
    # TODO add arguments like --long, --human, etc.


def get_sgkit_parser():
    top_parser = argparse.ArgumentParser(
        description=("Utilities for manipulating sgkit datasets")
    )
    subparsers = top_parser.add_subparsers(dest="subcommand")
    subparsers.required = True

    parser = subparsers.add_parser(
        "list", aliases=["ls"], help="List the arrays stored in a dataset"
    )
    parser.set_defaults(runner=run_list)
    add_list_arguments(parser)

    for plugin in format_plugins:
        if plugin.import_func is not None:
            add_import_command(subparsers, plugin)
        # Similarly for export

    return top_parser


def sgkit_main(arg_list=None):
    """
    Top-level hook called when running python -m sgkit.
    """
    parser = get_sgkit_parser()
    set_sigpipe_handler()
    args = parser.parse_args(arg_list)
    args.runner(args)
