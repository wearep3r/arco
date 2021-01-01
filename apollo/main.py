#!/usr/bin/env python3

import typer
import os
import subprocess
import json
import sys
import re
import anyconfig
from pathlib import Path
from read_version import read_version
from typing import Optional, List
import namesgenerator
from dotenv import load_dotenv
import pyperclip
import jinja2
import tempfile
from loguru import logger
import pwd
import functools
import platform
import zlib
import base64
import fsutil
from benedict import benedict

APP_NAME = "apollo"
app_dir = typer.get_app_dir(APP_NAME)


if not os.path.exists(app_dir):
    os.mkdir(app_dir)
    logger.debug(f"Created config directory at {app_dir}")


logger_config = {
    "handlers": [
        {
            "sink": sys.stdout,
            "format": "<green>{time:YYYY-MM-DD HH:mm:ss}</green> - <lvl>{level}</lvl> - <lvl>{message}</lvl>",
            "filter": lambda record: "history" not in record["extra"],
            "level": "WARNING",
        },
        # {
        #     "sink": os.path.join(app_dir, "history.json"),
        #     "serialize": True,
        #     "format": "{message}",
        #     "filter": lambda record: record["extra"].get("history")
        #     and record["extra"]["history"],
        # },
    ],
}


# @logger.catch()
# def arcolog(*, entry=False, exit=True, level="INFO"):
#     def wrapper(func):
#         name = func.__name__

#         @functools.wraps(func)
#         def wrapped(*args, **kwargs):
#             cli_context = arc["arco"]["cli_context"]
#             result = func(*args, **kwargs)

#             extra = {
#                 "history": True,
#                 "runtime": arc["arco"],
#                 "successful": False,
#                 "result": None,
#             }

#             if result:
#                 extra["successful"] = True
#                 extra["result"] = result

#             logger_ = logger.opt(depth=1).bind(**extra)

#             full_command = [cli_context["info_name"]]
#             full_command = [cli_context["info_name"]] + sys.argv[1:]

#             return result

#         return wrapped

#     return wrapper


# def wrapped(*args, **kwargs):
#     start = time.time()
#     result = func(*args, **kwargs)
#     end = time.time()
#     logger.info("Function '{}' executed in {:f} s", func.__name__, end - start)
#     return result

# return wrapped

arc = benedict(
    {
        "arco": {
            "app_dir": app_dir,
            "user": pwd.getpwuid(os.getuid()).pw_name,
            "version": read_version(str(Path(__file__).parent / "__init__.py")),
            "cwd": os.getcwd(),
            "hostname": platform.node(),
            "platform": platform.platform(),
            "platform_short": platform.platform(terse=True),
            "platform_system": platform.system(),
            "platform_version": platform.version(),
            "platform_release": platform.release(),
            "platform_machine": platform.machine(),
            "platform_processor": platform.processor(),
            "platform_architecture": str(platform.architecture()),
            "verbosity": 0,
            "context_dir": os.getcwd(),
            "code_dir": os.getcwd(),
        },
        "k8s": {
            "kubeconfig": os.path.join(os.path.expanduser("~"), ".kube", "config"),
            "auth": {"api_key": os.path.join(os.path.expanduser("~"), ".kube", "config")},
        },
        "helm": {
            "debug": False,
        },
        "kubeconfig": os.path.join(os.path.expanduser("~"), ".kube", "config"),
        "better_exceptions": 1,
        "systemd": {"colors": 1},
        "docker": {
            "host": "unix:///var/run/docker.sock",
        },
        "system_version_compat": 1,  # https://stackoverflow.com/questions/63972113/big-sur-clang-invalid-version-error-due-to-macosx-deployment-target
        "ansible": {
            "stdout_callback": "yaml",
            "display_skipped_hosts": False,
            "gathering": "smart",
            "diff_always": True,
            "display_args_to_stdout": True,
            "localhost_warning": False,
            "use_persistent_connections": True,
            "roles_path": os.getcwd(),
            "pipelining": True,
            "callback_whitelist": "profile_tasks",
            "deprecation_warnings": False,
            "force_color": True,
        },
    }
)

# HELPER COMMANDS

app = typer.Typer(no_args_is_help=True)


