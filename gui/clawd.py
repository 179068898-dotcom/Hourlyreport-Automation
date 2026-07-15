from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QElapsedTimer, QRectF, QTimer, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget


CLAWD_BODY = QColor("#D4634A")
CLAWD_EYE = QColor("#2A1810")
PHASE_DURATIONS = (5.0, 3.0, 3.0, 3.0, 6.0, 3.0)


@dataclass(frozen=True)
class ClawdPose:
    x: float = 0.0
    y: float = 0.0
    scale_x: float = 1.0
    scale_y: float = 1.0
    rotation: float = 0.0
    left_claw: float = 0.0
    right_claw: float = 0.0
    leg_swing: float = 0.0
    eyes: str = "forward"
    sparkle: bool = False


def _lerp(start: float, end: float, amount: float) -> float:
    return start + (end - start) * max(0.0, min(1.0, amount))


def _sample(keys: tuple[tuple[float, ...], ...], progress: float) -> tuple[float, ...]:
    progress = max(0.0, min(1.0, progress))
    for index in range(1, len(keys)):
        right = keys[index]
        if progress <= right[0]:
            left = keys[index - 1]
            span = max(0.0001, right[0] - left[0])
            amount = (progress - left[0]) / span
            return tuple(_lerp(left[pos], right[pos], amount) for pos in range(1, len(left)))
    return tuple(float(value) for value in keys[-1][1:])


_PEEK_KEYS = (
    (0.00, 375, 0, 1.00, 1.00, 0),
    (0.05, 230, 0, 1.00, 1.00, -8),
    (0.11, 185, -6, 0.98, 1.02, -18),
    (0.16, 175, -6, 0.98, 1.02, -22),
    (0.43, 175, -6, 0.98, 1.02, -22),
    (0.51, 230, 0, 1.00, 1.00, -8),
    (0.59, 230, 0, 1.00, 1.00, -8),
    (0.66, 175, -6, 0.98, 1.02, -22),
    (0.74, 0, 0, 1.10, 0.88, 0),
    (0.83, 0, -22, 0.95, 1.05, 0),
    (0.92, 0, 0, 1.03, 0.97, 0),
    (1.00, 0, 0, 1.00, 1.00, 0),
)

_JUMP_KEYS = (
    (0.000, 0, 0, 1.00, 1.00, 0),
    (0.067, 0, 0, 1.20, 0.60, 0),
    (0.133, 0, -175, 0.90, 1.15, 0),
    (0.233, 0, 0, 1.20, 0.60, 0),
    (0.333, 0, 0, 1.00, 1.00, 0),
    (0.400, 80, -50, 0.95, 1.05, 8),
    (0.467, 0, 0, 1.10, 0.90, 0),
    (0.533, -80, -50, 0.95, 1.05, -8),
    (0.600, 0, 0, 1.10, 0.90, 0),
    (1.000, 0, 0, 1.00, 1.00, 0),
)

_LOOK_KEYS = (
    (0.00, 0, 0, 1.0, 1.0, 0),
    (0.20, 0, 0, 1.0, 1.0, -4),
    (0.42, 0, 0, 1.0, 1.0, -4),
    (0.52, 0, 0, 1.0, 1.0, 0),
    (0.58, 0, 0, 1.0, 1.0, 0),
    (0.68, 0, 0, 1.0, 1.0, 4),
    (0.88, 0, 0, 1.0, 1.0, 4),
    (1.00, 0, 0, 1.0, 1.0, 0),
)

_WALK_KEYS = (
    (0.00, 0, 0, 1.00, 1.00, 0),
    (0.04, 0, -45, 0.94, 1.06, 0),
    (0.09, 50, 0, 1.10, 0.88, 0),
    (0.12, 50, -45, 0.94, 1.06, 0),
    (0.18, 100, 0, 1.10, 0.88, 0),
    (0.21, 100, -45, 0.94, 1.06, 0),
    (0.27, 150, 0, 1.10, 0.88, 0),
    (0.37, 150, 0, 1.00, 1.00, 0),
    (0.40, 150, -45, 0.94, 1.06, 0),
    (0.45, 90, 0, 1.10, 0.88, 0),
    (0.48, 90, -45, 0.94, 1.06, 0),
    (0.54, 30, 0, 1.10, 0.88, 0),
    (0.57, 30, -45, 0.94, 1.06, 0),
    (0.62, -30, 0, 1.10, 0.88, 0),
    (0.65, -30, -45, 0.94, 1.06, 0),
    (0.70, -90, 0, 1.10, 0.88, 0),
    (0.73, -90, -45, 0.94, 1.06, 0),
    (0.78, -150, 0, 1.10, 0.88, 0),
    (0.86, -150, 0, 1.00, 1.00, 0),
    (0.88, -150, -45, 0.94, 1.06, 0),
    (0.92, -100, 0, 1.10, 0.88, 0),
    (0.94, -100, -45, 0.94, 1.06, 0),
    (0.97, -50, 0, 1.10, 0.88, 0),
    (0.99, -50, -45, 0.94, 1.06, 0),
    (1.00, 0, 0, 1.00, 1.00, 0),
)


