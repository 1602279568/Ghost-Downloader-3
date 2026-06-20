"""下载完成弹窗 —— 独立的置顶窗口, 替代原右下角桌面通知。

不依附任何父窗口: 即使 Ghost Downloader 主窗口最小化也能浮在最前。
窗口显示文件名、保存路径、文件大小、下载耗时, 配「打开文件」「打开文件夹」
两个动作按钮。沿用项目现有 openFile / openFolder, 不引入新依赖。
"""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPainter
from PySide6.QtWidgets import (
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
)

_APP_ICON = QIcon(":/image/logo.png")
from qfluentwidgets import (
    BodyLabel,
    FluentIcon,
    IconWidget,
    PrimaryPushButton,
    PushButton,
    StrongBodyLabel,
    SubtitleLabel,
    isDarkTheme,
    qconfig,
)

from app.bases.models import Task
from app.supports.utils import openFile, openFolder, toReadableSize, toReadableTime


class DownloadFinishedWindow(QWidget):
    """置顶的「下载完成」窗口 (Fluent Design 风格)。

    无父窗口的独立 QWidget, 通过 ``WindowStaysOnTopHint`` 始终浮在最前。
    点击按钮执行动作后自动关闭。

    Args:
        task: 刚刚完成的任务, 用其 title / outputFolder / fileSize / createdAt
            填充内容。下载耗时按 ``time_ns() - task.createdAt`` 计算。
    """

    def __init__(self, task: Task):
        super().__init__(None)
        self.task = task
        self._filePath = task.outputFolder or ""
        self._folder = (
            str(Path(self._filePath).parent) if self._filePath else str(task.path)
        )

        self.setWindowTitle(self.tr("下载完成"))
        self.setWindowIcon(_APP_ICON)
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        # 关闭即销毁, 避免游离窗口泄漏
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        # 独立顶层 QWidget 不会自动套用 Fluent 暗色背景, 这里关闭自动填充,
        # 改由 paintEvent 按主题绘制背景, 否则暗色模式下底色恒为系统白
        self.setAutoFillBackground(False)
        self.setMinimumWidth(420)

        self._buildUi()
        self._connectSignals()

    def _buildUi(self):
        from time import time_ns

        # 内容
        fileNameText = self.task.title or ""
        sizeText = toReadableSize(self.task.fileSize) if self.task.fileSize else "--"
        # createdAt 单位: 纳秒 (time_ns())
        elapsedSeconds = max(0, int((time_ns() - self.task.createdAt) / 1_000_000_000))
        durationText = toReadableTime(elapsedSeconds)

        # 头部: 图标 + 标题
        self.iconLabel = IconWidget(FluentIcon.ACCEPT, self)
        self.iconLabel.setFixedSize(32, 32)
        self.titleLabel = SubtitleLabel(self.tr("下载完成"), self)

        headerLayout = QHBoxLayout()
        headerLayout.setContentsMargins(0, 0, 0, 0)
        headerLayout.setSpacing(12)
        headerLayout.addWidget(self.iconLabel, 0, Qt.AlignmentFlag.AlignVCenter)
        headerLayout.addWidget(self.titleLabel, 1, Qt.AlignmentFlag.AlignVCenter)

        # 文件名 (加粗主标题)
        self.fileNameLabel = StrongBodyLabel(fileNameText, self)
        self.fileNameLabel.setWordWrap(True)

        # 详情: 路径 / 大小 / 耗时
        # 次要文字颜色需随主题切换, 否则暗色模式下黑字贴黑底会看不见
        self._secondaryLabels: list[BodyLabel] = []

        self.pathValueLabel = BodyLabel(self._folder, self)
        self.pathValueLabel.setWordWrap(True)
        self._secondaryLabels.append(self.pathValueLabel)

        self.sizeLabel = BodyLabel(self.tr("大小"), self)
        self.sizeValueLabel = BodyLabel(sizeText, self)

        self.durationLabel = BodyLabel(self.tr("耗时"), self)
        self.durationValueLabel = BodyLabel(durationText, self)

        # 两列详情 (大小 / 耗时)
        detailLayout = QHBoxLayout()
        detailLayout.setContentsMargins(0, 0, 0, 0)
        detailLayout.setSpacing(16)
        for labelText, valueLabel in (
            (self.sizeLabel, self.sizeValueLabel),
            (self.durationLabel, self.durationValueLabel),
        ):
            self._secondaryLabels.append(labelText)
            column = QVBoxLayout()
            column.setContentsMargins(0, 0, 0, 0)
            column.setSpacing(2)
            column.addWidget(labelText)
            column.addWidget(valueLabel)
            detailLayout.addLayout(column)
        detailLayout.addStretch(1)

        # 按钮
        self.openFileButton = PrimaryPushButton(
            FluentIcon.DOCUMENT.icon(), self.tr("打开文件"), self
        )
        self.openFolderButton = PushButton(
            FluentIcon.FOLDER.icon(), self.tr("打开文件夹"), self
        )
        self.closeButton = PushButton(self.tr("关闭"), self)

        buttonLayout = QHBoxLayout()
        buttonLayout.setContentsMargins(0, 0, 0, 0)
        buttonLayout.setSpacing(8)
        buttonLayout.addWidget(self.openFileButton)
        buttonLayout.addWidget(self.openFolderButton)
        buttonLayout.addStretch(1)
        buttonLayout.addWidget(self.closeButton)

        rootLayout = QVBoxLayout(self)
        rootLayout.setContentsMargins(24, 20, 24, 20)
        rootLayout.setSpacing(10)
        rootLayout.addLayout(headerLayout)
        rootLayout.addSpacing(4)
        rootLayout.addWidget(self.fileNameLabel)
        rootLayout.addSpacing(2)
        rootLayout.addWidget(self.pathValueLabel)
        rootLayout.addSpacing(4)
        rootLayout.addLayout(detailLayout)
        rootLayout.addSpacing(8)
        rootLayout.addLayout(buttonLayout)

        # 初次按当前主题刷新次要文字颜色
        self._applySecondaryTextStyle()

    def _applySecondaryTextStyle(self):
        """按当前主题给次要文字着色。

        浅色: 接近黑的半透明 (rgba 0,0,0,150) —— 原 IDM 风格;
        暗色: 改用接近白的半透明 (rgba 255,255,255,160), 否则黑字贴
        暗色背景几乎不可见。
        """
        color = "rgba(255, 255, 255, 160)" if isDarkTheme() else "rgba(0, 0, 0, 150)"
        style = f"color: {color};"
        for label in self._secondaryLabels:
            label.setStyleSheet(style)

    def paintEvent(self, e):
        """按当前主题绘制窗口背景。

        本窗口是无父窗口的独立 QWidget, 不在 FluentWindow / MessageBoxBase
        体系内, qfluentwidgets 的全局暗色样式表不会作用到它, 所以必须自己
        绘制背景: 浅色白底、暗色 rgb(32,32,32) (与项目内 mobile/window 等
        暗色窗体色值保持一致)。
        """
        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing)
        bgColor = QColor(32, 32, 32) if isDarkTheme() else QColor(255, 255, 255)
        painter.fillRect(self.rect(), bgColor)

    def _connectSignals(self):
        self.openFileButton.clicked.connect(self._openFile)
        self.openFolderButton.clicked.connect(self._openFolder)
        self.closeButton.clicked.connect(self.close)
        # 主题切换时同步刷新背景与次要文字颜色
        qconfig.themeChanged.connect(self.update)
        qconfig.themeChanged.connect(self._applySecondaryTextStyle)

    def _openFile(self):
        if self._filePath:
            openFile(self._filePath)
        self.close()

    def _openFolder(self):
        # openFolder 会在 Windows 上 explorer /select, 选中文件本体 —— IDM 风格
        if self._filePath:
            openFolder(self._filePath)
        elif self._folder:
            openFile(self._folder)
        self.close()


# 持有窗口引用, 防止多任务并发完成时早期窗口被 Python GC 回收
_activeWindows: list[QWidget] = []


def showDownloadFinishedWindow(task: Task) -> None:
    """创建并显示一个独立的置顶「下载完成」窗口。

    无父窗口、非模态, 即使主窗口最小化也能浮在最前。窗口自带
    ``WA_DeleteOnClose``; 关闭时会从 ``_activeWindows`` 中移除自身。
    """
    window = DownloadFinishedWindow(task)
    window.destroyed.connect(lambda *_: _onWindowDestroyed(window))
    _activeWindows.append(window)
    window.show()
    window.raise_()
    window.activateWindow()


def _onWindowDestroyed(window: QWidget) -> None:
    try:
        _activeWindows.remove(window)
    except ValueError:
        pass
