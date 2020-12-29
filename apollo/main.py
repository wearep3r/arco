#!/usr/bin/env python3

import typer
import os
import subprocess
import yaml
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

APP_NAME = "apollo"
logger.debug(f"Starting {APP_NAME}")

app_dir = typer.get_app_dir(APP_NAME)
index_file = os.path.join(app_dir, ".index.json")

if not os.path.exists(app_dir):
    os.mkdir(app_dir)
    typer.echo(f"Created config directory at {app_dir}")


@logger.catch
def loadIndex():
    # Check index exists
    try:
        if not os.path.isfile(index_file):
            index = {
                "version": 1,
                "active": "default",
                "spaces": {},
            }

            anyconfig.dump(index, index_file, "json")
        else:
            index = anyconfig.load(index_file, "json")
        return index
    except Exception as e:
        typer.secho(
            f"Couldn't load index from {index_file}: {e}",
            err=True,
            fg=typer.colors.RED,
        )


def saveIndex(index: dict):
    try:
        anyconfig.dump(index, arc["index_file"], "json")
    except Exception as e:
        typer.secho(
            f"Couldn't update index at {arc['index_file']}: {e}",
            err=True,
            fg=typer.colors.RED,
        )

    arc["index"] = index
    return index


app = typer.Typer(help="apollo CLI", no_args_is_help=True)
index_app = typer.Typer()
app.add_typer(index_app, name="index")

arc = {
    "app_dir": app_dir,
    "index_file": index_file,
    "index": loadIndex(),
    "defaults_path": str(Path(__file__).parent / "Spacefile.yml"),
    "ansible_path": str(Path(__file__).parent / "ansible"),
    "version": read_version(str(Path(__file__).parent / "__init__.py")),
    "cwd": os.getcwd(),
}


# HELPER COMMANDS


def normalize_name(name):
    return re.sub(r"[^-_a-z0-9]", "", name.lower())


def space_list():
    return list(arc["index"]["spaces"].keys())


def loadSpacefile(spacefile: str = None):
    if spacefile:
        try:
            space_config = anyconfig.load(spacefile, "yaml")
            return space_config
        except Exception as e:
            if arc["verbosity"] > 0:
                typer.secho(
                    f"Could not load Spacefile: {e}", err=True, fg=typer.colors.RED
                )
    return None


def saveSpacefile(space_config: dict = None, spacefile: str = None):

    if space_config:
        try:
            space_config = anyconfig.dump(space_config, spacefile, "yaml")
            return space_config
        except Exception as e:
            if arc["verbosity"] > 0:
                typer.secho(
                    f"Could not save Spacefile: {e}", err=True, fg=typer.colors.RED
                )
    return None


def getSpaceNameFromIndex():
    if arc["index"]:
        for space in arc["index"]["spaces"]:
            if arc["index"]["spaces"][space]["spacefile"] == arc["spacefile"]:
                return space
    return None


@app.command()
def open():
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


@app.command()
def config(print: bool = True, rc: bool = False):
    if rc:
        if print:
            typer.echo(json.dumps(arc, indent=2))

        return arc
    else:
        if "config" in arc:
            if print:
                typer.echo(anyconfig.dumps(arc["config"], "yaml"))

            return arc["config"]
    return None


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


@app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def inventory(ctx: typer.Context):
    base_command = ["ansible-inventory", "-i", arc["spacefile"]]

    cluster_inventory = os.path.join(arc["space_dir"], arc["cluster"], "inventory.yml")

    if os.path.exists(cluster_inventory):
        base_command = base_command + [
            "-i",
            cluster_inventory,
        ]

    run_command = base_command + ctx.args

    if arc["verbosity"] > 0:
        typer.secho(f"{run_command}", fg=typer.colors.BRIGHT_BLACK)

    result = subprocess.run(run_command, cwd=arc["ansible_path"])

    return result


