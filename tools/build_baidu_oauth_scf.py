from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path


def build_scf_package(root: Path) -> Path:
    source = root / "cloud" / "baidu_oauth_callback"
    build_dir = source / "build"
    dist_dir = source / "dist"
    output = dist_dir / "baidu_oauth_callback_scf.zip"
    if build_dir.exists():
        shutil.rmtree(build_dir)
    build_dir.mkdir(parents=True)
    dist_dir.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()

    for name in ("index.py", "app.py", "scf_bootstrap"):
        shutil.copy2(source / name, build_dir / name)
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--requirement",
            str(source / "requirements.txt"),
            "--target",
            str(build_dir),
            "--platform",
            "manylinux2014_x86_64",
            "--implementation",
            "cp",
            "--python-version",
            "3.6",
            "--only-binary=:all:",
            "--disable-pip-version-check",
        ],
        check=True,
    )

    # pip includes package self-tests, bytecode for the build host, and install
    # metadata. They are unnecessary at runtime; self-tests also include sample
    # private keys that should not be shipped in a production deployment.
    for path in list(build_dir.rglob("*")):
        if not path.is_dir():
            continue
        if path.name == "__pycache__" or path.name.endswith(".dist-info"):
            shutil.rmtree(path)
    self_tests = build_dir / "Crypto" / "SelfTest"
    if self_tests.exists():
        shutil.rmtree(self_tests)
    for path in build_dir.rglob("*.pyc"):
        path.unlink()

    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in build_dir.rglob("*"):
            if path.is_file():
                relative = path.relative_to(build_dir).as_posix()
                if relative == "scf_bootstrap":
                    info = zipfile.ZipInfo(relative)
                    info.create_system = 3
                    info.external_attr = 0o100755 << 16
                    info.compress_type = zipfile.ZIP_DEFLATED
                    archive.writestr(info, path.read_bytes())
                else:
                    archive.write(path, relative)
    shutil.rmtree(build_dir)
    return output


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    output = build_scf_package(root)
    print(f"SCF 部署包已生成：{output}")
    print(f"大小：{output.stat().st_size / 1024 / 1024:.2f} MB")


if __name__ == "__main__":
    main()