def dict2Environment(data, prefix=None, print=False):
    env_dict = benedict(data, keypath_separator=".")

    f = env_dict
    f.clean(strings=True, collections=True)
    f.standardize()
    key_paths = f.keypaths(indexes=True)

    # print(key_paths)

    for path in key_paths:
        key = path
        value = f[path]

        if isinstance(value, list):
            continue

        if isinstance(value, dict):
            continue

        # Flatten key
        key = key.replace(".", "_").upper()

        if print:
            typer.echo(f"{key}={value}")
        else:
            os.environ[key] = str(value)

    # env_dict.traverse(traverse_item)


def hashString(string: str) -> bytes:
    compressed_data = zlib.compress(string.encode())
    encoded_data = base64.b64encode(compressed_data)

    return encoded_data


def unhashString(encoded_data: bytes) -> str:
    decoded_data = base64.b64decode(encoded_data)
    uncompressed_data = zlib.decompress(decoded_data)

    return uncompressed_data.decode("utf-8")


def normalize_name(name):
    return re.sub(r"[^-_a-z0-9]", "", name.lower())


def autocomplete_code(incomplete: str):
    # return ["Camila", "Carlos", "Sebastian"]
    root, dirs, files = next(os.walk(arc["arco"]["app_dir"]), ([], [], []))

    completion = []
    for directory in dirs:
        if directory.startswith(incomplete):
            completion.append(directory)
    return completion


def loadConfig(config_file: str = None):
    if config_file:
        # Try to assess suffix
        extension = fsutil.get_file_extension(config_file)

        try:
            arco_config = benedict(config_file, format=extension)
            return arco_config
        except Exception as e:
            pass
    return None


def saveSpacefile(space_config: dict = None, spacefile: str = None):

    if space_config:
        try:
            space_config = anyconfig.dump(space_config, spacefile, "yaml")
            return space_config
        except Exception as e:
            pass
    return None


@app.command(name="open")
def apollo_open():
    if "space_dir" in arc:
        if arc["space_dir"]:
            typer.launch(arc["space_dir"])
        else:
            typer.echo("No config found")
    else:
        typer.echo("No config found")


@app.command()
def edit():
    if "spacefile" in arc:
        if arc["spacefile"]:
            typer.launch(arc["spacefile"])
        else:
            typer.echo("No config found")
    else:
        typer.echo("No config found")


def arc_search(pattern: str):
    # m = arc.match(pattern, indexes=True)
    kp = arc.keypaths()

    result = []
    for keypath in kp:
        if pattern in keypath:
            result.append(keypath)

    return result


@app.command()
def config(
    silent: bool = False,
    copy: bool = typer.Option(False, "--copy", "-c"),
    render_yaml: bool = typer.Option(True, "--yaml"),
    render_json: bool = typer.Option(False, "--json"),
    render_env: bool = typer.Option(False, "--env"),
    pretty: bool = typer.Option(True, "--pretty"),
    save: bool = typer.Option(False, "--save"),
    filter: str = typer.Option(None, "--filter", "-f", autocompletion=arc_search),
):

    config = arc
    config["arco"]["cli_context"] = ""

    if filter:
        config = config[filter]

    if print:
        if render_json:
            if pretty:

                typer.echo(anyconfig.dumps(config, ac_parser="json", indent=2))
            else:
                typer.echo(anyconfig.dumps(config, "json"))

        elif render_env:
            dict2Environment(arc, print=True)

        elif render_yaml:
            typer.echo(anyconfig.dumps(config, ac_parser="yaml"))

        return arc

    if copy:
        pyperclip.copy(anyconfig.dumps(config, "yaml"))
        pyperclip.paste()

    return None


@app.command()
def clone(repository: str, directory: str = typer.Argument(app_dir)):
    """
    Clone code or context
    """

    command = ["git", "clone", repository]

    logger.info(f"Cloning {repository} to {directory}")

    result = subprocess.run(command, cwd=directory)

    if result.returncode != 0:
        logger.error(
            f"Command '{' '.join(command)}' returned exit code {result.returncode}"
        )
        sys.exit(result.returncode)

    return result


@app.command()
def commit(message: str):
    """
    Commit configuration changes to the space (requires git)
    """
    command = ["git", "commit", "-am", f"{message}"]

    if arc["verbosity"] > 0:
        typer.secho(f"{command}", fg=typer.colors.BRIGHT_BLACK)

    commit = subprocess.run(command)

    return commit


