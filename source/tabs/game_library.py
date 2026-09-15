import os
import time
from PyQt5.QtCore import (
    QAbstractAnimation,
    QEasingCurve,
    QEvent,
    QPointF,
    QPropertyAnimation,
    QRect,
    QRectF,
    Qt,
    QTimer,
    pyqtSignal,
)
from PyQt5.QtGui import QColor, QFont, QPainter, QPen, QPixmap
from PyQt5.QtWidgets import (
    QWidget,
    QLabel,
    QPushButton,
    QCheckBox,
    QScrollArea,
    QGridLayout,
    QVBoxLayout,
    QHBoxLayout,
    QTextEdit,
    QFrame,
    QDialog,
    QSizePolicy,
    QSlider,
)

from source.xzen_engine.posters import sanitize_png_file
from source.xzen_engine.app_state import background_saved_bytes, original_game_size
from source.xzen_engine.compressibility import calculate_savings_preview
from source.xzen_engine.theme import color as theme_color, themed_qss


MIN_CARD_W = 205
MAX_CARD_W = 235
CARD_H_EXTRA = 172
POSTER_W_PADDING = 30
POSTER_ASPECT = 260 / 175
GRID_SPACING = 12

SCROLLBAR_ACCENT = theme_color("accent_soft")

PURPLE_SCROLLBAR_STYLE = themed_qss(f"""
    QScrollBar:vertical {{
        background: #080808;
        width: 11px;
        margin: 0;
        border: none;
        border-radius: 5px;
    }}

    QScrollBar::handle:vertical {{
        background: {SCROLLBAR_ACCENT};
        min-height: 34px;
        border-radius: 5px;
    }}

    QScrollBar::handle:vertical:hover {{
        background: #c8aaff;
    }}

    QScrollBar::add-line:vertical,
    QScrollBar::sub-line:vertical {{
        height: 0;
        background: transparent;
        border: none;
    }}

    QScrollBar::add-page:vertical,
    QScrollBar::sub-page:vertical {{
        background: transparent;
    }}

    QScrollBar:horizontal {{
        background: #080808;
        height: 11px;
        margin: 0;
        border: none;
        border-radius: 5px;
    }}

    QScrollBar::handle:horizontal {{
        background: {SCROLLBAR_ACCENT};
        min-width: 34px;
        border-radius: 5px;
    }}

    QScrollBar::handle:horizontal:hover {{
        background: #c8aaff;
    }}

    QScrollBar::add-line:horizontal,
    QScrollBar::sub-line:horizontal {{
        width: 0;
        background: transparent;
        border: none;
    }}

    QScrollBar::add-page:horizontal,
    QScrollBar::sub-page:horizontal {{
        background: transparent;
    }}
""")

CHECKBOX_STYLE = themed_qss("""
    QCheckBox {
        color: #ffffff;
        font-size: 11px;
        background: transparent;
    }
    QCheckBox::indicator {
        width: 18px;
        height: 18px;
        border-radius: 4px;
        border: 1px solid #2B2640;
        background: #12101C;
    }
    QCheckBox::indicator:hover {
        border-color: #B38AFF;
        background: #181525;
    }
    QCheckBox::indicator:checked {
        background: #9D4EDD;
        border-color: #C071FF;
    }
""")


class PosterLabel(QLabel):
    left_clicked = pyqtSignal()
    right_clicked = pyqtSignal()

    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            self.right_clicked.emit()
            event.accept()
            return
        if event.button() == Qt.LeftButton:
            self.left_clicked.emit()
        super().mousePressEvent(event)