def _phase_at(seconds: float) -> tuple[int, float]:
    cursor = seconds % sum(PHASE_DURATIONS)
    for index, duration in enumerate(PHASE_DURATIONS):
        if cursor < duration:
            return index, cursor / duration
        cursor -= duration
    return len(PHASE_DURATIONS) - 1, 1.0


def _idle_phase_at(seconds: float) -> tuple[int, float]:
    durations = PHASE_DURATIONS[1:]
    cursor = seconds % sum(durations)
    for index, duration in enumerate(durations, start=1):
        if cursor < duration:
            return index, cursor / duration
        cursor -= duration
    return len(PHASE_DURATIONS) - 1, 1.0


def _pose_for(phase: int, progress: float) -> ClawdPose:
    if phase == 0:
        x, y, scale_x, scale_y, rotation = _sample(_PEEK_KEYS, progress)
        wave = 0.0
        if 0.72 <= progress <= 0.90:
            wave = 26.0 if int(progress * 48) % 2 == 0 else -18.0
        eyes = "left" if progress < 0.72 else "forward"
        if 0.46 <= progress <= 0.49:
            eyes = "blink"
        return ClawdPose(x, y, scale_x, scale_y, rotation, wave, -wave, wave * 0.55, eyes)
    if phase == 1:
        x, y, scale_x, scale_y, rotation = _sample(_JUMP_KEYS, progress)
        swing = 18.0 if int(progress * 12) % 2 == 0 else -18.0
        eyes = "blink" if 0.80 <= progress <= 0.83 or 0.91 <= progress <= 0.96 else "forward"
        return ClawdPose(x, y, scale_x, scale_y, rotation, swing, -swing, swing, eyes)
    if phase == 2:
        blink = (0.31 <= progress <= 0.38) or (0.69 <= progress <= 0.73) or (0.89 <= progress <= 0.95)
        return ClawdPose(eyes="blink" if blink else "forward")
    if phase == 3:
        x, y, scale_x, scale_y, rotation = _sample(_LOOK_KEYS, progress)
        eyes = "left" if 0.20 <= progress < 0.52 else "right" if 0.68 <= progress < 0.90 else "forward"
        return ClawdPose(x, y, scale_x, scale_y, rotation, eyes=eyes)
    if phase == 4:
        x, y, scale_x, scale_y, rotation = _sample(_WALK_KEYS, progress)
        swing = 30.0 if int(progress * 25) % 2 == 0 else -25.0
        return ClawdPose(x, y, scale_x, scale_y, rotation, swing, -swing, swing * 0.65, "forward")

    bounce = -18.0 * max(0.0, 1.0 - abs(progress - 0.07) / 0.07)
    squash = 0.94 if progress < 0.16 else 1.0
    sparkle = 0.15 <= progress <= 0.85
    return ClawdPose(0, bounce, 1.06 if progress < 0.16 else 1.0, squash, 0, -20, 20, 0, "forward", sparkle)


def _dance_pose(seconds: float) -> ClawdPose:
    sequence = (1, 2, 3, 4, 2, 2, 3, 4)
    beat_length = 0.34
    beat_index = int(seconds / beat_length) % len(sequence)
    beat = sequence[beat_index]
    progress = (seconds % beat_length) / beat_length
    pulse = 1.0 - abs(progress * 2.0 - 1.0)
    if beat == 1:
        return ClawdPose(x=-42 * pulse, y=-12 * pulse, rotation=-6 * pulse, left_claw=-34, right_claw=12, leg_swing=26, eyes="left")
    if beat == 2:
        return ClawdPose(x=42 * pulse, y=-10 * pulse, rotation=6 * pulse, left_claw=12, right_claw=34, leg_swing=-26, eyes="right")
    if beat == 3:
        return ClawdPose(y=10 * pulse, scale_x=1.10, scale_y=0.82, left_claw=-20, right_claw=20, leg_swing=18, eyes="forward")
    return ClawdPose(y=-48 * pulse, scale_x=0.94, scale_y=1.10, rotation=8 - 16 * progress, left_claw=-42, right_claw=42, leg_swing=-20, eyes="forward", sparkle=True)


