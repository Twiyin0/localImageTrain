from __future__ import annotations

import argparse
import os
import shlex
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path


RSYNC_EXCLUDES = [
    ".git/",
    ".venv/",
    ".cache/",
    "models/",
    "outputs/",
    "logs/",
    ".env*",
    "__pycache__/",
    ".pytest_cache/",
    ".mypy_cache/",
    "*.pyc",
    ".DS_Store",
    "._*",
]


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Deploy WD Tagger API and static WebUI to a remote NAS over SSH")
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


def build_ssh_base(args: argparse.Namespace) -> list[str]:
    ssh = shutil.which("ssh")
    if not ssh:
        raise RuntimeError("ssh is not available on this machine")
    return [
        ssh,
        "-p",
        str(args.port),
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "UserKnownHostsFile=/dev/null",
        "-o",
        "PreferredAuthentications=password",
        "-o",
        "PubkeyAuthentication=no",
        f"{args.username}@{args.host}",
    ]


@contextmanager
def ssh_env(password: str):
    with tempfile.TemporaryDirectory() as tmpdir:
        askpass = Path(tmpdir) / "ssh-askpass.sh"
        askpass.write_text(
            "#!/bin/sh\n"
            f"printf '%s\\n' {shlex.quote(password)}\n",
            encoding="utf-8",
        )
        askpass.chmod(0o700)

        env = os.environ.copy()
        env["SSH_ASKPASS"] = str(askpass)
        env["SSH_ASKPASS_REQUIRE"] = "force"
        env["DISPLAY"] = env.get("DISPLAY") or "codex-askpass"
        yield env


def run_remote(args: argparse.Namespace, command: str, *, env: dict[str, str]) -> tuple[int, str, str]:
    result = subprocess.run(
        build_ssh_base(args) + [command],
        check=False,
        capture_output=True,
        env=env,
        stdin=subprocess.DEVNULL,
        text=True,
    )
    return result.returncode, result.stdout, result.stderr


def print_remote_output(stdout: str, stderr: str) -> None:
    if stdout.strip():
        print(stdout, end="" if stdout.endswith("\n") else "\n")
    if stderr.strip():
        print(stderr, end="" if stderr.endswith("\n") else "\n")


def ensure_remote_dir(args: argparse.Namespace, *, env: dict[str, str]) -> None:
    code, out, err = run_remote(args, f"mkdir -p {shlex.quote(args.remote_dir)}", env=env)
    print_remote_output(out, err)
    if code != 0:
        raise RuntimeError(f"Remote directory creation failed with exit code {code}")


def sync_with_rsync(args: argparse.Namespace, local_root: Path, *, env: dict[str, str]) -> None:
    rsync = shutil.which("rsync")
    if not rsync:
        raise RuntimeError("rsync is not available on this machine")

    local_source = f"{local_root.as_posix().rstrip('/')}/"
    remote_target = f"{args.username}@{args.host}:{args.remote_dir.rstrip('/')}/"
    ssh_transport = build_ssh_base(args)[:-1]

    rsync_cmd = [rsync, "-az", "--delete"]
    for pattern in RSYNC_EXCLUDES:
        rsync_cmd.extend(["--exclude", pattern])
    rsync_cmd.extend(["-e", shlex.join(ssh_transport), local_source, remote_target])

    print("sync> " + shlex.join(rsync_cmd))
    subprocess.run(rsync_cmd, check=True, env=env, stdin=subprocess.DEVNULL)


def upload_env_file(args: argparse.Namespace, local_root: Path, *, env: dict[str, str]) -> None:
    local_env = local_root / ".env.nas"
    if not local_env.is_file():
        return

    with local_env.open("r", encoding="utf-8") as handle:
        content = handle.read()

    remote_env = shlex.quote(args.remote_dir.rstrip("/") + "/.env.nas")
    result = subprocess.run(
        build_ssh_base(args) + [f"cat > {remote_env} && chmod 600 {remote_env}"],
        input=content,
        check=False,
        capture_output=True,
        env=env,
        text=True,
    )
    print_remote_output(result.stdout, result.stderr)
    if result.returncode != 0:
        raise RuntimeError(f"Remote env upload failed with exit code {result.returncode}")


def choose_compose_command(args: argparse.Namespace, *, env: dict[str, str]) -> str:
    for candidate in ("docker compose", "docker-compose"):
        code, _, _ = run_remote(args, f"{candidate} version", env=env)
        if code == 0:
            return candidate
    raise RuntimeError("Neither 'docker compose' nor 'docker-compose' is available on the remote host")


def main() -> None:
    args = build_arg_parser().parse_args()
    local_root = Path(args.local_dir).resolve()
    if not local_root.exists():
        raise RuntimeError(f"Local directory does not exist: {local_root}")

    with ssh_env(args.password) as env:
        ensure_remote_dir(args, env=env)
        if args.no_upload:
            print("skip upload: using files already present on remote host")
        else:
            sync_with_rsync(args, local_root, env=env)
            upload_env_file(args, local_root, env=env)

        code, out, err = run_remote(args, "docker rm -f wd-tagger-webui >/dev/null 2>&1 || true", env=env)
        print_remote_output(out, err)
        if code != 0:
            raise RuntimeError(f"Remote container cleanup failed with exit code {code}")

        compose_cmd = choose_compose_command(args, env=env)
        remote_dir = shlex.quote(args.remote_dir)
        commands = [
            f"cd {remote_dir} && {compose_cmd} -f compose.nas.yml up -d --build --remove-orphans",
            f"cd {remote_dir} && {compose_cmd} -f compose.nas.yml ps",
        ]
        for command in commands:
            print(f"remote> {command}")
            code, out, err = run_remote(args, command, env=env)
            print_remote_output(out, err)
            if code != 0:
                raise RuntimeError(f"Remote command failed with exit code {code}: {command}")


if __name__ == "__main__":
    main()
