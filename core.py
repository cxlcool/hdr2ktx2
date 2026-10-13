from __future__ import annotations

from pathlib import Path
import os
import shutil
import tempfile


SAMPLE_COUNTS = (64, 128, 256, 512, 1024)
CUBE_RESOLUTIONS = (128, 256, 512, 1024, 2048)


def discover_hdr_files(paths: list[str | Path]) -> list[Path]:
    found: dict[str, Path] = {}
    for item in paths:
        path = Path(item)
        candidates = path.rglob("*") if path.is_dir() else (path,)
        for candidate in candidates:
            if candidate.is_file() and candidate.suffix.casefold() == ".hdr":
                found.setdefault(str(candidate.resolve()).casefold(), candidate.resolve())
    return sorted(found.values(), key=lambda path: str(path).casefold())


def build_cli_arguments(
    executable: Path,
    source: Path,
    destination: Path,
    lut_path: Path,
    sample_count: int,
    cube_resolution: int,
    mip_levels: int,
) -> list[str]:
    if sample_count not in SAMPLE_COUNTS:
        raise ValueError("Unsupported sample count")
    if cube_resolution not in CUBE_RESOLUTIONS:
        raise ValueError("Unsupported cube-map resolution")
    max_mips = cube_resolution.bit_length()
    if not 1 <= mip_levels <= max_mips:
        raise ValueError(f"Mip levels must be between 1 and {max_mips}")
    return [
        str(executable),
        "-inputPath",
        str(source),
        "-outCubeMap",
        str(destination),
        "-outLUT",
        str(lut_path),
        "-distribution",
        "GGX",
        "-sampleCount",
        str(sample_count),
        "-cubeMapResolution",
        str(cube_resolution),
        "-mipLevelCount",
        str(mip_levels),
        "-targetFormat",
        "R16G16B16A16_SFLOAT",
    ]


def validate_ktx2(path: Path) -> bool:
    try:
        with path.open("rb") as file:
            return file.read(12) == bytes.fromhex("AB4B5458203230BB0D0A1A0A")
    except OSError:
        return False


def ascii_temp_directory() -> tempfile.TemporaryDirectory[str]:
    candidates = [Path(tempfile.gettempdir()), Path(os.environ.get("SystemRoot", r"C:\Windows")) / "Temp"]
    last_error: OSError | None = None
    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            candidate_text = str(candidate.resolve())
            candidate_text.encode("ascii")
            return tempfile.TemporaryDirectory(prefix="hdr2ktx2-", dir=candidate_text)
        except (OSError, UnicodeEncodeError) as error:
            if isinstance(error, OSError):
                last_error = error
    raise OSError("No writable ASCII-only temporary directory is available") from last_error


def publish_output(staged_output: Path, destination: Path, overwrite: bool) -> None:
    if destination.exists() and not overwrite:
        raise FileExistsError(f"Target file already exists: {destination}")
    pending = destination.with_name(f".{destination.name}.hdr2ktx2-pending")
    try:
        shutil.copyfile(staged_output, pending)
        if destination.exists() and not overwrite:
            raise FileExistsError(f"Target file already exists: {destination}")
        os.replace(pending, destination)
    finally:
        pending.unlink(missing_ok=True)
