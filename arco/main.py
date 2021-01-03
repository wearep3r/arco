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

APP_NAME = "arco"
app_dir = typer.get_app_dir(APP_NAME)


if not os.path.exists(app_dir):
    os.mkdir(app_dir)
    logger.debug(f"Created config directory at {app_dir}")


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
logger.configure(**logger_config)


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
            "version": read_version(str(Path(__file__).parent / "__init__.py")),
            "cwd": os.getcwd(),
            "hostname": platform.node(),
            "user": pwd.getpwuid(os.getuid()).pw_name,
            "verbosity": 0,
            "context_dir": os.getcwd(),
            "code_dir": os.getcwd(),
            "date": datetime.datetime.utcnow().isoformat(),
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
            repo = git.Repo(search_parent_directories=True)

            if repo:
                namespace_context[namespace]["commit_sha"] = repo.head.commit.hexsha
                namespace_context[namespace]["commit_short_sha"] = repo.git.rev_parse(
                    namespace_context[namespace]["commit_sha"], short=8
                )
                namespace_context[namespace]["commit_ref_name"] = repo.head.reference.name
                namespace_context[namespace]["commit_tag"] = repo.tags[0]
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
            namespace_context[namespace]["roles_path"] = arc["arco"]["code_dir"]

        if namespace in ["docker"]:
            namespace_context[namespace]["buildkit"] = 1
            namespace_context[namespace]["host"] = "unix:///var/run/docker.sock"

    return namespace_context


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


def contextualizeDict(d, key, value):
    if isinstance(value, str):
        # If "key" contains any of the following words
        conversion_triggers = ["path", "dir", "folder", "file"]

        # Convert the "value" (we assume it is a directory or file path) to an absolute path
        if any(trigger in key for trigger in conversion_triggers):
            full_path = getAbsolutePath(value, arc["arco"]["context_dir"])
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
            return arco_config
        except Exception as e:
            pass
    return None


@app.command()
def config(
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
            logger.warning(f"{message}")
            config = {}

    if print:
        if format == "json":
            if pretty:
                typer.echo(anyconfig.dumps(config, ac_parser=format, indent=2))
            else:
                typer.echo(anyconfig.dumps(config, format))

        elif format == "env":
            if isinstance(config, dict):
                dict2Environment(config, print=True)

        elif format == "yaml":
            typer.echo(anyconfig.dumps(config, ac_parser=format))

        return arc

    if copy:
        pyperclip.copy(anyconfig.dumps(config, format))
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


def mountConfig(config: dict, path: str = None):
    tmp_file = tempfile.NamedTemporaryFile()
    anyconfig.dump(config, tmp_file.name, ac_parser="yaml")

    return tmp_file.name


@app.command(
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
@logger.catch
def run(ctx: typer.Context):
    args = []

    # Try to get "entrypoint" from context
    if not arc["arco"]["entrypoint"]:
        logger.error("No entrypoint defined")
        sys.exit(1)

    if ctx.args:
        args = args + ctx.args

    command_list = [arc["arco"]["entrypoint"]] + args

    logger.debug(f"Running command: {' '.join(command_list)}")

    result = subprocess.run(
        command_list, cwd=arc["arco"]["code_dir"], universal_newlines=True, shell=False
    )

    if result.returncode != 0:
        logger.error(
            f"Command '{' '.join(command_list)}' returned exit code {result.returncode}"
        )
        sys.exit(result.returncode)


@app.command(
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
@logger.catch
def x(ctx: typer.Context, command: str = typer.Argument(...)):
    args = []
    command_list = [command]

    if ctx.args:
        args = args + ctx.args

    if command in ["ansible-playbook", "ap", "ak"]:
        # Create tempfile with inventory from config
        # arc["clusters"][cluster]["inventory"]
        inventory = benedict(arc["ansible"]["inventory"])

        if inventory:
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

    if command in ["helm"]:
        if "install" in args:
            command_list.append("-f")
            command_list.append(arc["arco"]["mountpoint"])

        pass

    command_list = command_list + args

    logger.debug(f"Running command: {' '.join(command_list)}")

    result = subprocess.run(
        command_list, cwd=arc["arco"]["code_dir"], universal_newlines=True, shell=False
    )

    if result.returncode != 0:
        logger.error(
            f"Command '{' '.join(command_list)}' returned exit code {result.returncode}"
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
        envvar=["ARCO_CONTEXT_DIR"],
        autocompletion=autocomplete_code,
    ),
    context_file: str = typer.Option(
        None, "--context-file", envvar=["ARCO_CONTEXT_FILE"]
    ),
    code: str = typer.Option(
        None,
        "--code",
        help="The code to load",
        envvar=["ARCO_CODE_DIR"],
        autocompletion=autocomplete_code,
    ),
    default: bool = typer.Option(
        True,
        help="Load the default context",
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
    loglevel: str = typer.Option("WARNING", "--loglevel", help="Loglevel"),
    name: str = typer.Option(
        normalize_name(os.path.basename(os.getcwd())),
        "--name",
        "-n",
        help="an optional name for the context you're running in",
        envvar=["ARCO_CONTEXT_NAME"],
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

    # Name
    if name:
        arc["arco"]["name"] = name

    # Discovery
    arc["arco"]["discover"] = discover

    # Loglevel
    arc["arco"]["loglevel"] = loglevel.upper()
    logger_config["handlers"][0]["level"] = loglevel.upper()
    logger.configure(**logger_config)

    # Load default context from app_dir
    if default:
        _default_context_file = os.path.join(app_dir, "arco.yml")
        _default_context = loadConfig(_default_context_file)

        if _default_context:
            _default_context.traverse(contextualizeDict)
            arc.merge(_default_context, overwrite=True, concat=False)

            logger.debug(f"Merged default context from {app_dir}")

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
        context_dir = os.path.join(os.getcwd(), context)
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
        context_dir = os.path.join(arc["arco"]["app_dir"], context)

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
    _context_file = os.path.join(arc["arco"]["context_dir"], "arco.yml")
    _context = loadConfig(_context_file)

    if _context:
        _context.traverse(contextualizeDict)

    # Load code context
    _code_file = os.path.join(arc["arco"]["code_dir"], "arco.yml")
    _code = loadConfig(_code_file)

    # Merge
    # 1. Code
    if _code:
        arc.merge(_code, overwrite=True, concat=False)

        logger.debug(f"Merged code from {arc['arco']['code_dir']}")

        # Discover additional stuff
        if discover:
            current_dir = os.getcwd()
            os.chdir(arc["arco"]["code_dir"])

            discovered = discoverContext()

            arc.merge(discovered, overwrite=True, concat=False)

            os.chdir(current_dir)

    # 2. Context
    if _context:
        arc.merge(_context, overwrite=True, concat=False)

        logger.debug(f"Merged context from {arc['arco']['context_dir']}")

    # Populate extra vars
    logger.debug(f"Populating vars from --var")
    for v in var:
        key, value = v.split("=")

        # Split key on separator (.)
        # d = benedict(arc)
        arc[key] = value

    # Populate arc to environment
    dict2Environment(arc)

    # Mount arc
    arc["arco"]["mountpoint"] = mountConfig(arc)


if __name__ == "__main__":
    app()
