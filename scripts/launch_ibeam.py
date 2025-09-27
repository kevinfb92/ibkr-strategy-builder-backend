"""
Simple Windows launcher for the `voyz/ibeam` Docker image.

Features:
- CLI mode for quick runs and automation: supports --folder, --env-file, --dry-run

Usage (CLI):
    python scripts/launch_ibeam.py --folder "C:\Users\kevin\Desktop\trading\cpapi" --env-file env.list
    python scripts/launch_ibeam.py --folder "..." --env-file env.list --dry-run

The script runs:
    docker run --env-file env.list -p 5000:5000 voyz/ibeam

It runs the command in the specified working directory.
"""

import argparse
import shlex
import subprocess
import sys
import os

DEFAULT_FOLDER = r"C:\Users\kevin\Desktop\trading\cpapi"
DEFAULT_ENV = "env.list"
DOCKER_IMAGE = "voyz/ibeam"
PORT_MAPPING = "-p 5000:5000"


def build_command(env_file: str) -> list:
    cmd = ["docker", "run"]
    if env_file:
        cmd.extend(["--env-file", env_file])
    cmd.extend([PORT_MAPPING, DOCKER_IMAGE])
    return cmd


def run_command(cmd_list, cwd, capture_output=True):
    try:
        proc = subprocess.Popen(cmd_list, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        return proc
    except FileNotFoundError as e:
        raise RuntimeError("Docker executable not found. Ensure Docker Desktop is installed and in PATH.") from e
    except Exception as e:
        raise


def cli_main(args=None):
    parser = argparse.ArgumentParser(description='Launch voyz/ibeam docker image in a folder')
    parser.add_argument('--folder', '-f', default=DEFAULT_FOLDER, help='Working folder to run docker in')
    parser.add_argument('--env-file', '-e', default=DEFAULT_ENV, help='Environment file name (relative to folder)')
    parser.add_argument('--dry-run', action='store_true', help='Print the docker command and exit')
    parsed = parser.parse_args(args=args)

    folder = os.path.abspath(parsed.folder)
    env_file = parsed.env_file
    full_env_path = os.path.join(folder, env_file) if env_file else None

    cmd = build_command(env_file if env_file else None)
    pretty = ' '.join(shlex.quote(p) for p in cmd)

    print(f"Working folder: {folder}")
    if full_env_path:
        print(f"env-file: {full_env_path}")
    print(f"Command: {pretty}")

    if parsed.dry_run:
        print("Dry-run mode, not executing.")
        return 0

    if not os.path.isdir(folder):
        print(f"Error: folder does not exist: {folder}")
        return 2

    if full_env_path and not os.path.exists(full_env_path):
        print(f"Warning: env-file not found at {full_env_path}. Docker will error if it requires it.")

    try:
        proc = run_command(cmd, cwd=folder)
    except RuntimeError as re:
        print(str(re))
        return 3

    print("Started docker process, streaming logs (CTRL-C to exit)...")
    try:
        for line in proc.stdout:
            print(line, end='')
    except KeyboardInterrupt:
        print("Interrupted by user, terminating docker process...")
        try:
            proc.terminate()
        except Exception:
            pass
    return 0

if __name__ == '__main__':
    raise SystemExit(cli_main(sys.argv[1:]))