def runAnsible(custom_command, custom_vars: dict = {}, playbook_directory: str = None):
    os.environ["ANSIBLE_VERBOSITY"] = str(arc["verbosity"])
    os.environ["ANSIBLE_STDOUT_CALLBACK"] = "yaml"
    os.environ["ANSIBLE_DISPLAY_SKIPPED_HOSTS"] = "false"
    os.environ["ANSIBLE_GATHERING"] = "smart"
    os.environ["ANSIBLE_DIFF_ALWAYS"] = "true"
    os.environ["ANSIBLE_DISPLAY_ARGS_TO_STDOUT"] = "true"
    os.environ["ANSIBLE_LOCALHOST_WARNING"] = "false"
    os.environ["ANSIBLE_USE_PERSISTENT_CONNECTIONS"] = "true"
    os.environ["ANSIBLE_ROLES_PATH"] = playbook_directory
    os.environ["ANSIBLE_PIPELINING"] = "true"
    os.environ["ANSIBLE_CALLBACK_WHITELIST"] = "profile_tasks"
    os.environ["ANSIBLE_DEPRECATION_WARNINGS"] = "false"

    if not arc["verbosity"] > 0:
        os.environ["ANSIBLE_DEPRECATION_WARNINGS"] = "false"

    base_vars = arc

    if custom_vars:
        base_vars = base_vars + custom_vars

    base_command = ["ansible-playbook"]

    # Create tempfile with inventory from config
    # arc["clusters"][cluster]["inventory"]
    if "inventory" in arc["config"]["clusters"][arc["cluster"]]:
        inventory = arc["config"]["clusters"][arc["cluster"]]["inventory"]

        if inventory:
            # Create tempfile
            tmp_inventory = tempfile.TemporaryFile()
            anyconfig.dump(inventory, tmp_inventory)

        base_command = base_command + ["-i", tmp_inventory]

    # Check if we have a cluster inventory
    cluster_inventory = os.path.join(arc["space_dir"], arc["cluster"], "inventory.yml")

    if os.path.exists(cluster_inventory):
        base_command = base_command + [
            "-i",
            cluster_inventory,
        ]

    base_command = base_command + [
        "--flush-cache",
        "--extra-vars",
        f"{json.dumps(base_vars)}",
    ]

    run_command = base_command + custom_command

    if arc["dry"]:
        typer.secho(f"Running in check mode", fg=typer.colors.BRIGHT_BLACK)
        run_command.append("--check")

    if arc["verbosity"] > 0:
        typer.secho(f"{run_command}", fg=typer.colors.BRIGHT_BLACK)
        typer.secho(
            f"playbook_directory: {playbook_directory}",
            fg=typer.colors.BRIGHT_BLACK,
        )
        typer.secho(f"custom_command: {custom_command}", fg=typer.colors.BRIGHT_BLACK)
        typer.secho(f"custom_vars: {custom_vars}", fg=typer.colors.BRIGHT_BLACK)

    result = subprocess.run(run_command, cwd=playbook_directory)

    return result


@app.command()
def run(
    ctx: typer.Context,
    playbook_directory: str = typer.Option(
        None,
        "--playbook-directory",
        help="Run Ansible in the context of the current PWD instead of the space directory",
    ),
    vars: str = typer.Option(
        None,
        "--vars",
        help="additional variables to feed to ansible (accepts JSON dicts)",
    ),
    playbook: str = typer.Argument(...),
):
    """
    Run Ansible playbooks against a cluster
    """

    # Fail if we don't have a cluster to target
    if "spacefile" not in arc:
        typer.secho(
            f"No space selected. Set --space to select a space",
            err=True,
            fg=typer.colors.RED,
        )
        raise typer.Abort()
    if "cluster" not in arc:
        typer.secho(
            f"No cluster selected. Set --cluster to select a cluster",
            err=True,
            fg=typer.colors.RED,
        )
        raise typer.Abort()

    command = [
        playbook,
    ]

    custom_vars = {}

    if ctx.args:
        command = command + ctx.args

    # Execute playbook
    if not playbook_directory:
        playbook_directory = arc["space_dir"]

    result = runAnsible(command, custom_vars, playbook_directory)

    if result.returncode == 0:
        typer.secho(f"Run successful", err=False, fg=typer.colors.GREEN)
        return result
    else:
        typer.secho(f"Run failed", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=result.returncode)


