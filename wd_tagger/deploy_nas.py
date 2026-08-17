from __future__ import annotations

import argparse
import posixpath
import tarfile
from io import BytesIO
from pathlib import Path

import paramiko


DEFAULT_EXCLUDES = {
    ".git",
    ".venv",
    ".cache",
    "__pycache__",
    "outputs",
    "models",
    ".pytest_cache",
    ".mypy_cache",
}
EXACT_FILE_EXCLUDES = {
    ".env",
    ".env.nas",
}


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Deploy WD Tagger API and Node WebUI to a remote NAS over SSH")
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, default=22)
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--remote-dir", required=True)
    parser.add_argument("--local-dir", default=".")
    parser.add_argument(
        "--no-upload",
        action="store_true",
        help="Skip uploading local files and only rebuild/restart containers in remote-dir.",
    )
    return parser


def should_skip(path: Path) -> bool:
    parts = set(path.parts)
    if parts & DEFAULT_EXCLUDES:
        return True
    if path.name in EXACT_FILE_EXCLUDES:
        return True
    if path.name.startswith(".codex_"):
        return True
    if path.name.endswith(".pyc"):
        return True
    return False


def build_tar_stream(local_root: Path) -> bytes:
    buffer = BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for local_path in sorted(local_root.rglob("*")):
            rel = local_path.relative_to(local_root)
            if should_skip(rel):
                continue
            tar.add(local_path, arcname=rel.as_posix(), recursive=False)
            print(f"packed {rel.as_posix()}")
    buffer.seek(0)
    return buffer.read()


def run_remote(ssh: paramiko.SSHClient, command: str) -> tuple[int, str, str]:
    stdin, stdout, stderr = ssh.exec_command(command)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    return exit_code, out, err


def stream_tar_to_remote(ssh: paramiko.SSHClient, local_root: Path, remote_root: str) -> None:
    payload = build_tar_stream(local_root)
    command = f"mkdir -p {remote_root} && tar -xzf - -C {remote_root}"
    transport = ssh.get_transport()
    if transport is None:
        raise RuntimeError("SSH transport is not available")
    channel = transport.open_session()
    channel.exec_command(command)
    channel.sendall(payload)
    channel.shutdown_write()
    exit_code = channel.recv_exit_status()
    out = channel.recv(1024 * 1024).decode("utf-8", errors="replace")
    err = channel.recv_stderr(1024 * 1024).decode("utf-8", errors="replace")
    if out.strip():
        print(out)
    if err.strip():
        print(err)
    if exit_code != 0:
        raise RuntimeError(f"Remote archive extract failed with exit code {exit_code}")


def choose_compose_command(ssh: paramiko.SSHClient) -> str:
    for candidate in ("docker compose", "docker-compose"):
        code, _, _ = run_remote(ssh, f"{candidate} version")
        if code == 0:
            return candidate
    raise RuntimeError("Neither 'docker compose' nor 'docker-compose' is available on the remote host")


def main() -> None:
    args = build_arg_parser().parse_args()
    local_root = Path(args.local_dir).resolve()

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(
        hostname=args.host,
        port=args.port,
        username=args.username,
        password=args.password,
        look_for_keys=False,
        allow_agent=False,
        timeout=20,
    )

    try:
        if args.no_upload:
            print("skip upload: using files already present on remote host")
        else:
            stream_tar_to_remote(ssh, local_root, args.remote_dir)

        compose_cmd = choose_compose_command(ssh)
        remote_dir = args.remote_dir
        commands = [
            f"mkdir -p {remote_dir}",
            f"cd {remote_dir} && docker build -t localimagetrain-wd-tagger-api -f Dockerfile.api .",
            f"cd {remote_dir} && docker build -t localimagetrain-wd-tagger-webui -f Dockerfile.webui .",
            f"cd {remote_dir} && {compose_cmd} -f compose.nas.yml up -d --no-build",
            f"cd {remote_dir} && {compose_cmd} -f compose.nas.yml ps",
        ]
        for command in commands:
            print(f"remote> {command}")
            code, out, err = run_remote(ssh, command)
            if out.strip():
                print(out)
            if err.strip():
                print(err)
            if code != 0:
                raise RuntimeError(f"Remote command failed with exit code {code}: {command}")
    finally:
        ssh.close()


if __name__ == "__main__":
    main()
