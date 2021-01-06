#!/usr/bin/env python3

import typer
import os
import subprocess
import sys
import re
import anyconfig
from pathlib import Path
from read_version import read_version
from typing import Optional, List
from dotenv import load_dotenv
import pyperclip
import tempfile
from loguru import logger
import pwd
import platform
import zlib
import base64
import fsutil
from benedict import benedict
import git
from slugify import slugify
import datetime
import functools
import shellingham
import shortuuid

APP_NAME = "arco"
app_dir = typer.get_app_dir(APP_NAME)


if not os.path.exists(app_dir):
    os.mkdir(app_dir)
    logger.debug(f"Created config directory at {app_dir}")

running_data_sources = []

lookup_dirs = [
    os.getcwd(),
    os.path.join(os.getcwd(), ".arco"),
    app_dir,
]

discovery_namespaces = [
    "ci",
    "platform",
    "git",
    "ansible",
    "docker",
    "kubernetes",
    "k8s",
    "helm",
]

logger_config = {
    "handlers": [
        {
            "sink": sys.stderr,
            "format": "<green>{time:YYYY-MM-DD HH:mm:ss}</green> - <lvl>{level}</lvl> - <lvl>{message}</lvl>",
            "filter": lambda record: "history" not in record["extra"],
            "level": "INFO",
        },
        {
            "sink": os.path.join(app_dir, "history.json"),
            "serialize": True,
            "format": "{message}",
            "filter": lambda record: record["extra"].get("history")
            and record["extra"]["history"],
        },
    ],
}
logger.configure(**logger_config)


@logger.catch()
def arcolog(*, entry=False, exit=True, level="INFO"):
    def wrapper(func):
        name = func.__name__

        @functools.wraps(func)
        def wrapped(*args, **kwargs):

            # Execute the wrapped function
            result = func(*args, **kwargs)

            extra = {
                "history": True,
                "successful": False,
                "result": None,
                "uuid": shortuuid.uuid()[:8],
            }

            if result:
                extra["successful"] = True
                extra["result"] = result

            logger_ = logger.opt(depth=1).bind(**extra)

            command_args = sys.argv

            # First arg will be the command
            # Remove full path, just save the command/binary
            command_args[0] = fsutil.get_filename(command_args[0])

            full_command = " ".join(command_args)

            logger_.info(full_command)

            return result

        return wrapped

    return wrapper


def provide_default_shell():
    if os.name == "posix":
        return os.environ["SHELL"]
    elif os.name == "nt":
        return os.environ["COMSPEC"]
    raise NotImplementedError(f"OS {os.name!r} support not available")


def getShell():
    user_shell = None
    try:
        user_shell = shellingham.detect_shell()[1]
    except shellingham.ShellDetectionFailure:
        user_shell = provide_default_shell()[1]

    return user_shell


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
            "version": read_version(str(Path(__file__).parent / "__init__.py")),
            "cwd": os.getcwd(),
            "hostname": platform.node(),
            "user": pwd.getpwuid(os.getuid()).pw_name,
            "verbosity": 0,
            "date": datetime.datetime.utcnow().isoformat(),
            "context": {"dir": os.getcwd()},
            "code": {"dir": os.getcwd()},
            "api": {
                "default": {"entrypoint": "cat", "args": "README.md"},
                "context": {"entrypoint": "self", "args": None},
            },
            "origins": {},
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
        "system_version_compat": 1,  # https://stackoverflow.com/questions/63972113/big-sur-clang-invalid-version-error-due-to-macosx-deployment-target
    }
)

# HELPER COMMANDS

app = typer.Typer(no_args_is_help=True)