@app.command()
def copy():
    kubeconfig = anyconfig.load(arc["kubeconfig"], "yaml")
    pyperclip.copy(anyconfig.dumps(kubeconfig, "yaml"))
    pyperclip.paste()


# @app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
# def install(ctx: typer.Context):
#     """
#     Deploy apollo
#     """

#     command = [
#         "install.yml",
#     ]

#     custom_vars = {}

#     if ctx.args:
#         command = command + ctx.args

#     if arc["verbosity"] > 0:
#         typer.secho(f"{command}", fg=typer.colors.BRIGHT_BLACK)

#     result = runPlay(command, custom_vars)

#     if result.returncode == 0:
#         typer.secho(f"Deployment successful", err=False, fg=typer.colors.GREEN)
#         return result
#     else:
#         typer.secho(f"Deployment failed", err=True, fg=typer.colors.RED)
#         raise typer.Exit(code=result.returncode)


@app.command(name="add-space")
def add_space(
    name: str = typer.Option(
        normalize_name(os.path.basename(os.getcwd())),
        "--name",
        "-n",
        help="a human readable name for your space",
    ),
    directory: str = typer.Option(
        os.getcwd(),
        "--directory",
        "-d",
        help="a directory to store your space in",
    ),
    silent: bool = typer.Option(False, "--silent", "-s", help="don't be so talky"),
):

    directory = os.path.abspath(directory)

    # Assemble Spacefile.yml
    config = {"clusters": {"default": {}}}
    spacefile = os.path.join(directory, "Spacefile.yml")

    try:
        anyconfig.dump(config, spacefile)

        if not silent:
            message = typer.style("Spacefile saved to ", fg=typer.colors.WHITE)
            message = message + typer.style(f"{directory}", fg=typer.colors.GREEN)
            typer.echo(message)
    except Exception as e:
        typer.secho(f"Could not save Spacefile: {e}", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1)

    # Setup index
    index = arc["index"]
    index["spaces"][name] = {"spacefile": spacefile}

    updated_index = saveIndex(index)


@app.command(name="delete-space")
def delete_space(
    silent: bool = typer.Option(False, "--silent", "-s", help="don't be so talky"),
):

    if "space" in arc:
        #  Setup index
        index = arc["index"]
        del index["spaces"][arc["space"]]

        updated_index = saveIndex(index)

        if not silent:
            message = typer.style("Deleted space ", fg=typer.colors.WHITE)
            message = message + typer.style(f"{arc['space']}", fg=typer.colors.GREEN)
            typer.echo(message)
            typer.secho(
                f"Run 'rm -rf {arc['cwd']}' to clean up",
                fg=typer.colors.WHITE,
            )
    else:
        typer.echo("No space selected")


@app.command(name="add-cluster")
def add_cluster(
    name: str = typer.Option(
        normalize_name(os.path.basename(os.getcwd())),
        "--name",
        "-n",
        help="a human readable name for your space",
    ),
    kubeconfig: str = typer.Option(
        None, "--kubeconfig", help="path to the cluster's kubeconfig"
    ),
    docker_host: str = typer.Option(
        None, "--docker-host", help="the cluster's docker host"
    ),
    silent: bool = typer.Option(False, "--silent", "-s", help="don't be so talky"),
):

    # Check if we have a spacefile
    if "spacefile" in arc and arc["spacefile"]:
        # Check if config has been loaded
        if "config" in arc:
            space_config = arc["config"]

            space_config["clusters"][name] = {}
            cluster_config = space_config["clusters"][name]

            if kubeconfig:
                cluster_config["kubeconfig"] = kubeconfig

            if docker_host:
                cluster_config["docker_host"] = docker_host

            updated_config = saveSpacefile(space_config, arc["spacefile"])

            return updated_config
        else:
            if not silent:
                typer.secho("No config found")
    else:
        if not silent:
            typer.secho("Cannot add cluster: no Spacefile found")

    sys.exit(1)