@app.command()
def push():
    """
    Push configuration changes to the space repository (requires git)
    """
    command = ["git", "push"]

    if arc["verbosity"] > 0:
        typer.secho(f"{command}", fg=typer.colors.BRIGHT_BLACK)

    push = subprocess.run(command)

    return push


@app.command(name="hash")
def apollo_hash(data=typer.Argument(None)):

    if data:
        data = "\n".join([data])
        hashed_data = hashString(data).decode("UTF-8")
        print(hashed_data)

        return hashed_data

    if not sys.stdin.isatty():
        line_container = []
        lines = sys.stdin.readlines()

        for line in lines:
            if line != "":
                line_container.append(line.rstrip("\n\n"))
        data = "".join(line_container)

        hashed_data = hashString(data).decode("UTF-8")

        print(hashed_data)
        return hashed_data

    return data


@app.command(name="unhash")
def apollo_unhash(data: str = typer.Argument(None)):
    if data:
        data = "\n".join([data])

        unhashed_data = unhashString(data.encode())
        print(unhashed_data)

        return unhashed_data

    if not sys.stdin.isatty():
        line_container = []
        lines = sys.stdin.readlines()

        for line in lines:
            if line != "":
                line_container.append(line.rstrip("\n\n"))
        data = "".join(line_container)

        unhashed_data = unhashString(data.encode())
        print(unhashed_data)
        return unhashed_data

    return data
    print(unhashString(data.encode()))


# def runAnsible(custom_command, custom_vars: dict = {}, playbook_directory: str = None):
#     os.environ["ANSIBLE_VERBOSITY"] = str(arc["verbosity"])
#     os.environ["ANSIBLE_STDOUT_CALLBACK"] = "yaml"
#     os.environ["ANSIBLE_DISPLAY_SKIPPED_HOSTS"] = "false"
#     os.environ["ANSIBLE_GATHERING"] = "smart"
#     os.environ["ANSIBLE_DIFF_ALWAYS"] = "true"
#     os.environ["ANSIBLE_DISPLAY_ARGS_TO_STDOUT"] = "true"
#     os.environ["ANSIBLE_LOCALHOST_WARNING"] = "false"
#     os.environ["ANSIBLE_USE_PERSISTENT_CONNECTIONS"] = "true"
#     os.environ["ANSIBLE_ROLES_PATH"] = playbook_directory
#     os.environ["ANSIBLE_PIPELINING"] = "true"
#     os.environ["ANSIBLE_CALLBACK_WHITELIST"] = "profile_tasks"
#     os.environ["ANSIBLE_DEPRECATION_WARNINGS"] = "false"

#     if not arc["verbosity"] > 0:
#         os.environ["ANSIBLE_DEPRECATION_WARNINGS"] = "false"

#     base_vars = arc

#     if custom_vars:
#         base_vars = base_vars + custom_vars

#     base_command = ["ansible-playbook"]

#     # Create tempfile with inventory from config
#     # arc["clusters"][cluster]["inventory"]
#     if "inventory" in arc["config"]["clusters"][arc["cluster"]]:
#         inventory = arc["config"]["clusters"][arc["cluster"]]["inventory"]

#         if inventory:
#             # Create tempfile
#             tmp_inventory = tempfile.TemporaryFile()
#             anyconfig.dump(inventory, tmp_inventory)

#         base_command = base_command + ["-i", tmp_inventory]

#     if arc["config"]["clusters"][arc["cluster"]].get("inventory_file"):
#         inventory_file = arc["config"]["clusters"][arc["cluster"]]["inventory_file"]

#         base_command = base_command + ["-i", inventory_file]
#     else:
#         # Check if we have a cluster inventory
#         cluster_inventory = os.path.join(arc["cluster_dir"], "inventory.yml")

#         if os.path.exists(cluster_inventory):
#             base_command = base_command + [
#                 "-i",
#                 cluster_inventory,
#             ]

#     base_command = base_command + [
#         "--flush-cache",
#         "--extra-vars",
#         f"{json.dumps(base_vars)}",
#     ]

#     run_command = base_command + custom_command