@logger.catch
def discoverContext():
    namespace_context = {}

    for namespace in discovery_namespaces:
        namespace_context[namespace] = {}

        if namespace in ["platform"]:

            namespace_context[namespace]["name"] = platform.platform()
            namespace_context[namespace]["name_short"] = platform.platform(terse=True)
            namespace_context[namespace]["system"] = platform.system()
            namespace_context[namespace]["version"] = platform.version()
            namespace_context[namespace]["release"] = platform.release()
            namespace_context[namespace]["machine"] = platform.machine()
            namespace_context[namespace]["processor"] = platform.processor()
            namespace_context[namespace]["architecture"] = str(platform.architecture())

        if namespace in ["ci", "git"]:
            repo = None
            try:
                repo = git.Repo(search_parent_directories=True)
            except:
                pass

            if repo:
                namespace_context[namespace]["commit_sha"] = repo.head.commit.hexsha
                namespace_context[namespace]["commit_short_sha"] = repo.git.rev_parse(
                    namespace_context[namespace]["commit_sha"], short=8
                )
                namespace_context[namespace]["commit_ref_name"] = repo.head.reference.name
                namespace_context[namespace]["commit_tag"] = (
                    str(repo.tags[0]) if len(repo.tags) > 0 else ""
                )
                namespace_context[namespace]["commit_description"] = (
                    repo.head.commit.message.rstrip() or ""
                )
                namespace_context[namespace]["commit_message"] = (
                    repo.head.commit.message.rstrip() or ""
                )
                namespace_context[namespace]["commit_ref_slug"] = (
                    slugify(repo.head.reference.name.rstrip()) or ""
                )
                namespace_context[namespace]["project_name"] = arc["arco"]["name"] or ""

        if namespace in ["ansible"]:
            namespace_context[namespace]["stdout_callback"] = "yaml"
            namespace_context[namespace]["display_skipped_hosts"] = False
            namespace_context[namespace]["gathering"] = "smart"
            namespace_context[namespace]["diff_always"] = True
            namespace_context[namespace]["display_args_to_stdout"] = True
            namespace_context[namespace]["localhost_warning"] = False
            namespace_context[namespace]["use_persistent_connections"] = True
            namespace_context[namespace]["roles_path"] = os.getcwd()
            namespace_context[namespace]["pipelining"] = True
            namespace_context[namespace]["callback_whitelist"] = "profile_tasks"
            namespace_context[namespace]["deprecation_warnings"] = False
            namespace_context[namespace]["force_color"] = True
            namespace_context[namespace]["roles_path"] = arc["arco"]["code"]["dir"]

        if namespace in ["docker"]:
            namespace_context[namespace]["buildkit"] = 1
            namespace_context[namespace]["host"] = "unix:///var/run/docker.sock"

        if namespace in ["tf"]:
            namespace_context[namespace]["in_automation"] = 1
            namespace_context[namespace]["input"] = 0

    return namespace_context


def dict2Environment(data, prefix=None, print=False, uppercase=True):
    env_dict = benedict(data, keypath_separator=".")

    f = env_dict
    f.clean(strings=True, collections=True)
    # f.standardize()
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
        key = key.replace(".", "_")

        if uppercase:
            key = key.upper()

        if prefix:
            key = f"{prefix}_{key}"

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


def contextualizeDict(d, key, value):
    if isinstance(value, str):
        # If "key" contains any of the following words
        conversion_triggers = ["path", "dir", "folder", "file"]

        if not isinstance(d, list):
            # Convert the "value" (we assume it is a directory or file path) to an absolute path
            if any(trigger in key for trigger in conversion_triggers):
                full_path = getAbsolutePath(value, arc["arco"]["context"]["dir"])
                d[key] = full_path


def getAbsolutePath(path, context_dir):
    context_path = path

    os.chdir(context_dir)

    local_path = os.path.join(os.getcwd(), path)

    if fsutil.exists(local_path):
        context_path = os.path.abspath(local_path)

    return context_path


# autocomplete
def autocomplete_code(incomplete: str):
    # return ["Camila", "Carlos", "Sebastian"]
    root, dirs, files = next(os.walk(arc["arco"]["app_dir"]), ([], [], []))

    completion = []
    for directory in dirs:
        if directory.startswith(incomplete):
            completion.append(directory)
    return completion


def arc_search(pattern: str):
    # m = arc.match(pattern, indexes=True)
    kp = arc.keypaths()

    result = []
    for keypath in kp:
        if pattern in keypath:
            result.append(keypath)

    return result