# @app.command()
# def init(force: bool = typer.Option(False, "--force", "-f")):
#     """
#     Initialize space configuration
#     """

#     # typer.secho("Initializing apollo config", bold=True, fg=typer.colors.BRIGHT_BLACK)

#     # Check if config already exists
#     if os.path.exists(arc["spacefile"]):
#         if not force:
#             message = typer.style(
#                 "Config already exists. ",
#                 bold=True,
#                 fg=typer.colors.RED,
#             )
#             message += typer.style(
#                 "Run '!! -f' (or 'apollo init --force') to overwrite it.",
#                 bold=False,
#                 fg=typer.colors.WHITE,
#             )
#             typer.echo(message)
#             raise typer.Exit(code=1)

#     defaults = anyconfig.load(arc["defaults_path"])

#     # with open(arc["defaults_path"], "r") as file:
#     #     defaults = yaml.load(file, Loader=yaml.FullLoader)

#     # name
#     if defaults["all"]["id"] == "default":
#         # Generate random name
#         cluster_name = namesgenerator.get_random_name(sep="-")

#         # Prompt for
#         space_id = typer.prompt("Set a cluster id", default=cluster_name)

#         # Check if a cluster with this index already exists
#         if space_id in arc["index"]["spaces"]:
#             # Cluster exists
#             overwrite = typer.prompt(
#                 "A cluster with that id already exists. Overwrite?",
#                 abort=True,
#             )
#             typer.secho("Overwriting cluster index for {space_id}", fg=typer.colors.WHITE)
#         defaults["all"]["id"] = space_id

#     # Save Spacefile.yml
#     try:
#         anyconfig.dump(defaults, arc["spacefile"])

#         message = typer.style("Config saved to ", fg=typer.colors.WHITE)
#         message = message + typer.style(f"{arc['inventory']}", fg=typer.colors.GREEN)
#         typer.echo(message)
#     except Exception as e:
#         typer.secho(f"Could not save config: {e}", err=True, fg=typer.colors.RED)
#         raise typer.Exit(code=1)

#     # Update index
#     index = arc["index"]

#     index["spaces"][space_id] = {"spacefile": arc["spacefile"]}

#     updated_index = saveIndex(index)


def version_callback(value: bool):
    if value:
        version = read_version(str(Path(__file__).parent / "__init__.py"))
        typer.echo(f"{version}")
        raise typer.Exit()


# @app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
# def create(
#     ctx: typer.Context,
# ):
#     if arc["cluster"] in arc["config"]:
#         # Check if inventory exists
#         cluster_inventory = os.path.join(
#             arc["space_dir"], arc["cluster"], "inventory.yml"
#         )
#         if os.path.exists(cluster_inventory):
#             inventory = anyconfig.load(cluster_inventory)

#             if len(inventory[arc["cluster"]]) > 0:
#                 typer.secho(
#                     f"Cluster already created. Run 'apollo -s {arc['space_id']} -c {arc['cluster']} inventory' for more information",
#                     fg=typer.colors.GREEN,
#                 )
#                 raise typer.Exit()

#     command = [
#         "--tags",
#         "create",
#         "create.yml",
#     ]

#     if ctx.args:
#         command = command + ctx.args

#     result = runPlay(command)

#     if result.returncode == 0:
#         typer.secho(f"Cluster created.", err=False, fg=typer.colors.GREEN)
#         return result
#     else:
#         typer.secho(f"Cluster creation failed.", err=True, fg=typer.colors.RED)
#         raise typer.Exit(code=result.returncode)

#     # Managers
#     # 1. Check if "nodes" list is empty
#     # 2. if so, fall back on group spec

#     raise typer.Exit()