#     if arc["dry"]:
#         typer.secho(f"Running in check mode", fg=typer.colors.BRIGHT_BLACK)
#         run_command.append("--check")

#     if arc["verbosity"] > 0:
#         typer.secho(f"{run_command}", fg=typer.colors.BRIGHT_BLACK)
#         typer.secho(
#             f"playbook_directory: {playbook_directory}",
#             fg=typer.colors.BRIGHT_BLACK,
#         )
#         typer.secho(f"custom_command: {custom_command}", fg=typer.colors.BRIGHT_BLACK)
#         typer.secho(f"custom_vars: {custom_vars}", fg=typer.colors.BRIGHT_BLACK)

#     result = subprocess.run(run_command, cwd=playbook_directory)

#     return result


# @app.command()
# def play(
#     ctx: typer.Context,
#     playbook_directory: str = typer.Option(
#         None,
#         "--playbook-directory",
#         help="Run Ansible in the context of the current PWD instead of the space directory",
#     ),
#     vars: str = typer.Option(
#         None,
#         "--vars",
#         help="additional variables to feed to ansible (accepts JSON dicts)",
#     ),
#     playbook: str = typer.Argument(...),
# ):
#     """
#     Run Ansible playbooks against a cluster
#     """

#     # Fail if we don't have a cluster to target
#     if "spacefile" not in arc:
#         typer.secho(
#             f"No space selected. Set --space to select a space",
#             err=True,
#             fg=typer.colors.RED,
#         )
#         raise typer.Abort()
#     if "cluster" not in arc:
#         typer.secho(
#             f"No cluster selected. Set --cluster to select a cluster",
#             err=True,
#             fg=typer.colors.RED,
#         )
#         raise typer.Abort()

#     command = [
#         playbook,
#     ]

#     custom_vars = {}

#     if ctx.args:
#         command = command + ctx.args

#     # Execute playbook
#     if not playbook_directory:
#         playbook_directory = arc["space_dir"]

#     result = runAnsible(command, custom_vars, playbook_directory)

#     if result.returncode == 0:
#         typer.secho(f"Run successful", err=False, fg=typer.colors.GREEN)
#         return result
#     else:
#         typer.secho(f"Run failed", err=True, fg=typer.colors.RED)
#         raise typer.Exit(code=result.returncode)

# # Kubernetes
# @logger.catch
# def runKubectl(custom_command, custom_vars: dict = {}):
#     base_command = ["kubectl"]

#     run_command = base_command + custom_command

#     if arc["verbosity"] > 0:
#         typer.secho(f"{run_command}", fg=typer.colors.BRIGHT_BLACK)

#     result = subprocess.run(run_command)

#     return result


# @logger.catch
# @app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
# def k(ctx: typer.Context):
#     if arc.get("spacefile") and (not arc.get("kubeconfig") or not arc.get("cluster")):
#         logger.error("No kubeconfig available")
#         sys.exit(1)

#     command = []

#     if ctx.args:
#         command = command + ctx.args

#     runKubectl(command)


# # Docker Compose
# @logger.catch
# def runDockerCompose(command, custom_vars: dict = {}, config=None, raw=False):
#     base_command = ["docker-compose"]

#     if not raw:
#         run_command = base_command + ["-f", "-"] + command

#         if arc["verbosity"] > 0:
#             typer.secho(f"{run_command}", fg=typer.colors.BRIGHT_BLACK)

#         result = subprocess.run(run_command, text=True, input=config)
#     else:
#         run_command = base_command + command

#         if arc["verbosity"] > 0:
#             typer.secho(f"{run_command}", fg=typer.colors.BRIGHT_BLACK)

#         result = subprocess.run(run_command)

#     return result


# @logger.catch
# @app.command(
#     context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
#     name="docker-compose",
# )
# @app.command(
#     context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
#     name="dc",
# )
# def dc(
#     ctx: typer.Context,
#     raw: bool = typer.Option(
#         False, "--raw", help="Don't apply augmentations, run docker-compose direct"
#     ),
# ):
#     command = []
#     args = []

#     if ctx.args:
#         args = args + ctx.args

#     # If --raw, just run the command
#     if not raw:
#         # Cleanup args, remove "-f" flags if not running in raw mode