def loadConfig(config_file: str = None):
    if config_file:
        # Try to assess suffix
        extension = fsutil.get_file_extension(config_file)

        try:
            arco_config = benedict(config_file, format=extension)

            # Save current context dir
            _arc_context_dir = arc["arco"]["context"]["dir"]

            # Set current context dir to this context
            arc["arco"]["context"]["dir"] = os.path.dirname(config_file)

            # Make paths absolute
            arco_config.traverse(contextualizeDict)

            # Save origin of this context path to arc._origins
            keypaths = arco_config.keypaths(indexes=False)
            for keypath in keypaths:
                if not keypath.startswith("arco.origins"):
                    arc["arco"]["origins"][keypath] = config_file

            # Reset current context_dir
            arc["arco"]["context"]["dir"] = _arc_context_dir

            return arco_config
        except Exception as e:
            print(f"Exception: {e}")
    return None


def discoverConfig(path: str = os.getcwd()):
    # Accepted files
    autodiscover_configs = [
        "arco.yml",
        "arco.json",
        ".arco.yml",
        ".arco.json",
    ]

    for config in autodiscover_configs:
        config_path = os.path.join(path, config)

        if fsutil.exists(config_path):
            return config_path


@app.command()
@arcolog()
def create(name: str = typer.Argument(...)):
    """
    Create an API Object
    """

    config_path = os.path.join(arc["arco"]["app_dir"], name)
    config_file = os.path.join(config_path, "arco.yml")

    config = benedict()

    try:
        if not os.path.exists(config_path):
            logger.debug(f"Creating directory {config_path}")
            os.mkdir(config_path)

        if not os.path.exists(config_file):
            logger.debug(f"Creating {config_file}")
            config.to_yaml(filepath=config_file)

        typer.launch(config_file)
    except Exception as e:
        logger.error(f"{e}")
    typer.launch(config_file)

    return True


@app.command()
@arcolog()
def edit(default: bool = typer.Option(False, help="Edit the default context file")):
    """
    Edit the context file. Will use context_dir to determine the file to edit
    """
    default_context_file = os.path.join(arc["arco"]["app_dir"], "arco.yml")
    current_context_file = os.path.join(arc["arco"]["context"]["dir"], "arco.yml")

    if os.path.exists(current_context_file) and not default:
        typer.launch(current_context_file)
    else:
        typer.launch(default_context_file)


@app.command()
@arcolog()
def context(
    silent: bool = False,
    copy: bool = typer.Option(False, "--copy", "-c"),
    format: str = typer.Option("json", "--format"),
    pretty: bool = typer.Option(True, "--pretty"),
    save: bool = typer.Option(False, "--save"),
    filter: str = typer.Option(None, "--filter", "-f", autocompletion=arc_search),
):

    config = arc
    config["arco"]["cli_context"] = ""

    if filter:
        try:
            filtered_data = benedict()
            filtered_data[filter] = config[filter]
            config = filtered_data
        except KeyError as e:
            message = str(e).replace("\\", "")
            logger.warning(f"Cannot locate key {message} in context")
            config = {}

    if print:
        config.clean(strings=True, collections=True)
        if format == "json":
            if pretty:
                typer.echo(anyconfig.dumps(config, ac_parser=format, indent=2))
            else:
                typer.echo(anyconfig.dumps(config, format))

        elif format == "env":
            if isinstance(config, dict):
                dict2Environment(config, print=True)

        elif format == "yaml":
            print(config.to_yaml())
            # typer.echo(anyconfig.dumps(config, ac_parser=format))
        else:
            logger.error(f"Format {format} not supported")
            sys.exit(1)

        return arc

    if copy:
        pyperclip.copy(anyconfig.dumps(config, format))
        pyperclip.paste()

    return None


@app.command()
@arcolog()
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
@arcolog()
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
@arcolog()
def push():
    """
    Push configuration changes to the space repository (requires git)
    """
    command = ["git", "push"]

    if arc["verbosity"] > 0:
        typer.secho(f"{command}", fg=typer.colors.BRIGHT_BLACK)

    push = subprocess.run(command)

    return push