# @app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
# def delete(
#     ctx: typer.Context,
#     list_tasks: bool = typer.Option(
#         False, "--list-tasks", "-d", help="List Tasks, do not execute"
#     ),
#     list_tags: bool = typer.Option(
#         False, "--list-tags", "-d", help="List Tags, do not execute"
#     ),
# ):

#     command = [
#         "--tags",
#         "delete",
#         "delete.yml",
#     ]

#     if list_tasks:
#         command.append("--list-tasks")

#     if list_tags:
#         command.append("--list-tags")

#     if ctx.args:
#         command = command + ctx.args

#     result = runPlay(command)

#     if result.returncode == 0:
#         typer.secho(f"Cluster deleted.", err=False, fg=typer.colors.GREEN)
#         return result
#     else:
#         typer.secho(f"Cluster deletion failed.", err=True, fg=typer.colors.RED)
#         raise typer.Exit(code=result.returncode)

#     # Managers
#     # 1. Check if "nodes" list is empty
#     # 2. if so, fall back on group spec

#     raise typer.Exit()


# Kubernetes
def runKubectl(custom_command, custom_vars: dict = {}):
    base_command = ["kubectl"]

    run_command = base_command + custom_command

    if arc["verbosity"] > 0:
        typer.secho(f"{run_command}", fg=typer.colors.BRIGHT_BLACK)

    result = subprocess.run(run_command)

    return result


@app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def k(ctx: typer.Context):
    command = []

    if ctx.args:
        command = command + ctx.args

    runKubectl(command)


# Docker Compose
def runDockerCompose(command, custom_vars: dict = {}, config=None, raw=False):
    base_command = ["docker-compose"]

    if not raw:
        run_command = base_command + ["-f", "-"] + command

        if arc["verbosity"] > 0:
            typer.secho(f"{run_command}", fg=typer.colors.BRIGHT_BLACK)

        result = subprocess.run(run_command, text=True, input=config)
    else:
        run_command = base_command + command

        if arc["verbosity"] > 0:
            typer.secho(f"{run_command}", fg=typer.colors.BRIGHT_BLACK)

        result = subprocess.run(run_command)

    return result


@app.command(
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
    name="docker-compose",
)
@app.command(
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
    name="dc",
)
def dc(
    ctx: typer.Context,
    raw: bool = typer.Option(
        False, "--raw", help="Don't apply augmentations, run docker-compose direct"
    ),
):
    command = []
    args = []

    if ctx.args:
        args = args + ctx.args

    # If --raw, just run the command
    if not raw:
        # Cleanup args, remove "-f" flags if not running in raw mode

        for arg in reversed(args):
            if arg == "-f":

                # Get next arg
                this_arg = args.index(arg)
                next_arg = args.index(arg) + 1

                # Remove next arg
                del args[next_arg]
                del args[this_arg]

        # Load jinja-templated docker-compose.yml
        with open("docker-compose.yml") as file_:
            template = jinja2.Template(file_.read())
        rendered = template.render(arc)

        command = command + args

        executed = runDockerCompose(command=command, config=rendered)

        if executed.returncode != 0:
            typer.secho(
                f"docker-compose returned exit code {executed.returncode}",
                err=True,
                fg=typer.colors.RED,
            )
            raise typer.Exit(code=executed.returncode)
    else:
        command = command + args
        runDockerCompose(command=command, raw=raw)


# Docker
def runDocker(command, custom_vars: dict = {}, raw=False):
    base_command = ["docker"]

    if not raw:
        run_command = base_command + command

        if arc["verbosity"] > 0:
            typer.secho(f"{run_command}", fg=typer.colors.BRIGHT_BLACK)

        result = subprocess.run(run_command)
    else:
        run_command = base_command + command

        if arc["verbosity"] > 0:
            typer.secho(f"{run_command}", fg=typer.colors.BRIGHT_BLACK)

        result = subprocess.run(run_command)

    return result