class PosterCropCanvas(QWidget):
    def __init__(self, pixmap, parent=None):
        super().__init__(parent)
        self.pixmap = pixmap
        self.zoom = 1.0
        self.center = QPointF(pixmap.width() / 2, pixmap.height() / 2)
        self.drag_start = None
        self.drag_center = QPointF(self.center)
        self.setMinimumSize(360, 500)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setCursor(Qt.OpenHandCursor)

    def crop_frame(self):
        margin = 28
        available_w = max(1, self.width() - margin * 2)
        available_h = max(1, self.height() - margin * 2)
        frame_h = min(available_h, available_w * 1.5)
        frame_w = frame_h * 2 / 3
        if frame_w > available_w:
            frame_w = available_w
            frame_h = frame_w * 1.5
        x = (self.width() - frame_w) / 2
        y = (self.height() - frame_h) / 2
        return QRectF(x, y, frame_w, frame_h)

    def image_scale(self):
        frame = self.crop_frame()
        min_scale = max(
            frame.width() / max(1, self.pixmap.width()),
            frame.height() / max(1, self.pixmap.height()),
        )
        return max(min_scale, min_scale * self.zoom)

    def image_rect(self):
        frame = self.crop_frame()
        scale = self.image_scale()
        image_w = self.pixmap.width() * scale
        image_h = self.pixmap.height() * scale
        x = frame.center().x() - self.center.x() * scale
        y = frame.center().y() - self.center.y() * scale
        return QRectF(x, y, image_w, image_h)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.fillRect(self.rect(), QColor("#08070D"))

        rect = self.image_rect()
        painter.drawPixmap(
            QRect(int(rect.x()), int(rect.y()), int(rect.width()), int(rect.height())),
            self.pixmap,
        )

        frame = self.crop_frame()
        overlay = QColor(0, 0, 0, 180)
        painter.fillRect(0, 0, self.width(), int(frame.top()), overlay)
        painter.fillRect(0, int(frame.bottom()), self.width(), int(self.height() - frame.bottom()), overlay)
        painter.fillRect(0, int(frame.top()), int(frame.left()), int(frame.height()), overlay)
        painter.fillRect(int(frame.right()), int(frame.top()), int(self.width() - frame.right()), int(frame.height()), overlay)

        pen = QPen(QColor(theme_color("accent_soft")), 2)
        painter.setPen(pen)
        painter.drawRect(frame.toRect())

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_start = event.pos()
            self.drag_center = QPointF(self.center)
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        if self.drag_start is not None:
            scale = self.image_scale()
            delta = event.pos() - self.drag_start
            self.center = QPointF(
                self.drag_center.x() - delta.x() / max(0.0001, scale),
                self.drag_center.y() - delta.y() / max(0.0001, scale),
            )
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_start = None
            self.setCursor(Qt.OpenHandCursor)

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if delta > 0:
            self.zoom = min(4.0, self.zoom * 1.08)
        elif delta < 0:
            self.zoom = max(1.0, self.zoom / 1.08)
        self.update()
        event.accept()

    def set_zoom(self, value):
        self.zoom = max(1.0, min(4.0, float(value)))
        self.update()

    def reset_view(self):
        self.zoom = 1.0
        self.center = QPointF(self.pixmap.width() / 2, self.pixmap.height() / 2)
        self.update()

    def get_cropped_pixmap(self):
        frame = self.crop_frame()
        scale = self.image_scale()
        rect = self.image_rect()

        source_x = (frame.x() - rect.x()) / scale
        source_y = (frame.y() - rect.y()) / scale
        source_w = frame.width() / scale
        source_h = frame.height() / scale

        image = self.pixmap.toImage()
        crop_rect = QRect(int(source_x), int(source_y), int(source_w), int(source_h))
        crop_rect = crop_rect.intersected(QRect(0, 0, image.width(), image.height()))
        cropped = image.copy(crop_rect)
        return QPixmap.fromImage(cropped)


class PosterCropDialog(QDialog):
    def __init__(self, pixmap, title="Adjust Poster", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(460, 680)
        self.result_pixmap = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        self.canvas = PosterCropCanvas(pixmap, self)
        layout.addWidget(self.canvas, stretch=1)

        slider_row = QHBoxLayout()
        slider_label = QLabel("Zoom:")
        slider_label.setStyleSheet("color: #ffffff; font-size: 12px;")
        self.zoom_slider = QSlider(Qt.Horizontal)
        self.zoom_slider.setRange(100, 400)
        self.zoom_slider.setValue(100)
        self.zoom_slider.valueChanged.connect(lambda val: self.canvas.set_zoom(val / 100.0))

        reset_btn = QPushButton("Reset")
        reset_btn.setObjectName("CropButton")
        reset_btn.clicked.connect(self.canvas.reset_view)
        reset_btn.clicked.connect(lambda: self.zoom_slider.setValue(100))

        slider_row.addWidget(slider_label)
        slider_row.addWidget(self.zoom_slider, stretch=1)
        slider_row.addWidget(reset_btn)
        layout.addLayout(slider_row)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("CropCancelButton")
        cancel_btn.clicked.connect(self.reject)

        save_btn = QPushButton("Save Poster")
        save_btn.setObjectName("CropSaveButton")
        save_btn.clicked.connect(self.save_and_accept)

        buttons.addWidget(cancel_btn)
        buttons.addWidget(save_btn)
        layout.addLayout(buttons)

    def save_and_accept(self):
        self.result_pixmap = self.canvas.get_cropped_pixmap()
        self.accept()


class LoadingSpinner(QWidget):
    def __init__(self, parent=None, size=32):
        super().__init__(parent)
        self.size = size
        self.angle = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.rotate)
        self.setFixedSize(size, size)

    def rotate(self):
        self.angle = (self.angle + 30) % 360
        self.update()

    def start(self):
        if not self.timer.isActive():
            self.timer.start(50)

    def stop(self):
        self.timer.stop()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        center = QPointF(self.width() / 2, self.height() / 2)
        radius = (self.width() - 8) / 2
        tick = 4
        accent = QColor(theme_color("accent"))

        for index in range(12):
            opacity = int(255 * (index + 1) / 12)
            color = QColor(accent.red(), accent.green(), accent.blue(), opacity)
            painter.setPen(QPen(color, 4, Qt.SolidLine, Qt.RoundCap))
            painter.save()
            painter.translate(center)
            painter.rotate(self.angle + index * 30)
            painter.drawLine(0, -radius, 0, -radius + tick)
            painter.restore()