#         for arg in reversed(args):
#             if arg == "-f":

#                 # Get next arg
#                 this_arg = args.index(arg)
#                 next_arg = args.index(arg) + 1

#                 # Remove next arg
#                 del args[next_arg]
#                 del args[this_arg]

#         # Load jinja-templated docker-compose.yml
#         with open("docker-compose.yml") as file_:
#             template = jinja2.Template(file_.read())
#         rendered = template.render(arc)

#         command = command + args

#         executed = runDockerCompose(command=command, config=rendered)

#         if executed.returncode != 0:
#             typer.secho(
#                 f"docker-compose returned exit code {executed.returncode}",
#                 err=True,
#                 fg=typer.colors.RED,
#             )
#             raise typer.Exit(code=executed.returncode)
#     else:
#         command = command + args
#         runDockerCompose(command=command, raw=raw)


# # Docker
# @logger.catch
# def runDocker(command, custom_vars: dict = {}, raw=False):
#     base_command = ["docker"]

#     if not raw:
#         run_command = base_command + command

#         if arc["verbosity"] > 0:
#             typer.secho(f"{run_command}", fg=typer.colors.BRIGHT_BLACK)

#         result = subprocess.run(run_command)
#     else:
#         run_command = base_command + command

#         if arc["verbosity"] > 0:
#             typer.secho(f"{run_command}", fg=typer.colors.BRIGHT_BLACK)

#         result = subprocess.run(run_command)

#     return result

# @logger.catch
# @app.command(
#     context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
#     name="docker",
# )
# @app.command(
#     context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
#     name="d",
# )
# def apollo_docker(
#     ctx: typer.Context,
#     raw: bool = typer.Option(
#         False, "--raw", help="Don't apply augmentations, run docker direct"
#     ),
# ):
#     if arc.get("spacefile") and not arc.get("cluster"):
#         logger.error("No cluster selected")
#         sys.exit(1)

#     if arc.get("cluster") and not arc["config"]["clusters"].get("cluster"):
#         logger.error(
#             f"Cluster '{arc['cluster']}' does not exist in space '{arc['space']}'"
#         )
#         sys.exit(1)

#     if arc.get("spacefile") and not arc.get("docker_host"):
#         logger.error("No docker_host selected")
#         sys.exit(1)

#     command = []
#     args = []

#     if ctx.args:
#         args = args + ctx.args

#     # If --raw, just run the command
#     if not raw:
#         command = command + args
#         executed = runDocker(command=command)

#         if executed.returncode != 0:
#             logger.error(f"docker returned exit code {executed.returncode}")
#             sys.exit(1)
#     else:
#         command = command + args
#         executed = runDocker(command=command, raw=raw)

#         if executed.returncode != 0:
#             typer.secho(
#                 f"docker returned exit code {executed.returncode}",
#                 err=True,
#                 fg=typer.colors.RED,
#             )
#             raise typer.Exit(code=executed.returncode)