@app.command(
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
    name="docker",
)
@app.command(
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
    name="d",
)
def apollo_docker(
    ctx: typer.Context,
    raw: bool = typer.Option(
        False, "--raw", help="Don't apply augmentations, run docker direct"
    ),
):
    command = []
    args = []

    if ctx.args:
        args = args + ctx.args

    # If --raw, just run the command
    if not raw:
        command = command + args
        executed = runDocker(command=command)

        if executed.returncode != 0:
            typer.secho(
                f"docker returned exit code {executed.returncode}",
                err=True,
                fg=typer.colors.RED,
            )
            raise typer.Exit(code=executed.returncode)
    else:
        command = command + args
        executed = runDocker(command=command, raw=raw)

        if executed.returncode != 0:
            typer.secho(
                f"docker returned exit code {executed.returncode}",
                err=True,
                fg=typer.colors.RED,
            )
            raise typer.Exit(code=executed.returncode)


@index_app.command("show")
def index_show(item: str = "all"):
    typer.echo(json.dumps(arc["index"], indent=4))


@index_app.command("list")
def index_list(item: str = "all", print: bool = True):
    for space in arc["index"]["spaces"]:
        if space == item or item == "all":
            message = typer.style(f"{space}", fg=typer.colors.WHITE)
            message = message + " "
            message = message + typer.style(
                f"{arc['index']['spaces'][space]['spacefile']}", fg=typer.colors.GREEN
            )
            typer.echo(message)

    # typer.echo(json.dumps(arc["index"], indent=4))


@app.command()
def activate():
    index = arc["index"]
    index["active"] = arc["space_id"]

    updated_index = saveIndex(index)

    return updated_index


@app.command()
def deactivate():
    index = arc["index"]
    index["active"] = None

    updated_index = saveIndex(index)

    return updated_index


@app.command()
def active(print: bool = True):
    active_space = arc["index"]["active"]

    if active_space:
        spacefile = arc["index"]["spaces"][active_space]["spacefile"]
    else:
        spacefile = None

    if print:
        typer.echo(f"{active_space}: {spacefile}")

    return spacefile