@app.command()
def history(filter: str = typer.Option(None)):
    """
    Show the arco history
    """

    history_file = os.path.join(app_dir, "history.json")

    with open(history_file) as f:
        for line in f:
            data = benedict.from_json(line)

            if filter:
                if filter not in data:
                    print("NOT FOUND")
                    pass
            message_uuid = typer.style(
                f"{data['record']['extra']['uuid']}",
                fg=typer.colors.WHITE,
                bold=False,
            )

            message_date = typer.style(
                f"{data['record']['time']['repr']}", fg=typer.colors.WHITE, bold=False
            )

            if data["record"]["extra"]["successful"]:
                message_text = typer.style(
                    f"{data['record']['message']}", fg=typer.colors.GREEN, bold=False
                )
            else:
                message_text = typer.style(
                    f"{data['record']['message']}", fg=typer.colors.RED, bold=False
                )

            message = f"{message_uuid} | {message_date} | {message_text}"

            typer.echo(message)


@app.command(name="hash")
@arcolog()
def arco_hash(data=typer.Argument(None)):

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
@arcolog()
def arco_unhash(data: str = typer.Argument(None)):
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


def mountConfig(config: dict, path: str = None):
    tmp_file = tempfile.NamedTemporaryFile()
    anyconfig.dump(config, tmp_file.name, ac_parser="yaml")

    return tmp_file.name


