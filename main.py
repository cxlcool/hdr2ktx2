from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QFont
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core import (
    CUBE_RESOLUTIONS,
    SAMPLE_COUNTS,
    ascii_temp_directory,
    build_cli_arguments,
    discover_hdr_files,
    publish_output,
    validate_ktx2,
)


APP_NAME = "HDR2KTX2"
APP_VERSION = json.loads((Path(__file__).parent / "version.json").read_text(encoding="utf-8"))["version"]
KTX2_MAGIC = bytes.fromhex("AB4B5458203230BB0D0A1A0A")


def resource_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "bundle"
    return Path(__file__).parent / "bundle"


class DropFrame(QFrame):
    files_dropped = Signal(list)

    def __init__(self) -> None:
        super().__init__()
        self.setAcceptDrops(True)
        self.setObjectName("dropFrame")
        self.setMinimumHeight(88)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        title = QLabel("拖放 HDR 文件到这里")
        title.setObjectName("dropTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle = QLabel("支持 .hdr 文件，可一次添加多个文件")
        subtitle.setObjectName("muted")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        layout.addWidget(subtitle)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        self.files_dropped.emit(paths)
        event.acceptProposedAction()


class ConversionWorker(QThread):
    progress = Signal(int, int, str)
    log_line = Signal(str)
    item_finished = Signal(str, bool, str)
    finished_all = Signal()

    def __init__(
        self,
        jobs: list[tuple[Path, Path]],
        sample_count: int,
        cube_resolution: int,
        mip_levels: int,
        overwrite: bool,
    ) -> None:
        super().__init__()
        self.jobs = jobs
        self.sample_count = sample_count
        self.cube_resolution = cube_resolution
        self.mip_levels = mip_levels
        self.overwrite = overwrite
        self._cancel_requested = False

    def cancel(self) -> None:
        self._cancel_requested = True

    def run(self) -> None:
        root = resource_root()
        executable = root / "cli.exe"
        if not executable.is_file():
            self.log_line.emit("错误：内置转换程序 cli.exe 不存在。")
            self.finished_all.emit()
            return

        completed = 0
        for index, (source, destination) in enumerate(self.jobs, start=1):
            if self._cancel_requested:
                break
            self.progress.emit(index - 1, len(self.jobs), source.name)
            if destination.exists() and not self.overwrite:
                self.item_finished.emit(str(source), False, f"目标文件已存在，已跳过：{destination}")
                completed += 1
                self.progress.emit(completed, len(self.jobs), source.name)
                continue

            destination.parent.mkdir(parents=True, exist_ok=True)
            try:
                self.log_line.emit(f"开始：{source}")
                with ascii_temp_directory() as temporary_root:
                    staging = Path(temporary_root)
                    staged_input = staging / "input.hdr"
                    staged_output = staging / "output.ktx2"
                    lut_path = staging / "lut.png"
                    shutil.copyfile(source, staged_input)
                    arguments = build_cli_arguments(
                        executable,
                        staged_input,
                        staged_output,
                        lut_path,
                        self.sample_count,
                        self.cube_resolution,
                        self.mip_levels,
                    )
                    process = subprocess.Popen(
                        arguments,
                        cwd=root,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        bufsize=1,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                    assert process.stdout is not None
                    for line in process.stdout:
                        self.log_line.emit(line.rstrip())
                        if self._cancel_requested and process.poll() is None:
                            process.terminate()
                    exit_code = process.wait()
                    success = exit_code == 0 and validate_ktx2(staged_output)
                    if success:
                        publish_output(staged_output, destination, self.overwrite)
                if success:
                    self.item_finished.emit(str(source), True, f"完成：{destination} ({destination.stat().st_size:,} bytes)")
                else:
                    reason = f"CLI 退出码 {exit_code}，或输出不是有效 KTX2。"
                    self.item_finished.emit(str(source), False, f"失败：{source}；{reason}")
                completed += 1
            except (OSError, ValueError) as error:
                self.item_finished.emit(str(source), False, f"失败：{source}；{error}")
                completed += 1
            finally:
                self.progress.emit(completed, len(self.jobs), source.name)

        if self._cancel_requested:
            self.log_line.emit("已请求取消；当前任务结束后停止队列。")
        self.finished_all.emit()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        self.setMinimumSize(820, 760)
        self.resize(920, 820)
        self.setAcceptDrops(True)
        self._worker: ConversionWorker | None = None
        self._build_ui()
        self._apply_style()

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        page = QVBoxLayout(central)
        page.setContentsMargins(28, 22, 28, 22)
        page.setSpacing(14)

        header = QHBoxLayout()
        brand = QVBoxLayout()
        title = QLabel("HDR2KTX2")
        title.setObjectName("appTitle")
        subtitle = QLabel("HDR 环境图 · IBL 预滤波立方体贴图")
        subtitle.setObjectName("muted")
        brand.addWidget(title)
        brand.addWidget(subtitle)
        header.addLayout(brand)
        header.addStretch(1)
        self.version_badge = QLabel(APP_VERSION)
        self.version_badge.setObjectName("versionBadge")
        header.addWidget(self.version_badge, alignment=Qt.AlignmentFlag.AlignTop)
        page.addLayout(header)

        note = QLabel("输出为六面立方体环境贴图 KTX2（RGBA16F），包含 GGX 预滤波与 mip 级别；不是等尺寸全景图封装。需要支持 Vulkan 的显卡及驱动。")
        note.setWordWrap(True)
        note.setObjectName("infoNote")
        page.addWidget(note)

        self.drop_frame = DropFrame()
        self.drop_frame.files_dropped.connect(self._add_paths)
        page.addWidget(self.drop_frame)

        actions = QHBoxLayout()
        self.add_files_button = QPushButton("添加 HDR 文件")
        self.add_folder_button = QPushButton("添加文件夹")
        self.remove_button = QPushButton("移除所选")
        self.clear_button = QPushButton("清空列表")
        actions.addWidget(self.add_files_button)
        actions.addWidget(self.add_folder_button)
        actions.addStretch(1)
        actions.addWidget(self.remove_button)
        actions.addWidget(self.clear_button)
        page.addLayout(actions)

        self.file_list = QListWidget()
        self.file_list.setObjectName("fileList")
        self.file_list.setMinimumHeight(130)
        self.file_list.setMaximumHeight(200)
        page.addWidget(self.file_list)

        output_row = QHBoxLayout()
        output_row.addWidget(QLabel("输出目录"))
        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText("留空：每个 .ktx2 与对应 .hdr 保存在同一目录")
        self.output_button = QPushButton("浏览…")
        self.output_clear_button = QPushButton("清除")
        output_row.addWidget(self.output_edit, 1)
        output_row.addWidget(self.output_button)
        output_row.addWidget(self.output_clear_button)
        page.addLayout(output_row)

        settings = QGridLayout()
        settings.setHorizontalSpacing(12)
        settings.setVerticalSpacing(6)
        self.samples_combo = QComboBox()
        self.samples_combo.addItems([str(value) for value in SAMPLE_COUNTS])
        self.samples_combo.setCurrentText("128")
        self.resolution_combo = QComboBox()
        self.resolution_combo.addItems([str(value) for value in CUBE_RESOLUTIONS])
        self.resolution_combo.setCurrentText("512")
        self.mips_spin = QSpinBox()
        self.mips_spin.setRange(1, 10)
        self.mips_spin.setValue(10)
        self.overwrite_check = QCheckBox("覆盖已存在的 KTX2 文件")
        settings.addWidget(QLabel("采样数"), 0, 0)
        settings.addWidget(self.samples_combo, 1, 0)
        settings.addWidget(QLabel("立方体分辨率"), 0, 1)
        settings.addWidget(self.resolution_combo, 1, 1)
        settings.addWidget(QLabel("Mip 级别数"), 0, 2)
        settings.addWidget(self.mips_spin, 1, 2)
        settings.addWidget(self.overwrite_check, 1, 3)
        settings.setColumnStretch(3, 1)
        page.addLayout(settings)

        progress_row = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.progress_label = QLabel("就绪")
        self.progress_label.setObjectName("muted")
        progress_row.addWidget(self.progress_bar, 1)
        progress_row.addWidget(self.progress_label)
        page.addLayout(progress_row)

        footer = QHBoxLayout()
        self.status_label = QLabel("请选择 HDR 文件开始")
        self.status_label.setObjectName("muted")
        self.convert_button = QPushButton("开始转换")
        self.convert_button.setObjectName("primaryButton")
        self.convert_button.setMinimumWidth(150)
        self.cancel_button = QPushButton("取消")
        self.cancel_button.setEnabled(False)
        footer.addWidget(self.status_label, 1)
        footer.addWidget(self.cancel_button)
        footer.addWidget(self.convert_button)
        page.addLayout(footer)

        log_title = QLabel("运行日志")
        log_title.setObjectName("sectionTitle")
        page.addWidget(log_title)
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMinimumHeight(125)
        self.log_view.setPlaceholderText("转换过程和错误信息会显示在这里。")
        page.addWidget(self.log_view, 1)

        self.add_files_button.clicked.connect(self._pick_files)
        self.add_folder_button.clicked.connect(self._pick_folder)
        self.remove_button.clicked.connect(self._remove_selected)
        self.clear_button.clicked.connect(self.file_list.clear)
        self.output_button.clicked.connect(self._pick_output)
        self.output_clear_button.clicked.connect(self.output_edit.clear)
        self.convert_button.clicked.connect(self._start_conversion)
        self.cancel_button.clicked.connect(self._cancel_conversion)
        self.resolution_combo.currentTextChanged.connect(self._update_mip_limit)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget { background: #f5f7fb; color: #172033; font-family: 'Segoe UI', 'Microsoft YaHei UI'; font-size: 10pt; }
            QLabel#appTitle { font-size: 23pt; font-weight: 700; color: #121a2b; }
            QLabel#muted { color: #68758b; }
            QLabel#versionBadge { background: #e7edff; color: #3659c9; border-radius: 12px; padding: 7px 12px; font-weight: 700; }
            QLabel#infoNote { background: #eef3ff; color: #3d507b; border: 1px solid #dce5fb; border-radius: 10px; padding: 11px 13px; }
            QLabel#sectionTitle { font-size: 11pt; font-weight: 700; }
            QFrame#dropFrame { background: #ffffff; border: 2px dashed #b7c4df; border-radius: 12px; }
            QLabel#dropTitle { font-size: 12pt; font-weight: 700; color: #3659c9; }
            QListWidget, QTextEdit, QLineEdit, QComboBox, QSpinBox { background: #ffffff; border: 1px solid #dce2ed; border-radius: 8px; padding: 7px; selection-background-color: #dce6ff; }
            QListWidget::item { padding: 5px; }
            QPushButton { background: #ffffff; border: 1px solid #d7deea; border-radius: 8px; padding: 8px 12px; }
            QPushButton:hover { background: #eef3ff; border-color: #b4c5f5; }
            QPushButton:disabled { color: #9aa4b5; background: #edf0f5; }
            QPushButton#primaryButton { background: #3e63dd; color: white; border: none; font-weight: 700; padding: 10px 16px; }
            QPushButton#primaryButton:hover { background: #3155cc; }
            QProgressBar { background: #e8ecf3; border: none; border-radius: 6px; height: 12px; text-align: center; }
            QProgressBar::chunk { background: #4a6de0; border-radius: 6px; }
            QCheckBox { spacing: 7px; }
            """
        )

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        self._add_paths(paths)
        event.acceptProposedAction()

    def _pick_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "选择 HDR 文件", "", "HDR 全景图 (*.hdr)")
        self._add_paths(paths)

    def _pick_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "选择包含 HDR 文件的文件夹")
        if folder:
            self._add_paths([folder])

    def _add_paths(self, paths: list[str]) -> None:
        files = discover_hdr_files(paths)
        existing = {self.file_list.item(index).data(Qt.ItemDataRole.UserRole).casefold() for index in range(self.file_list.count())}
        added = 0
        for path in files:
            key = str(path).casefold()
            if key in existing:
                continue
            item = QListWidgetItem(f"{path.name}    —    {path.parent}")
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            item.setToolTip(str(path))
            self.file_list.addItem(item)
            existing.add(key)
            added += 1
        if paths and not files:
            self._append_log("所选路径中没有找到 .hdr 文件。")
        elif added:
            self.status_label.setText(f"已添加 {added} 个 HDR 文件")

    def _remove_selected(self) -> None:
        for item in self.file_list.selectedItems():
            self.file_list.takeItem(self.file_list.row(item))

    def _pick_output(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "选择 KTX2 输出文件夹")
        if folder:
            self.output_edit.setText(folder)

    def _update_mip_limit(self, value: str) -> None:
        max_mips = int(value).bit_length()
        current = min(self.mips_spin.value(), max_mips)
        self.mips_spin.setRange(1, max_mips)
        self.mips_spin.setValue(current)

    def _build_jobs(self) -> list[tuple[Path, Path]]:
        sources = [Path(self.file_list.item(index).data(Qt.ItemDataRole.UserRole)) for index in range(self.file_list.count())]
        output_root = self.output_edit.text().strip()
        jobs: list[tuple[Path, Path]] = []
        destinations: set[str] = set()
        for source in sources:
            parent = Path(output_root) if output_root else source.parent
            destination = parent / f"{source.stem}.ktx2"
            key = str(destination.resolve()).casefold()
            if key in destinations:
                raise ValueError(f"多个输入会写入同一输出文件：{destination}")
            destinations.add(key)
            if destination.exists() and not self.overwrite_check.isChecked():
                continue
            jobs.append((source, destination))
        return jobs

    def _start_conversion(self) -> None:
        if self._worker and self._worker.isRunning():
            return
        try:
            jobs = self._build_jobs()
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "无法开始转换", str(error))
            return
        if not jobs:
            QMessageBox.information(self, "没有待转换文件", "请添加 HDR 文件，或勾选覆盖已存在文件。")
            return

        self.progress_bar.setRange(0, len(jobs))
        self.progress_bar.setValue(0)
        self.log_view.clear()
        self.status_label.setText(f"正在处理 {len(jobs)} 个文件…")
        self._set_busy(True)
        self._worker = ConversionWorker(
            jobs,
            int(self.samples_combo.currentText()),
            int(self.resolution_combo.currentText()),
            self.mips_spin.value(),
            self.overwrite_check.isChecked(),
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.log_line.connect(self._append_log)
        self._worker.item_finished.connect(self._on_item_finished)
        self._worker.finished_all.connect(self._on_finished)
        self._worker.start()

    def _cancel_conversion(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self.cancel_button.setEnabled(False)
            self.status_label.setText("正在停止当前任务…")

    def _on_progress(self, completed: int, total: int, name: str) -> None:
        self.progress_bar.setValue(completed)
        self.progress_label.setText(f"{completed}/{total}")
        if completed < total:
            self.status_label.setText(f"正在处理：{name}")

    def _on_item_finished(self, source: str, success: bool, message: str) -> None:
        self._append_log(message)
        color = "#1e8e5a" if success else "#bd4343"
        for index in range(self.file_list.count()):
            item = self.file_list.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == source:
                item.setForeground(color)
                break

    def _on_finished(self) -> None:
        self._set_busy(False)
        self.status_label.setText("转换任务结束")
        self._append_log("队列处理结束。")

    def _set_busy(self, busy: bool) -> None:
        for widget in (self.add_files_button, self.add_folder_button, self.remove_button, self.clear_button, self.convert_button):
            widget.setEnabled(not busy)
        self.cancel_button.setEnabled(busy)

    def _append_log(self, text: str) -> None:
        self.log_view.append(text.replace("<", "&lt;").replace(">", "&gt;"))

    def closeEvent(self, event) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(5000)
        event.accept()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setFont(QFont("Microsoft YaHei UI", 10))
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