class SmoothScrollArea(QScrollArea):
    """
    Optimized kinetic touch & mouse drag scroll area designed for handheld ergonomics (Legion Go).
    Allows vertical flicking, swiping, and inertia momentum deceleration anywhere on the viewport.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self._scroll_target = 0
        self._scroll_animation = QPropertyAnimation(self.verticalScrollBar(), b"value", self)
        self._scroll_animation.setDuration(400)
        self._scroll_animation.setEasingCurve(QEasingCurve.OutCubic)

        # Kinetic Touch & Drag Tracking
        self._is_dragging = False
        self._drag_start_y = 0
        self._last_drag_y = 0
        self._last_drag_time = 0.0
        self._velocity = 0.0
        self._drag_threshold = 8
        self._drag_occurred = False

        if self.viewport():
            self.viewport().installEventFilter(self)

    def eventFilter(self, obj, event):
        if obj == self.viewport():
            event_type = event.type()
            if event_type == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                self._is_dragging = True
                self._drag_start_y = event.pos().y()
                self._last_drag_y = event.pos().y()
                self._last_drag_time = time.time()
                self._velocity = 0.0
                self._drag_occurred = False
                self._scroll_animation.stop()

            elif event_type == QEvent.MouseMove and self._is_dragging:
                current_y = event.pos().y()
                delta_y = current_y - self._last_drag_y
                total_delta = abs(current_y - self._drag_start_y)

                if total_delta > self._drag_threshold:
                    self._drag_occurred = True

                now = time.time()
                dt = max(0.001, now - self._last_drag_time)
                self._velocity = (-delta_y) / dt
                self._last_drag_y = current_y
                self._last_drag_time = now

                bar = self.verticalScrollBar()
                if bar:
                    bar.setValue(bar.value() - delta_y)
                return self._drag_occurred

            elif event_type == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton and self._is_dragging:
                self._is_dragging = False
                bar = self.verticalScrollBar()
                if bar and abs(self._velocity) > 60:
                    momentum_offset = int(self._velocity * 0.32)
                    target = max(bar.minimum(), min(bar.maximum(), bar.value() + momentum_offset))
                    self._scroll_animation.stop()
                    self._scroll_animation.setDuration(480)
                    self._scroll_animation.setStartValue(bar.value())
                    self._scroll_animation.setEndValue(target)
                    self._scroll_animation.start()

                if self._drag_occurred:
                    return True

        return super().eventFilter(obj, event)

    def wheelEvent(self, event):
        bar = self.verticalScrollBar()
        if not bar or bar.maximum() <= bar.minimum():
            super().wheelEvent(event)
            return

        delta = event.angleDelta().y()
        if not delta:
            pixel_delta = event.pixelDelta().y()
            delta = pixel_delta if pixel_delta else 0

        if not delta:
            super().wheelEvent(event)
            return

        if self._scroll_animation.state() == QAbstractAnimation.Running:
            current = self._scroll_target
        else:
            current = bar.value()

        step = max(90, int(bar.pageStep() * 0.34))
        wheel_units = delta / 120.0
        if abs(delta) > 0 and abs(delta) < 120:
            wheel_units = delta / 64.0

        self._scroll_target = int(current - (wheel_units * step * 1.35))
        self._scroll_target = max(bar.minimum(), min(bar.maximum(), self._scroll_target))

        self._scroll_animation.stop()
        self._scroll_animation.setStartValue(bar.value())
        self._scroll_animation.setEndValue(self._scroll_target)
        self._scroll_animation.start()
        event.accept()


class GameCard(QFrame):
    clicked = pyqtSignal(int)
    action_clicked = pyqtSignal(int)
    poster_context_requested = pyqtSignal(int)
    checked_toggled = pyqtSignal(int, bool)

    def __init__(
        self,
        index,
        game,
        format_size_func,
        selected=False,
        checked=False,
        action_text="Compress",
        card_width=MIN_CARD_W,
        poster_width=None,
        poster_height=None,
        scroll_parent=None,
    ):
        super().__init__()

        self.index = index
        self.game = game
        self.format_size = format_size_func
        self.scroll_parent = scroll_parent
        self.poster_width = int(poster_width or max(1, card_width - POSTER_W_PADDING))
        self.poster_height = int(poster_height or self.poster_width * POSTER_ASPECT)

        self.setFixedSize(int(card_width), int(self.poster_height + CARD_H_EXTRA))
        self.setCursor(Qt.PointingHandCursor)
        self.setObjectName("GameCardSelected" if selected else "GameCard")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 8)
        layout.setSpacing(6)

        # Header row: Checkbox and Traffic Light Pill
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)

        self.checkbox = QCheckBox()
        self.checkbox.setStyleSheet(CHECKBOX_STYLE)
        self.checkbox.setChecked(bool(checked))
        self.checkbox.toggled.connect(lambda c: self.checked_toggled.emit(self.index, c))

        traffic_light, badge_text, preview_text = calculate_savings_preview(game)
        light_color = "#00E676" if traffic_light == "green" else "#FFD166" if traffic_light == "yellow" else "#FF4D6D" if traffic_light == "red" else "#888899"

        self.traffic_badge = QLabel(f"● {badge_text}")
        self.traffic_badge.setStyleSheet(f"color: {light_color}; font-size: 10px; font-weight: bold; background: transparent;")
        self.traffic_badge.setToolTip(f"Compressibility: {badge_text}")

        header_layout.addWidget(self.checkbox)
        header_layout.addStretch()
        header_layout.addWidget(self.traffic_badge)
        layout.addLayout(header_layout)

        self.poster = PosterLabel()
        self.poster.setFixedSize(self.poster_width, self.poster_height)
        self.poster.setAlignment(Qt.AlignCenter)
        self.poster.setObjectName("Poster")
        self.poster.left_clicked.connect(self._handle_click)
        self.poster.right_clicked.connect(lambda: self.poster_context_requested.emit(self.index))

        self.load_poster()

        self.name_label = QLabel(game.get("name", "Unknown"))
        self.name_label.setAlignment(Qt.AlignCenter)
        self.name_label.setWordWrap(True)
        self.name_label.setObjectName("CardName")
        self.name_label.setMinimumHeight(32)
        self.name_label.setMaximumHeight(36)

        status = game.get("status", "Unknown")
        size = original_game_size(game)
        compressed_size = int(game.get("compressed_size", 0) or 0)

        meta_text = f"{status} | {self.format_size(size)}"
        if compressed_size > 0:
            meta_text = f"{status} | {self.format_size(size)} -> {self.format_size(compressed_size)}"

        self.meta_label = QLabel(meta_text)
        self.meta_label.setAlignment(Qt.AlignCenter)
        self.meta_label.setWordWrap(True)
        self.meta_label.setObjectName("CardMeta")
        self.meta_label.setMinimumHeight(24)
        self.meta_label.setMaximumHeight(30)

        # Potential / Actual Savings Preview Text
        self.savings_label = QLabel(preview_text)
        self.savings_label.setAlignment(Qt.AlignCenter)
        self.savings_label.setStyleSheet("color: #B38AFF; font-size: 11px; font-weight: bold; background: transparent;")
        self.savings_label.setMinimumHeight(16)
        self.savings_label.setMaximumHeight(18)

        self.action_btn = QPushButton(action_text)
        self.action_btn.setObjectName("CardActionButton")
        self.action_btn.setProperty(
            "state", "disable" if action_text == "Decompress" else "enable"
        )
        self.action_btn.setFixedHeight(32)
        self.action_btn.clicked.connect(lambda: self.action_clicked.emit(self.index))

        layout.addWidget(self.poster, alignment=Qt.AlignCenter)
        layout.addWidget(self.name_label)
        layout.addWidget(self.meta_label)
        layout.addWidget(self.savings_label)
        layout.addWidget(self.action_btn)

    def load_poster(self):
        poster_path = self.game.get("poster", "")
        if poster_path and os.path.exists(poster_path):
            poster_path = sanitize_png_file(poster_path)
            pixmap = QPixmap(poster_path)
            if not pixmap.isNull():
                pixmap = pixmap.scaled(
                    self.poster_width,
                    self.poster_height,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
                self.poster.setPixmap(pixmap)
                return

        status = self.game.get("poster_status", "Queued")
        self.poster.setText(status if status else "No Poster")
        self.poster.setStyleSheet(themed_qss("background: transparent; color:#ffffff; border:none;"))

    def _handle_click(self):
        if self.scroll_parent and getattr(self.scroll_parent, "_drag_occurred", False):
            return
        self.clicked.emit(self.index)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._handle_click()
        super().mousePressEvent(event)


class GameRow(QFrame):
    clicked = pyqtSignal(int)
    action_clicked = pyqtSignal(int)
    poster_context_requested = pyqtSignal(int)
    checked_toggled = pyqtSignal(int, bool)

    def __init__(
        self,
        index,
        game,
        format_size_func,
        selected=False,
        checked=False,
        action_text="Compress",
        scroll_parent=None,
    ):
        super().__init__()

        self.index = index
        self.game = game
        self.format_size = format_size_func
        self.scroll_parent = scroll_parent
        self.setObjectName("GameCardSelected" if selected else "GameCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(78)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        # Multi-select checkbox on the left edge
        self.checkbox = QCheckBox()
        self.checkbox.setStyleSheet(CHECKBOX_STYLE)
        self.checkbox.setChecked(bool(checked))
        self.checkbox.toggled.connect(lambda c: self.checked_toggled.emit(self.index, c))

        self.poster = PosterLabel()
        self.poster.setFixedSize(44, 58)
        self.poster.setAlignment(Qt.AlignCenter)
        self.poster.setObjectName("Poster")
        self.poster.left_clicked.connect(self._handle_click)
        self.poster.right_clicked.connect(lambda: self.poster_context_requested.emit(self.index))
        self.load_poster()

        self.name_label = QLabel(game.get("name", "Unknown"))
        self.name_label.setObjectName("RowName")
        self.name_label.setWordWrap(False)
        self.name_label.setFixedWidth(190)
        self.name_label.setToolTip(game.get("name", "Unknown"))

        # Traffic light indicator pill
        traffic_light, badge_text, preview_text = calculate_savings_preview(game)
        light_color = "#00E676" if traffic_light == "green" else "#FFD166" if traffic_light == "yellow" else "#FF4D6D" if traffic_light == "red" else "#888899"

        self.traffic_badge = QLabel(f"● {badge_text}")
        self.traffic_badge.setStyleSheet(f"color: {light_color}; font-size: 11px; font-weight: bold; background: transparent;")
        self.traffic_badge.setFixedWidth(155)
        self.traffic_badge.setToolTip(f"Compressibility: {badge_text}")

        status = game.get("status", "Unknown")
        size = original_game_size(game)
        compressed_size = int(game.get("compressed_size", 0) or 0)
        size_text = f"Size: {self.format_size(size)}"
        if compressed_size > 0:
            size_text = f"Size: {self.format_size(size)} -> {self.format_size(compressed_size)}"

        self.meta_label = QLabel(f"{status} | {size_text}")
        self.meta_label.setObjectName("RowMeta")
        self.meta_label.setWordWrap(False)
        self.meta_label.setFixedWidth(210)

        # Pre-calculated savings preview or saved size
        self.saved_label = QLabel(preview_text)
        self.saved_label.setStyleSheet("color: #B38AFF; font-size: 11px; font-weight: bold; background: transparent;")
        self.saved_label.setFixedWidth(130)

        self.action_btn = QPushButton(action_text)
        self.action_btn.setObjectName("CardActionButton")
        self.action_btn.setProperty(
            "state", "disable" if action_text == "Decompress" else "enable"
        )
        self.action_btn.setFixedWidth(120)
        self.action_btn.clicked.connect(lambda: self.action_clicked.emit(self.index))

        layout.addWidget(self.checkbox)
        layout.addWidget(self.poster)
        layout.addWidget(self.name_label)
        layout.addWidget(self.traffic_badge)
        layout.addWidget(self.meta_label)
        layout.addWidget(self.saved_label)
        layout.addStretch(1)
        layout.addWidget(self.action_btn)

    def load_poster(self):
        poster_path = self.game.get("poster", "")
        if poster_path and os.path.exists(poster_path):
            poster_path = sanitize_png_file(poster_path)
            pixmap = QPixmap(poster_path)
            if not pixmap.isNull():
                self.poster.setPixmap(
                    pixmap.scaled(44, 58, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                )
                return

        status = self.game.get("poster_status", "No Poster")
        self.poster.setText(status if status else "No Poster")
        self.poster.setStyleSheet(themed_qss("background: transparent; color:#ffffff; border:none;"))

    def _handle_click(self):
        if self.scroll_parent and getattr(self.scroll_parent, "_drag_occurred", False):
            return
        self.clicked.emit(self.index)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._handle_click()
        super().mousePressEvent(event)


class XGCRGameLibraryPage(QWidget):
    scan_steam_requested = pyqtSignal()
    add_folder_requested = pyqtSignal()
    remove_selected_requested = pyqtSignal()
    refresh_sizes_requested = pyqtSignal()
    refresh_posters_requested = pyqtSignal()
    game_selected = pyqtSignal(int)
    game_action_requested = pyqtSignal(int)
    custom_poster_requested = pyqtSignal(int)
    view_mode_changed = pyqtSignal(str)
    batch_compress_requested = pyqtSignal(list)
    selection_changed = pyqtSignal(list)

    def __init__(self, format_size_func, card_action_text_func, initial_view_mode="grid"):
        super().__init__()
        self.format_size = format_size_func
        self.card_action_text = card_action_text_func
        self.current_games = []
        self.current_selected_index = None
        self.selected_indices = set()
        self.current_columns = 0
        self.current_card_width = 0
        self.reflow_pending = False
        self._initial_show_reflow_done = False
        self.view_mode = "rows" if initial_view_mode == "rows" else "grid"
        self.setObjectName("DashboardPage")
        self.busy_overlay = None
        self.busy_spinner = None
        self.busy_label = None
        self.build_ui()

    def grid_metrics(self):
        available = self.width()
        if hasattr(self, "scroll") and self.scroll.viewport():
            available = int(self.scroll.viewport().width() or available)
        available = max(MIN_CARD_W, int(available or MIN_CARD_W))
        columns = max(1, (available + GRID_SPACING) // (MIN_CARD_W + GRID_SPACING))
        card_width = int((available - (GRID_SPACING * (columns - 1))) / columns)
        card_width = max(MIN_CARD_W, min(MAX_CARD_W, card_width))
        poster_width = max(1, card_width - POSTER_W_PADDING)
        poster_height = int(poster_width * POSTER_ASPECT)
        return int(columns), int(card_width), int(poster_width), int(poster_height)

    def schedule_grid_reflow(self):
        if self.reflow_pending:
            return
        self.reflow_pending = True
        QTimer.singleShot(0, self.reflow_current_grid)
        QTimer.singleShot(80, self.reflow_current_grid)
        QTimer.singleShot(180, self.reflow_current_grid)

    def reflow_current_grid(self):
        self.reflow_pending = False
        if not self.isVisible() or not self.current_games:
            return
        columns, card_width, _, _ = self.grid_metrics()
        if self.view_mode == "rows":
            columns = 1
        if columns != self.current_columns or abs(card_width - self.current_card_width) >= 4:
            self.refresh_grid(self.current_games, self.current_selected_index)

    def build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.scan_btn = QPushButton("Scan Stores")
        self.add_btn = QPushButton("Add Folder")
        self.remove_btn = QPushButton("Remove")
        self.size_btn = QPushButton("Refresh Sizes")
        self.poster_btn = QPushButton("Refresh Posters")

        # Handheld Batch Operations Toolbar Controls
        self.select_all_btn = QPushButton("Select All")
        self.batch_compress_btn = QPushButton("⚡ Batch Compress (0)")
        self.batch_compress_btn.setStyleSheet(themed_qss("background: #7B2CBF; color: #ffffff; font-weight: bold;"))

        self.grid_view_btn = QPushButton("Grid")
        self.row_view_btn = QPushButton("Rows")

        for action_button in (
            self.scan_btn,
            self.add_btn,
            self.remove_btn,
            self.size_btn,
            self.poster_btn,
            self.select_all_btn,
            self.batch_compress_btn,
        ):
            action_button.setObjectName("TopActionButton")

        for view_button in (self.grid_view_btn, self.row_view_btn):
            view_button.setObjectName("ViewModeButton")
            view_button.setCheckable(True)
            view_button.setFixedWidth(66)

        self.grid_view_btn.setChecked(self.view_mode == "grid")
        self.row_view_btn.setChecked(self.view_mode == "rows")

        self.scan_btn.clicked.connect(self.scan_steam_requested.emit)
        self.add_btn.clicked.connect(self.add_folder_requested.emit)
        self.remove_btn.clicked.connect(self.remove_selected_requested.emit)
        self.size_btn.clicked.connect(self.refresh_sizes_requested.emit)
        self.poster_btn.clicked.connect(self.refresh_posters_requested.emit)
        self.select_all_btn.clicked.connect(self.toggle_select_all)
        self.batch_compress_btn.clicked.connect(self.trigger_batch_compress)
        self.grid_view_btn.clicked.connect(lambda: self.set_view_mode("grid"))
        self.row_view_btn.clicked.connect(lambda: self.set_view_mode("rows"))

        actions = QHBoxLayout()
        actions.setSpacing(8)
        actions.addWidget(self.scan_btn)
        actions.addWidget(self.add_btn)
        actions.addWidget(self.remove_btn)
        actions.addSpacing(6)
        actions.addWidget(self.select_all_btn)
        actions.addWidget(self.batch_compress_btn)
        actions.addSpacing(6)
        actions.addWidget(self.size_btn)
        actions.addWidget(self.poster_btn)
        actions.addStretch()
        actions.addWidget(self.grid_view_btn)
        actions.addWidget(self.row_view_btn)

        layout.addLayout(actions)

        self.scroll = SmoothScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll.setStyleSheet(PURPLE_SCROLLBAR_STYLE)

        self.grid_container = QWidget()
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        self.grid_layout.setHorizontalSpacing(GRID_SPACING)
        self.grid_layout.setVerticalSpacing(GRID_SPACING)
        self.grid_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        self.scroll.setWidget(self.grid_container)
        layout.addWidget(self.scroll, stretch=1)

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setFixedHeight(145)
        self.log_box.setStyleSheet(PURPLE_SCROLLBAR_STYLE)

        layout.addWidget(self.log_box)

        self.build_busy_overlay()

    def build_busy_overlay(self):
        self.busy_overlay = QFrame(self)
        self.busy_overlay.setWindowFlags(Qt.Widget)
        self.busy_overlay.setObjectName("GameLibraryBusyOverlay")
        self.busy_overlay.setAttribute(Qt.WA_StyledBackground, True)
        self.busy_overlay.setStyleSheet(
            themed_qss("""
            #GameLibraryBusyOverlay {
                background: rgba(8, 7, 14, 174);
                border: 1px solid rgba(179, 138, 255, 0.22);
                border-radius: 10px;
            }
            #GameLibraryBusyText {
                color: #ffffff;
                font-size: 13px;
                font-weight: 900;
                background: transparent;
            }
            """)
        )
        self.busy_overlay.hide()

        overlay_layout = QVBoxLayout(self.busy_overlay)
        overlay_layout.setContentsMargins(0, 0, 0, 0)
        overlay_layout.setSpacing(12)
        overlay_layout.setAlignment(Qt.AlignCenter)

        self.busy_spinner = LoadingSpinner(self.busy_overlay)
        self.busy_label = QLabel("Working...", self.busy_overlay)
        self.busy_label.setObjectName("GameLibraryBusyText")
        self.busy_label.setAlignment(Qt.AlignCenter)

        overlay_layout.addWidget(self.busy_spinner, alignment=Qt.AlignCenter)
        overlay_layout.addWidget(self.busy_label, alignment=Qt.AlignCenter)
        self.position_busy_overlay()

    def position_busy_overlay(self):
        if not self.busy_overlay:
            return
        self.busy_overlay.setGeometry(self.rect())
        self.busy_overlay.raise_()

    def set_busy_overlay(self, visible, text="Working..."):
        if not self.busy_overlay:
            return
        self.busy_label.setText(str(text or "Working..."))
        self.position_busy_overlay()
        if visible and self.isVisible():
            self.busy_overlay.show()
            self.busy_overlay.raise_()
            self.busy_spinner.start()
        else:
            self.busy_spinner.stop()
            self.busy_overlay.hide()

    def set_view_mode(self, mode):
        mode = "rows" if mode == "rows" else "grid"
        if self.view_mode == mode:
            self.grid_view_btn.setChecked(mode == "grid")
            self.row_view_btn.setChecked(mode == "rows")
            return

        self.view_mode = mode
        self.grid_view_btn.setChecked(mode == "grid")
        self.row_view_btn.setChecked(mode == "rows")
        self.view_mode_changed.emit(mode)
        self.refresh_grid(self.current_games, self.current_selected_index)

    def handle_row_checked_toggled(self, index, checked):
        if checked:
            self.selected_indices.add(index)
        else:
            self.selected_indices.discard(index)
        self.update_batch_button_ui()
        self.selection_changed.emit(list(self.selected_indices))

    def update_batch_button_ui(self):
        count = len(self.selected_indices)
        self.batch_compress_btn.setText(f"⚡ Batch Compress ({count})")
        if self.current_games and len(self.selected_indices) >= len(self.current_games):
            self.select_all_btn.setText("Deselect All")
        else:
            self.select_all_btn.setText("Select All")

    def toggle_select_all(self):
        if len(self.selected_indices) >= len(self.current_games) and self.current_games:
            self.selected_indices.clear()
        else:
            self.selected_indices = set(range(len(self.current_games)))

        self.refresh_grid(self.current_games, self.current_selected_index)
        self.update_batch_button_ui()
        self.selection_changed.emit(list(self.selected_indices))

    def trigger_batch_compress(self):
        if not self.selected_indices:
            return
        self.batch_compress_requested.emit(list(self.selected_indices))

    def refresh_grid(self, games, selected_index):
        self.current_games = list(games or [])
        self.current_selected_index = selected_index
        columns, card_width, poster_width, poster_height = self.grid_metrics()
        if self.view_mode == "rows":
            columns = 1
        self.current_columns = columns
        self.current_card_width = card_width

        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        for index, game in enumerate(self.current_games):
            is_checked = index in self.selected_indices
            if self.view_mode == "rows":
                row = index
                col = 0
                card = GameRow(
                    index=index,
                    game=game,
                    format_size_func=self.format_size,
                    selected=index == selected_index,
                    checked=is_checked,
                    action_text=self.card_action_text(game),
                    scroll_parent=self.scroll,
                )
            else:
                row = index // columns
                col = index % columns
                card = GameCard(
                    index=index,
                    game=game,
                    format_size_func=self.format_size,
                    selected=index == selected_index,
                    checked=is_checked,
                    action_text=self.card_action_text(game),
                    card_width=card_width,
                    poster_width=poster_width,
                    poster_height=poster_height,
                    scroll_parent=self.scroll,
                )

            card.clicked.connect(self.game_selected.emit)
            card.action_clicked.connect(self.game_action_requested.emit)
            card.poster_context_requested.connect(self.custom_poster_requested.emit)
            card.checked_toggled.connect(self.handle_row_checked_toggled)

            alignment = Qt.AlignTop if self.view_mode == "rows" else Qt.AlignTop | Qt.AlignLeft
            self.grid_layout.addWidget(card, row, col, alignment)

        for col_index in range(max(1, columns + 1)):
            self.grid_layout.setColumnStretch(col_index, 0)
        if self.view_mode == "rows":
            self.grid_layout.setColumnStretch(0, 1)
        else:
            self.grid_layout.setColumnStretch(columns, 1)
        self.grid_layout.setRowStretch((len(self.current_games) // columns) + 1, 1)
        self.update_batch_button_ui()
        self.schedule_grid_reflow()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.position_busy_overlay()
        self.reflow_current_grid()

    def showEvent(self, event):
        super().showEvent(event)
        if not self._initial_show_reflow_done:
            self._initial_show_reflow_done = True
            self.schedule_grid_reflow()

    def log(self, text):
        self.log_box.append(text)

    def set_terminal_visible(self, visible):
        self.log_box.setVisible(bool(visible))

    def set_buttons_enabled(self, enabled):
        self.scan_btn.setEnabled(enabled)
        self.add_btn.setEnabled(enabled)
        self.remove_btn.setEnabled(enabled)
        self.size_btn.setEnabled(enabled)
        self.poster_btn.setEnabled(enabled)
        self.select_all_btn.setEnabled(enabled)
        self.batch_compress_btn.setEnabled(enabled)