class ClawdAnimator(QWidget):
    """Compact Qt rendering of the six-part Clawd loop used by the reference page."""

    def __init__(
        self,
        parent=None,
        width: int = 46,
        height: int = 24,
        background: str = "#eef3f8",
        zoom: float = 1.0,
    ):
        super().__init__(parent)
        self.setObjectName("clawdAnimator")
        self.setFixedSize(width, height)
        self._background = QColor(background)
        self._mode = "loop"
        self._zoom = max(0.8, min(1.4, float(zoom)))
        self._clock = QElapsedTimer()
        self._clock.start()
        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self.update)
        self._timer.start()

    def set_mode(self, mode: str) -> None:
        self._mode = mode if mode in {"dance", "idle"} else "loop"
        self.update()

    def paintEvent(self, event) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        seconds = self._clock.elapsed() / 1000.0
        phase, progress = _idle_phase_at(seconds) if self._mode == "idle" else _phase_at(seconds)
        pose = _dance_pose(seconds) if self._mode == "dance" else _pose_for(phase, progress)
        cell = min(self.width() / 30.0, self.height() / 12.0) * self._zoom
        scene_left = (self.width() - 30.0 * cell) / 2.0
        base_x = scene_left + 8.0 * cell
        base_y = (self.height() - 10.0 * cell) / 2.0
        x = base_x + (pose.x / 20.0) * cell
        y = base_y + (pose.y / 20.0) * cell * 0.32

        painter.save()
        pivot_x = x + 7.0 * cell
        pivot_y = y + 10.0 * cell
        painter.translate(pivot_x, pivot_y)
        painter.rotate(pose.rotation)
        painter.scale(pose.scale_x, pose.scale_y)
        painter.translate(-pivot_x, -pivot_y)

        self._draw_shadow(painter, x, y, cell, pose)
        self._draw_legs(painter, x, y, cell, pose.leg_swing)
        self._draw_claw(painter, x, y, cell, left=True, rotation=pose.left_claw)
        self._draw_claw(painter, x, y, cell, left=False, rotation=pose.right_claw)
        painter.fillRect(QRectF(x + 2 * cell, y, 10 * cell, 7 * cell), CLAWD_BODY)
        self._draw_eyes(painter, x, y, cell, pose)
        painter.restore()

        if self._mode != "dance" and phase == 0 and progress < 0.74:
            wall_x = scene_left + 22.0 * cell
            painter.fillRect(QRectF(wall_x + max(1.0, 0.3 * cell), 0, self.width() - wall_x, self.height()), self._background)
            painter.fillRect(QRectF(wall_x, 0, max(1.0, 0.3 * cell), self.height()), CLAWD_EYE)
        painter.end()

    @staticmethod
    def _draw_shadow(painter: QPainter, x: float, y: float, cell: float, pose: ClawdPose) -> None:
        color = QColor(42, 24, 16, 42)
        width = 8.0 * cell * max(0.65, pose.scale_x)
        painter.fillRect(QRectF(x + 7 * cell - width / 2, y + 9.55 * cell, width, max(1.0, 0.35 * cell)), color)

    @staticmethod
    def _draw_legs(painter: QPainter, x: float, y: float, cell: float, swing: float) -> None:
        for index, logical_x in enumerate((2.0, 4.0, 9.0, 11.0)):
            direction = 1.0 if index % 2 == 0 else -1.0
            center_x = x + (logical_x + 0.5) * cell
            top_y = y + 7.0 * cell
            painter.save()
            painter.translate(center_x, top_y)
            painter.rotate(direction * swing)
            painter.translate(-center_x, -top_y)
            painter.fillRect(QRectF(x + logical_x * cell, top_y, cell, 2.5 * cell), CLAWD_BODY)
            painter.restore()

    @staticmethod
    def _draw_claw(painter: QPainter, x: float, y: float, cell: float, left: bool, rotation: float) -> None:
        logical_x = 0.0 if left else 12.0
        rect = QRectF(x + logical_x * cell, y + 2.0 * cell, 2.0 * cell, 2.0 * cell)
        pivot_x = rect.right() if left else rect.left()
        pivot_y = rect.center().y()
        painter.save()
        painter.translate(pivot_x, pivot_y)
        painter.rotate(rotation)
        painter.translate(-pivot_x, -pivot_y)
        painter.fillRect(rect, CLAWD_BODY)
        painter.restore()

    @staticmethod
    def _draw_eyes(painter: QPainter, x: float, y: float, cell: float, pose: ClawdPose) -> None:
        if pose.sparkle:
            block = max(1.0, 0.35 * cell)
            for eye_x in (4.5, 9.5):
                center_x = x + eye_x * cell
                center_y = y + 2.0 * cell
                for dx, dy in ((-0.55, 0), (0.55, 0), (0, -0.55), (0, 0.55)):
                    painter.fillRect(QRectF(center_x + dx * cell - block / 2, center_y + dy * cell - block / 2, block, block), CLAWD_EYE)
            return
        if pose.eyes == "blink":
            for logical_x in (4.0, 9.0):
                painter.fillRect(QRectF(x + logical_x * cell, y + 1.92 * cell, cell, max(1.0, 0.16 * cell)), CLAWD_EYE)
            return
        eye_shift = -0.45 if pose.eyes == "left" else 0.45 if pose.eyes == "right" else 0.0
        for logical_x in (4.0, 9.0):
            painter.fillRect(QRectF(x + (logical_x + eye_shift) * cell, y + 1.5 * cell, cell, cell), CLAWD_EYE)