@app.callback(invoke_without_command=True)
@index_app.callback(invoke_without_command=True)
def callback(
    ctx: typer.Context,
    verbosity: int = typer.Option(0, "--verbosity", "-v", help="Verbosity"),
    spacefile: str = typer.Option(
        None,
        "--spacefile",
        help="The location of the Spacefile",
        envvar=["APOLLO_SPACEFILE"],
    ),
    space: str = typer.Option(
        None,
        "--space",
        "-s",
        help="The space to manage",
        envvar=["APOLLO_SPACE"],
        autocompletion=space_list,
    ),
    cluster: str = typer.Option(
        None,
        "--cluster",
        "-c",
        help="The cluster to manage",
        envvar=["APOLLO_CLUSTER"],
    ),
    env_file: str = typer.Option(
        os.path.join(os.environ.get("PWD"), ".env"),
        "--env-file",
        "-e",
        help="A file containing environment variables to be used during command execution",
        envvar=["APOLLO_ENV_FILE"],
    ),
    index: bool = typer.Option(True, "--index", help="Enable or disable indexing"),
    force: bool = typer.Option(False, "--force", help="Enable Development Mode"),
    dry: bool = typer.Option(False, "--dry", help="Enable dry run"),
    version: Optional[bool] = typer.Option(
        None, "--version", callback=version_callback, is_eager=True
    ),
):
    # Load from .env
    load_dotenv(dotenv_path=env_file)

    # Space-independent values
    arc["verbosity"] = verbosity
    arc["force"] = force
    arc["dev"] = force
    arc["dry"] = dry
    os.environ["APOLLO_FORCE"] = str(arc["force"])
    os.environ["APOLLO_CONFIG_VERSION"] = "3"
    os.environ["APOLLO_VERSION"] = arc["version"]

    # --space > --spacefile
    if space:
        if index:
            # Try to load config from index
            if space in arc["index"]["spaces"]:
                # Found that space in the index
                arc["spacefile"] = arc["index"]["spaces"][space]["spacefile"]
                arc["space"] = space
            else:
                typer.secho(
                    f"Cannot find space '{space}' in the index",
                    err=True,
                    fg=typer.colors.RED,
                )
                raise typer.Abort()
        else:
            typer.secho(
                f"Indexing is disabled. Set --spacefile to select a space directly",
                err=True,
                fg=typer.colors.RED,
            )
            raise typer.Abort()
    else:
        if spacefile:
            arc["spacefile"] = spacefile

            # Do a reverse lookup of the directory in the index to find the space name
            if index:
                arc["space"] = getSpaceNameFromIndex()

        else:
            # No specific space or spacefile has been selected
            # 1. Fall back to local Spacefile

            # Check if there's a Spacefile.yml in the current directory
            local_spacefile = os.path.join(os.getcwd(), "Spacefile.yml")

            if os.path.exists(local_spacefile):
                # If the local spacefile exists, load it
                spacefile = local_spacefile
                arc["spacefile"] = spacefile

                if index:
                    arc["space"] = getSpaceNameFromIndex()
            else:
                # If no local spacefile exists,
                # 2. Fall back to active space
                if index:
                    # Fall back to "active" space
                    active_space = arc["index"]["active"]

                    if active_space:
                        arc["space"] = active_space
                        arc["spacefile"] = arc["index"]["spaces"][active_space][
                            "spacefile"
                        ]
                    else:
                        # LAST RESORT
                        # If no active space can be loaded, proceed with defaults (no space)
                        if arc["verbosity"] > 0:
                            typer.secho(
                                "Cannot find space config. Proceeding with local context"
                            )
                        pass
                else:
                    typer.secho(
                        f"Indexing is disabled. Set --spacefile to select a space directly",
                        err=True,
                        fg=typer.colors.RED,
                    )
                    raise typer.Abort()
        pass

    # Augment variables if space configuration is available
    if "spacefile" in arc and arc["spacefile"]:
        # Space config
        arc["config"] = loadSpacefile(arc["spacefile"])

        # Spacefile
        arc["apollo_spacefile"] = arc["spacefile"]
        os.environ["APOLLO_SPACEFILE"] = arc["spacefile"]

        # Space directory
        arc["space_dir"] = str(Path(arc["spacefile"]).parent)
        arc["apollo_space_dir"] = arc["space_dir"]
        os.environ["APOLLO_SPACE_DIR"] = arc["space_dir"]

        # Cluster
        if cluster:
            arc["cluster"] = cluster
        else:
            arc["cluster"] = "default"

        arc["apollo_cluster"] = arc["cluster"]
        os.environ["APOLLO_CLUSTER"] = arc["cluster"]

        arc["cluster_dir"] = os.path.join(arc["space_dir"], arc["cluster"])
        os.environ["APOLLO_CLUSTER_DIR"] = arc["cluster_dir"]

        # Check if cluster exists
        if arc["cluster"] in arc["config"]["clusters"]:
            # Kubernetes
            if "kubeconfig" in arc["config"]["clusters"][arc["cluster"]]:
                arc["kubeconfig"] = arc["config"]["clusters"][arc["cluster"]][
                    "kubeconfig"
                ]
            else:
                cluster_kubeconfig = os.path.join(arc["cluster_dir"], "kubeconfig.yml")
                arc["kubeconfig"] = cluster_kubeconfig

            # Docker
            if "docker_host" in arc["config"]["clusters"][arc["cluster"]]:
                arc["docker_host"] = arc["config"]["clusters"][arc["cluster"]][
                    "docker_host"
                ]

    # Kubernetes
    if "kubeconfig" in arc and arc["kubeconfig"]:
        os.environ["KUBECONFIG"] = arc["kubeconfig"]
        os.environ["K8S_AUTH_KUBECONFIG"] = arc["kubeconfig"]

    if "docker_host" in arc and arc["docker_host"]:
        os.environ["DOCKER_HOST"] = arc["docker_host"]


if __name__ == "__main__":
    app()
