"""Install a checksum-pinned official Stockfish release, without Python packages."""

import argparse
import hashlib
import os
from pathlib import Path
import platform
import shutil
import tarfile
import tempfile
import urllib.request
import zipfile


VERSION = "19"
# SHA-256 digests published on the official sf_19 GitHub release assets.
ASSETS = {
    ("Linux", "x86_64"): ("stockfish-linux-x86-64-universal.tar.gz", "9defc0d4e55d49c65a6d042f3e571a39fcea499ade6dbe741b53b8c65e03611f"),
    ("Linux", "aarch64"): ("stockfish-linux-arm64-universal.tar.gz", "fe26cfd1d9db4c8af3d21e24d9ff34cacb31c1f940085a7583da11796f2bac01"),
    ("Windows", "x86_64"): ("stockfish-windows-x86-64-universal.zip", "3c8bf1f9ea66a09350a40df4f632288285ac206d99f33ab5842c408fc30b48a7"),
    ("Windows", "aarch64"): ("stockfish-windows-arm64-universal.zip", "8372ad3f0d7276deb2c70f801f541ec7db463219fc6d9c7592864e542aa4f401"),
}


def install(destination: Path) -> Path:
    machine = platform.machine().lower()
    machine = {"amd64": "x86_64", "arm64": "aarch64"}.get(machine, machine)
    try:
        name, digest = ASSETS[(platform.system(), machine)]
    except KeyError as exc:
        raise RuntimeError("This platform needs a manual Stockfish installation and STOCKFISH_PATH.") from exc
    marker = destination / "executable.txt"
    if marker.is_file():
        executable = destination / marker.read_text(encoding="utf-8").strip()
        if executable.is_file():
            return executable
    if destination.exists():
        raise RuntimeError(f"Destination already exists without a complete installation: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="stockfish-download-", dir=destination.parent) as temporary:
        root = Path(temporary)
        archive = root / name
        url = f"https://github.com/official-stockfish/Stockfish/releases/download/sf_{VERSION}/{name}"
        print(f"Downloading official Stockfish {VERSION}: {name}", flush=True)
        with urllib.request.urlopen(url, timeout=120) as response, archive.open("wb") as output:
            shutil.copyfileobj(response, output)
        with archive.open("rb") as source:
            actual = hashlib.file_digest(source, "sha256").hexdigest()
        if actual != digest:
            raise RuntimeError("Stockfish archive checksum did not match the pinned official release.")
        extracted = root / "extracted"
        extracted.mkdir()
        if name.endswith(".zip"):
            with zipfile.ZipFile(archive) as bundle:
                for member in bundle.infolist():
                    if not (extracted / member.filename).resolve().is_relative_to(extracted.resolve()):
                        raise RuntimeError("Unsafe archive path.")
                bundle.extractall(extracted)
        else:
            with tarfile.open(archive) as bundle:
                bundle.extractall(extracted, filter="data")
        executable_name = name.removesuffix(".tar.gz").removesuffix(".zip")
        if platform.system() == "Windows":
            executable_name += ".exe"
        matches = list(extracted.rglob(executable_name))
        if len(matches) != 1:
            raise RuntimeError(f"Expected one {executable_name} in the official archive.")
        executable = matches[0]
        if platform.system() != "Windows":
            executable.chmod(executable.stat().st_mode | 0o111)
        relative = executable.relative_to(extracted)
        (extracted / "executable.txt").write_text(relative.as_posix(), encoding="utf-8")
        (extracted / "release.txt").write_text(f"Stockfish {VERSION}\n{url}\nsha256:{digest}\n", encoding="utf-8")
        # Keep the release's license, source and network files beside the engine.
        os.replace(extracted, destination)
    return destination / relative


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, default=Path(__file__).resolve().parents[1] / ".tools" / "stockfish")
    parser.add_argument("--link", type=Path, help="Optional executable symlink for a Linux image.")
    args = parser.parse_args()
    executable = install(args.destination.resolve())
    if args.link:
        args.link.symlink_to(executable)
    print(f"Stockfish ready: {executable}")


if __name__ == "__main__":
    main()
