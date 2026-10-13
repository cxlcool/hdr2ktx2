from pathlib import Path
import tempfile
import unittest

from core import ascii_temp_directory, build_cli_arguments, discover_hdr_files, publish_output, validate_ktx2


class CoreTests(unittest.TestCase):
    def test_build_cli_arguments_preserves_unicode_paths(self) -> None:
        arguments = build_cli_arguments(
            Path("cli.exe"),
            Path("D:/素材/环境.hdr"),
            Path("D:/输出/环境.ktx2"),
            Path("D:/临时/lut.png"),
            128,
            512,
            10,
        )
        self.assertIn(str(Path("D:/素材/环境.hdr")), arguments)
        self.assertIn(str(Path("D:/输出/环境.ktx2")), arguments)

    def test_rejects_invalid_mip_level_count(self) -> None:
        with self.assertRaises(ValueError):
            build_cli_arguments(Path("cli.exe"), Path("in.hdr"), Path("out.ktx2"), Path("lut.png"), 128, 128, 9)

    def test_discovers_hdr_files_recursively_case_insensitively(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "a.hdr").touch()
            nested = root / "nested"
            nested.mkdir()
            (nested / "b.HDR").touch()
            (nested / "c.png").touch()
            files = discover_hdr_files([root])
            self.assertEqual({file.name.casefold() for file in files}, {"a.hdr", "b.hdr"})

    def test_validates_ktx2_identifier(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "valid.ktx2"
            path.write_bytes(bytes.fromhex("AB4B5458203230BB0D0A1A0A") + b"payload")
            self.assertTrue(validate_ktx2(path))

    def test_ascii_temp_directory_supports_native_cli_paths(self) -> None:
        with ascii_temp_directory() as temp:
            self.assertTrue(str(Path(temp).resolve()).isascii())

    def test_publish_output_handles_unicode_destination_and_overwrite_guard(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            staged = root / "staged.ktx2"
            destination = root / "输出.ktx2"
            staged.write_bytes(b"first")
            publish_output(staged, destination, overwrite=False)
            self.assertEqual(destination.read_bytes(), b"first")
            staged.write_bytes(b"second")
            with self.assertRaises(FileExistsError):
                publish_output(staged, destination, overwrite=False)
            publish_output(staged, destination, overwrite=True)
            self.assertEqual(destination.read_bytes(), b"second")


if __name__ == "__main__":
    unittest.main()