@app.command(
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
@logger.catch
def run(ctx: typer.Context, command: str = typer.Argument(...)):
    args = []

    if ctx.args:
        args = args + ctx.args

    if command in ["ansible-playbook", "ap", "ak"]:
        pass

    if command in ["docker"]:
        pass

    command = [command] + args

    result = subprocess.run(
        command, cwd=arc["arco"]["code_dir"], universal_newlines=True, shell=False
    )

    if result.returncode != 0:
        logger.error(
            f"Command '{' '.join(command)}' returned exit code {result.returncode}"
        )
        sys.exit(result.returncode)


def version_callback(value: bool):
    if value:
        version = read_version(str(Path(__file__).parent / "__init__.py"))
        typer.echo(f"{version}")
        raise typer.Exit()


@app.callback(
    invoke_without_command=True,
)
# @logger.catch
def callback(
    ctx: typer.Context,
    context: str = typer.Option(
        None,
        "--context",
        help="The context to load",
        envvar=["ARCO_CONTEXT"],
    ),
    code: str = typer.Option(
        None,
        "--code",
        help="The code to load",
        envvar=["ARCO_CODE"],
        autocompletion=autocomplete_code,
    ),
    env_file: str = typer.Option(
        os.path.join(os.getcwd(), ".env"),
        "--env-file",
        "-e",
        help="A file containing environment variables to be used during command execution",
        envvar=["ARCO_ENV_FILE"],
    ),
    loglevel: str = typer.Option("WARNING", "--loglevel", help="Loglevel"),
    name: str = typer.Option(
        normalize_name(os.path.basename(os.getcwd())),
        "--name",
        "-n",
        help="an optional name for the context you're running in",
        envvar=["ARCO_CONTEXT_NAME"],
    ),
    var: Optional[List[str]] = typer.Option(
        None,
        "--var",
        help="Add additional vars at runtime; you can use paths like '--var context.key=value' to nest values",
        autocompletion=arc_search,
    ),
    version: Optional[bool] = typer.Option(
        None, "--version", callback=version_callback, is_eager=True
    ),
):
    # Load from .env
    # load_dotenv(dotenv_path=env_file)

    # conf = arc
    global arc

    if name:
        arc["arco"]["name"] = name

    if loglevel:
        arc["arco"]["loglevel"] = loglevel.upper()
        logger.add(sys.stdout, level=loglevel.upper())

    if code:
        # Try to find code_dir locally
        code_dir = os.path.join(os.getcwd(), code)
        code_found = False

        if os.path.isdir(code_dir):
            logger.debug(f"Found code_dir in {code_dir}")
            arc["arco"]["code_dir"] = code_dir
            code_found = True

        # Try to find code_dir .arco/ in $CWD
        code_dir = os.path.join(os.getcwd(), ".arco", code)

        if os.path.isdir(code_dir):
            logger.debug(f"Found code_dir in {code_dir}")
            arc["arco"]["code_dir"] = code_dir
            code_found = True

        # Try to find code_dir in app_dir
        code_dir = os.path.join(arc["arco"]["app_dir"], code)

        if os.path.isdir(code_dir):
            logger.debug(f"Found code_dir in {code_dir}")
            arc["arco"]["code_dir"] = code_dir
            code_found = True

        # Can't find code_dir?
        # Exit. The user has specified to use it
        # so we should terminate if it can't be found
        if not code_found:
            logger.error(f"Can't locate code in {code}")
            sys.exit(1)

    if context:
        # Try to find context_dir locally
        context_dir = os.path.isdir(os.path.join(os.getcwd(), context))
        context_found = False

        if os.path.isdir(context_dir):
            logger.debug(f"Found context_dir in {context_dir}")
            arc["arco"]["context_dir"] = context_dir
            context_found = True

        # Try to find context_dir .arco/ in $CWD
        context_dir = os.path.join(os.getcwd(), ".arco", context)

        if os.path.isdir(context_dir):
            logger.debug(f"Found context_dir in {context_dir}")
            arc["arco"]["context_dir"] = context_dir
            context_found = True

        # Try to find context_dir in app_dir
        context_dir = os.path.join(arc["app_dir"], context)

        if os.path.isdir(context_dir):
            logger.debug(f"Found context_dir in {context_dir}")
            arc["arco"]["context_dir"] = context_dir
            context_found = True

        # Can't find context_dir?
        # Exit. The user has specified to use it
        # so we should terminate if it can't be found
        if not context_found:
            logger.error(f"Can't locate context in {context}")
            sys.exit(1)

    # Load context
    _context = loadConfig(os.path.join(arc["arco"]["context_dir"], "arco.yml"))

    # Load code context
    _code = loadConfig(os.path.join(arc["arco"]["code_dir"], "arco.yml"))

    # Merge
    # 1. Code
    if _code:
        # updated_arc = benedict(arc)
        arc.merge(_code, overwrite=True, concat=False)

        logger.debug(f"Merged code from {arc['arco']['code_dir']}")

        # arc = updated_code

    # 2. Context
    if _context:
        arc.merge(_context, overwrite=True, concat=False)

        logger.debug(f"Merged context from {arc['arco']['context_dir']}")

    #
    #
    #

    arc["ansible"]["roles_path"] = arc["arco"]["code_dir"]

    # Populate extra vars
    for v in var:
        key, value = v.split("=")

        # Split key on separator (.)
        d = benedict(arc)
        d[key] = value

    # Populate arc to environment
    dict2Environment(arc)

    arc["arco"]["cli_context"] = ctx.__dict__


if __name__ == "__main__":
    app()