@app.command(
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
@logger.catch
@arcolog()
def run(
    ctx: typer.Context,
    api_path: str = typer.Argument(
        f"{os.getcwd()}/default", help="Path to the API Endpoint"
    ),
):
    logger.debug(f"Running API '{api_path}'")
    args = []

    if ctx.args:
        args = args + ctx.args

    result = callAPI(api_path, args)

    if result:
        print(result)

    return result


@app.command(
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
@logger.catch
@arcolog()
def shell(
    ctx: typer.Context,
    api_path: str = typer.Argument(..., help="Path to the API Endpoint"),
):
    args = []
    if ctx.args:
        args = args + ctx.args

    user_shell = getShell()

    command_list = [user_shell]

    # Manipulate PS1
    ps1 = os.environ.get("PS1") or ""

    ps1 = " ".join([f"[{arc['arco']['name']}] ", ps1])
    os.environ["PS1"] = ps1

    logger.debug(f"Setting shell to {user_shell[1]}")
    logger.info(f"Entering interactive shell. To exit this shell, just run 'exit'")

    command_list = command_list + args

    try:
        result = subprocess.run(
            command_list,
            cwd=arc["arco"]["code"]["dir"],
            universal_newlines=True,
            shell=True,
            env=os.environ.copy(),
            executable=user_shell,
        )

        if result.returncode != 0:
            logger.warning(
                f"Command '{' '.join(command_list)}' returned exit code {result.returncode}"
            )
            return False

        return True
    except Exception as e:
        logger.error(e)
        return False

    return True


def augmentCommand(command):
    command_list = []

    logger.debug(f"Augmenting command {command}")

    if command in ["ansible-playbook", "ap", "ak"]:
        # Create tempfile with inventory from config
        # arc["clusters"][cluster]["inventory"]

        inventory = arc["ansible"].get("inventory")

        if inventory:
            inventory = benedict(arc["ansible"]["inventory"])

            # Create tempfile
            mounted_inventory = mountConfig(inventory)

            command_list.append("-i")
            command_list.append(mounted_inventory)

        inventory_file = arc["ansible"].get("inventory_file")

        if inventory_file:
            command_list.append("-i")
            command_list.append(inventory_file)

        command_list.append("--extra-vars")
        command_list.append(f"{arc.dump()}")

        pass

    if command in ["docker"]:
        pass

    if command in ["terraform"]:
        # Export vars with TF_PREFIX
        dict2Environment(arc, prefix="TF_VAR", uppercase=False)

        pass

    if command in ["helm"]:
        if "install" in args:
            command_list.append("-f")
            command_list.append(arc["arco"]["mountpoint"])

        pass

    return command_list


@app.command(
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
@logger.catch
@arcolog()
def x(ctx: typer.Context, command: str = typer.Argument(...)):
    args = []
    command_list = [command]

    activate_shell = False

    if ctx.args:
        args = args + ctx.args

    augmentations = augmentCommand(command)

    command_list = command_list + augmentations + args

    logger.debug(f"Running command: {' '.join(command_list)}")

    try:
        result = subprocess.run(
            command_list,
            cwd=arc["arco"]["code"]["dir"],
            universal_newlines=True,
            shell=activate_shell,
            env=os.environ.copy(),
        )

        if result.returncode != 0:
            logger.warning(
                f"Command '{' '.join(command_list)}' returned exit code {result.returncode}"
            )
            return False

        return result.returncode
    except Exception as e:
        logger.error(e)
        return False

    return True


# Load context-config to dict + Contextualize (i.e. make paths absolute)
# Merge in either direction
#


def mergeContext(data, updated_data):
    if updated_data:
        data.merge(updated_data, overwrite=True, concat=False)

    return data


def callAPI(api_path: str = None, args=[]):
    # Gets input like "arco-dev/install"
    # Or testfolder/subfolder/api-folder/setup
    # The LAST item of the path is always the "entrypoint" of the API
    # The first parts (arbitrary number) is the path to the API

    global arc

    api_absolute_path = None

    if not api_path:
        logger.error(f"No API seletected: {api_path}")
        sys.exit(1)

    # 1. Split API and Entrypoint
    if "/" in api_path:
        api, endpoint = api_path.rsplit("/", 1)
    else:
        # Check for and endpoint named "api_path" in local context
        if ["arco", "api", api_path] in arc:
            logger.debug(
                f"Found endpoint '{api_path}' in '{arc['arco']['origins']['arco']['api'][api_path]['entrypoint']}'. Loading its API"
            )
            api = os.getcwd()
            endpoint = api_path
        else:
            api = api_path
            endpoint = "default"

    # 2. Determine absolute path to API
    if api:
        logger.debug(f"Calling API '{api}', endpoint '{endpoint}'")

        # Iterate over "lookup_dirs" to auto-discover the API path
        if api in [".", os.getcwd()]:
            api_absolute_path = os.getcwd()
            logger.debug(f"Loading API '{api}' from '{api_absolute_path}'")
        else:
            if os.path.isabs(api):
                api_absolute_path = api
            else:
                for lookup_dir in lookup_dirs:
                    _api_dir = os.path.join(lookup_dir, api)
                    logger.debug(f"Searching API '{api}' in '{_api_dir}'")

                    if os.path.isdir(_api_dir):
                        api_absolute_path = _api_dir
                        logger.debug(f"Loading API '{api}' from '{_api_dir}'")
                        break

        if not api_absolute_path:
            logger.error(f"Cannot find API {api}")
            sys.exit(1)
    else:
        logger.error(f"No API selected: {api_path}")
        sys.exit(1)

    # Setup empty context
    _context = benedict()

    # Discover additional stuff
    if arc["arco"]["discover"]:
        current_dir = os.getcwd()

        # Switch to the path of the API
        # to discover its context
        os.chdir(api_absolute_path)

        discovered = discoverContext()

        mergeContext(_context, discovered)

        os.chdir(current_dir)

    # Locate context
    api_config_file = discoverConfig(api_absolute_path)

    if api_config_file:
        loaded = loadConfig(api_config_file)

        running_data_sources.append(api_config_file)

        logger.debug(f"Loading API config from '{api_config_file}'")
        _context = mergeContext(_context, loaded)

    # 3. Setup entrypoints
    if not endpoint:
        endpoint = "default"

    # 4. Start routing
    entrypoint = None

    # 4.1 Prepare API
    default_api = benedict(
        {
            "arco": {
                "api": {
                    "default": {"entrypoint": "self"},
                    "context": {"entrypoint": "self"},
                    "bypass": {"entrypoint": None},
                    "shell": {"entrypoint": getShell()},
                }
            }
        }
    )

    _context = mergeContext(default_api, _context)

    # Check if the endpoint exists or exit
    if endpoint not in _context["arco"]["api"]:
        logger.error(f"Endpoint {endpoint} does not exist")
        sys.exit(1)

    entrypoint = _context["arco"]["api"][endpoint].get("entrypoint")
    logger.debug(f"Setting entrypoint for endpoint '{endpoint}' to '{entrypoint}'")

    args = _context["arco"]["api"][endpoint].get("args") or args
    logger.debug(f"Setting args for endpoint '{endpoint}' to '{' '.join(args)}'")

    # If the "entrypoint" is "self", simply return the current context
    if entrypoint == "self":
        logger.debug(f"Returning current API context for entrypoint '{entrypoint}'")
        return _context

    # 5. Merge in base context
    _arc = arc

    # We're deleting the "api" section of the merged-in context
    # to not overwrite our current API's "api" settings
    del _arc["arco"]["api"]

    _context = mergeContext(_context, _arc)

    # 6. Merge current _context to arc
    # If you wonder why we do this after we merged arc into _context:
    # When merging arc into _context, we're building the current context
    # without overwriting the "api" section in _context from arc; additionally,
    # we're doing this extra step to make sure that updated context from arc overwrites
    # basic API context definied in _context
    # Since we pass the arc to the API, we need to update arc with the
    # contents from _context to have everything set correctly
    arc = mergeContext(arc, _context)

    # Get command augmentations
    augmentations = augmentCommand(entrypoint)

    # If the entrypoint is not "self", proceed with running the requested commands
    command_list = [entrypoint] + augmentations + args

    result = None

    if endpoint == "shell":
        # We do stuff differently when in shell mode
        logger.debug(f"Setting shell to {entrypoint}")
        logger.info("Entering interactive shell. To exit this shell, just run 'exit'")

        result = subprocess.run(
            command_list,
            cwd=api_absolute_path,
            universal_newlines=True,
            shell=True,
            env=os.environ.copy(),
            executable=entrypoint,
        )

    else:
        result = subprocess.run(
            command_list,
            cwd=api_absolute_path,
            universal_newlines=True,
            shell=False,
            capture_output=True,
        )

    if result.returncode != 0:
        logger.error(
            f"Command '{' '.join(command_list)}' returned exit code {result.returncode}"
        )
        sys.exit(result.returncode)

    return result.stdout


def version_callback(value: bool):
    if value:
        version = read_version(str(Path(__file__).parent / "__init__.py"))
        typer.echo(f"{version}")
        raise typer.Exit()


@app.callback(
    invoke_without_command=True,
)
@logger.catch
def callback(
    ctx: typer.Context,
    data_sources: Optional[List[str]] = typer.Option(
        None,
        "--data",
        help="Context sources to query",
        envvar=["ARCO_DATA_DIR"],
        autocompletion=autocomplete_code,
    ),
    data_files: Optional[List[str]] = typer.Option(
        None, "--context-file", envvar=["ARCO_DATA_FILE"]
    ),
    # code: str = typer.Option(
    #     None,
    #     "--code",
    #     help="The code to load",
    #     envvar=["ARCO_CODE_DIR"],
    #     autocompletion=autocomplete_code,
    # ),
    default: bool = typer.Option(
        True,
        help=f"Load default context from {app_dir}",
        envvar=["ARCO_LOAD_DEFAULT_CONTEXT"],
    ),
    discover: bool = typer.Option(True),
    env_file: str = typer.Option(
        os.path.join(os.getcwd(), ".env"),
        "--env-file",
        "-e",
        help="A file containing environment variables to be used during command execution",
        envvar=["ARCO_ENV_FILE"],
    ),
    local: bool = typer.Option(True, help="Load local context from $PWD"),
    loglevel: str = typer.Option(
        logger_config["handlers"][0]["level"], "--loglevel", help="Loglevel"
    ),
    name: str = typer.Option(
        normalize_name(os.path.basename(os.getcwd())),
        "--name",
        "-n",
        help="an optional name for the context you're running in",
        envvar=["ARCO_CONTEXT_NAME"],
    ),
    reload_vars: bool = typer.Option(
        True, help="Reload vars from --vars after context has been loaded"
    ),
    select: Optional[List[str]] = typer.Option(
        None, "--select", help="Select keypaths to be in the context."
    ),
    omit: Optional[List[str]] = typer.Option(
        None, "--omit", help="Omit keypaths from the context"
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
    load_dotenv(dotenv_path=env_file)

    # conf = arc
    global arc
    global logger

    # Loglevel
    arc["arco"]["loglevel"] = loglevel.upper()
    logger_config["handlers"][0]["level"] = loglevel.upper()
    logger.configure(**logger_config)

    # Discovery
    arc["arco"]["discover"] = discover

    stdin = False

    if not sys.stdin.isatty():
        stdin = True
        line_container = []
        lines = sys.stdin.readlines()

        for line in lines:
            if line != "":
                #    line_container.append(line.rstrip("\n\n"))
                line_container.append(line)

        _context_from_stdin = benedict("".join(line_container))

        # Merge context to arc
        arc.merge(_context_from_stdin, overwrite=True, concat=False)
        logger.debug(f"Loading context from STDIN")

    # Name
    if not arc["arco"].get("name"):
        arc["arco"]["name"] = name
        logger.debug(f"Setting name to {name}")

    # Load default context from app_dir
    if default and not stdin:
        logger.debug(f"Loading defaults ...")
        _default_context = callAPI(f"{arc['arco']['app_dir']}/context")
        mergeContext(arc, _default_context)

    # Load local context from CWD
    if local and not stdin:
        logger.debug(f"Loading local context ...")
        _local_context = callAPI(f"{os.getcwd()}/context")
        mergeContext(arc, _local_context)

    # Populate extra vars for the first time
    # We're doing this twice so we can inject vars to the context
    # that can be used while pulling additional context
    # from another endpoint (--context)
    # Later we will run this piece of code again
    # to make sure that the --vars overrride loaded context again
    logger.debug(
        f"Populating vars from --var to make them available when using --context"
    )
    for v in var:
        key, value = v.split("=")

        # Split key on separator (.)
        # d = benedict(arc)
        arc[key] = value

    # Discover contexts
    for data_source in data_sources:
        logger.debug("Loading context from --data")
        _context = callAPI(data_source)

        arc = mergeContext(arc, _context)

    # for context in data_sources:
    #     context_dir = None

    #     for context_lookup_dir in lookup_dirs:
    #         if not context_dir:
    #             _context_dir = os.path.join(context_lookup_dir, context)
    #             logger.debug(f"Checking {_context_dir} for context")

    #             if os.path.isdir(_context_dir):
    #                 context_dir = _context_dir
    #                 logger.debug(f"Found context in {context_dir}")

    #     # Can't find context_dir?
    #     # Exit. The user has specified to use it
    #     # so we should terminate if it can't be found
    #     if not context_dir:
    #         logger.error(f"Can't locate context {context}")
    #         sys.exit(1)

    #     # Load context
    #     context_file = discoverConfig(context_dir)

    #     if context_file:
    #         if context_file not in running_data_sources:
    #             running_data_sources.append(context_file)
    #             logger.debug(f"Loading {context_file}")
    #         else:
    #             logger.debug(f"Skipping context {context_file} (already discovered)")

    # Append context-files (form --context-file)
    # for context_file in data_files:
    #     running_data_sources.append(context_file)

    # Loop over running_data_sources
    # Load and merge
    # for running_context_file in running_data_sources:
    #     _context = loadConfig(running_context_file)

    #     if _context:
    #         # Make context paths absolute
    #         _arc_context_dir = arc["arco"]["context"]["dir"]

    #         arc["arco"]["context"]["dir"] = os.path.dirname(running_context_file)

    #         _context.traverse(contextualizeDict)

    #         keypaths = _context.keypaths(indexes=False)
    #         for keypath in keypaths:
    #             if not keypath.startswith("arco.origins"):
    #                 arc["arco"]["origins"][keypath] = running_context_file

    #         arc.merge(_context, overwrite=True, concat=False)

    #         logger.debug(f"Merged context from {running_context_file}")

    #         arc["arco"]["context"]["dir"] = _arc_context_dir

    # Populate extra vars
    if reload_vars:
        logger.debug("Reloading vars from --var")
        for v in var:
            key, value = v.split("=")

            # Split key on separator (.)
            # d = benedict(arc)
            arc[key] = value

    # Mount arc
    arc["arco"]["mountpoint"] = mountConfig(arc)
    logger.debug(f"Mounting context in {arc['arco']['mountpoint']}")

    # Populate arc to environment
    logger.debug(
        f"Populating context to environment. Run '{APP_NAME} context --format env' to see available environment variables"
    )
    dict2Environment(arc)

    # Export vars with TF_PREFIX
    logger.debug("Populating Terraform context to environment")
    dict2Environment(arc, prefix="TF_VAR", uppercase=False)


if __name__ == "__main__":
    app()
