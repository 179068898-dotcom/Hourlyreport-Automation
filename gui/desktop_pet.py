from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QRect, QRectF, QSize, QTimer, Qt
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QLabel, QWidget


CELL_SIZE = QSize(192, 208)
ATLAS_SIZE = QSize(1536, 2288)
BASE_PET_SIZE = QSize(108, 117)
BASE_WINDOW_SIZE = QSize(122, 128)
FONT_FAMILY = "Microsoft YaHei Light"

ANIMATIONS: dict[str, tuple[int, tuple[int, ...]]] = {
    "idle": (0, (280, 110, 110, 140, 140, 320)),
    "walk_right": (1, (120, 120, 120, 120, 120, 120, 120, 220)),
    "walk_left": (2, (120, 120, 120, 120, 120, 120, 120, 220)),
    "waving": (3, (140, 140, 140, 280)),
    "jumping": (4, (140, 140, 140, 140, 280)),
    "failed": (5, (140, 140, 140, 140, 140, 140, 140, 240)),
    "waiting": (6, (150, 150, 150, 150, 150, 260)),
    "running": (7, (120, 120, 120, 120, 120, 220)),
    "review": (8, (150, 150, 150, 150, 150, 280)),
    "look_a": (9, (170, 170, 170, 170, 170, 170, 170, 220)),
    "look_b": (10, (170, 170, 170, 170, 170, 170, 170, 220)),
}

@dataclass(frozen=True)
class ClassicPassage:
    title: str
    lines: tuple[str, ...]


_CLASSIC_EXCERPTS = (
    ClassicPassage("洛神赋", (
        "翩若惊鸿，婉若游龙。",
        "荣曜秋菊，华茂春松。",
        "仿佛兮若轻云之蔽月，飘飖兮若流风之回雪。",
    )),
    ClassicPassage("洛神赋", (
        "远而望之，皎若太阳升朝霞。",
        "迫而察之，灼若芙蕖出渌波。",
        "秾纤得衷，修短合度。",
    )),
    ClassicPassage("洛神赋", (
        "凌波微步，罗袜生尘。",
        "动无常则，若危若安。",
        "进止难期，若往若还。",
    )),
    ClassicPassage("滕王阁序", (
        "落霞与孤鹜齐飞，秋水共长天一色。",
        "渔舟唱晚，响穷彭蠡之滨。",
        "雁阵惊寒，声断衡阳之浦。",
    )),
    ClassicPassage("滕王阁序", (
        "天高地迥，觉宇宙之无穷。",
        "兴尽悲来，识盈虚之有数。",
        "关山难越，谁悲失路之人？",
        "萍水相逢，尽是他乡之客。",
    )),
    ClassicPassage("滕王阁序", (
        "老当益壮，宁移白首之心？",
        "穷且益坚，不坠青云之志。",
        "东隅已逝，桑榆非晚。",
    )),
    ClassicPassage("前出师表", (
        "诚宜开张圣听，以光先帝遗德，恢弘志士之气。",
        "不宜妄自菲薄，引喻失义，以塞忠谏之路也。",
    )),
    ClassicPassage("前出师表", (
        "亲贤臣，远小人，此先汉所以兴隆也。",
        "亲小人，远贤臣，此后汉所以倾颓也。",
    )),
    ClassicPassage("前出师表", (
        "受任于败军之际，奉命于危难之间，尔来二十有一年矣。",
        "受命以来，夙夜忧叹，恐托付不效，以伤先帝之明。",
        "今当远离，临表涕零，不知所言。",
    )),
    ClassicPassage("陈情表", (
        "臣以险衅，夙遭闵凶。",
        "生孩六月，慈父见背；行年四岁，舅夺母志。",
        "祖母刘愍臣孤弱，躬亲抚养。",
    )),
    ClassicPassage("陈情表", (
        "茕茕孑立，形影相吊。",
        "而刘夙婴疾病，常在床蓐。",
        "臣侍汤药，未曾废离。",
    )),
    ClassicPassage("陈情表", (
        "臣无祖母，无以至今日；祖母无臣，无以终余年。",
        "母孙二人，更相为命，是以区区不能废远。",
        "乌鸟私情，愿乞终养。",
    )),
    ClassicPassage("岳阳楼记", (
        "衔远山，吞长江，浩浩汤汤，横无际涯。",
        "朝晖夕阴，气象万千。",
        "此则岳阳楼之大观也。",
    )),
    ClassicPassage("岳阳楼记", (
        "至若春和景明，波澜不惊，上下天光，一碧万顷。",
        "沙鸥翔集，锦鳞游泳。",
        "岸芷汀兰，郁郁青青。",
    )),
    ClassicPassage("岳阳楼记", (
        "不以物喜，不以己悲。",
        "居庙堂之高则忧其民，处江湖之远则忧其君。",
        "先天下之忧而忧，后天下之乐而乐。",
    )),
    ClassicPassage("醉翁亭记", (
        "峰回路转，有亭翼然临于泉上者，醉翁亭也。",
        "醉翁之意不在酒，在乎山水之间也。",
        "山水之乐，得之心而寓之酒也。",
    )),
    ClassicPassage("醉翁亭记", (
        "日出而林霏开，云归而岩穴暝。",
        "野芳发而幽香，佳木秀而繁阴。",
        "风霜高洁，水落而石出。",
    )),
    ClassicPassage("醉翁亭记", (
        "人知从太守游而乐，而不知太守之乐其乐也。",
        "醉能同其乐，醒能述以文者，太守也。",
    )),
    ClassicPassage("兰亭集序", (
        "群贤毕至，少长咸集。",
        "此地有崇山峻岭，茂林修竹。",
        "又有清流激湍，映带左右。",
    )),
    ClassicPassage("兰亭集序", (
        "是日也，天朗气清，惠风和畅。",
        "仰观宇宙之大，俯察品类之盛。",
        "所以游目骋怀，足以极视听之娱，信可乐也。",
    )),
    ClassicPassage("兰亭集序", (
        "向之所欣，俯仰之间，已为陈迹，犹不能不以之兴怀。",
        "况修短随化，终期于尽。",
        "古人云：‘死生亦大矣。’岂不痛哉！",
    )),
    ClassicPassage("桃花源记", (
        "忽逢桃花林，夹岸数百步，中无杂树。",
        "芳草鲜美，落英缤纷。",
        "渔人甚异之，复前行，欲穷其林。",
    )),
    ClassicPassage("桃花源记", (
        "复行数十步，豁然开朗。",
        "土地平旷，屋舍俨然，有良田、美池、桑竹之属。",
        "阡陌交通，鸡犬相闻。",
    )),
    ClassicPassage("桃花源记", (
        "此中人语云：‘不足为外人道也。’",
        "既出，得其船，便扶向路，处处志之。",
        "寻向所志，遂迷，不复得路。",
    )),
    ClassicPassage("前赤壁赋", (
        "清风徐来，水波不兴。",
        "月出于东山之上，徘徊于斗牛之间。",
        "白露横江，水光接天。",
    )),
    ClassicPassage("前赤壁赋", (
        "纵一苇之所如，凌万顷之茫然。",
        "浩浩乎如凭虚御风，而不知其所止。",
        "飘飘乎如遗世独立，羽化而登仙。",
    )),
    ClassicPassage("前赤壁赋", (
        "寄蜉蝣于天地，渺沧海之一粟。",
        "哀吾生之须臾，羡长江之无穷。",
        "挟飞仙以遨游，抱明月而长终。",
    )),
    ClassicPassage("逍遥游", (
        "北冥有鱼，其名为鲲。",
        "鲲之大，不知其几千里也。",
        "化而为鸟，其名为鹏。",
        "鹏之背，不知其几千里也。",
    )),
    ClassicPassage("逍遥游", (
        "鹏之徙于南冥也，水击三千里。",
        "抟扶摇而上者九万里，去以六月息者也。",
    )),
    ClassicPassage("逍遥游", (
        "且举世誉之而不加劝，举世非之而不加沮。",
        "定乎内外之分，辩乎荣辱之境，斯已矣。",
        "至人无己，神人无功，圣人无名。",
    )),
)


def _pair_classic_passages(excerpts: tuple[ClassicPassage, ...]) -> tuple[ClassicPassage, ...]:
    paired: list[ClassicPassage] = []
    for passage in excerpts:
        for start in range(0, len(passage.lines), 2):
            lines = passage.lines[start:start + 2]
            if len(lines) < 2:
                lines = passage.lines[-2:]
            item = ClassicPassage(passage.title, tuple(lines))
            if not paired or paired[-1] != item:
                paired.append(item)
    return tuple(paired)


CLASSIC_PASSAGES = _pair_classic_passages(_CLASSIC_EXCERPTS)
CLASSIC_RECITATION_MS = 10_000


@dataclass(frozen=True)
class RoutineStep:
    state: str
    duration_ms: int
    move_x: int = 0


@dataclass(frozen=True)
class IdleRoutine:
    name: str
    steps: tuple[RoutineStep, ...]
    recites_classic: bool = False


IDLE_ROUTINES = (
    IdleRoutine("伸懒腰", (RoutineStep("waving", 900), RoutineStep("jumping", 950), RoutineStep("idle", 500))),
    IdleRoutine("四处张望", (RoutineStep("look_a", 1450), RoutineStep("look_b", 1450), RoutineStep("idle", 450))),
    IdleRoutine(
        "桌面巡逻",
        (RoutineStep("walk_left", 1250, -90), RoutineStep("review", 700), RoutineStep("walk_right", 1250, 90)),
    ),
    IdleRoutine("原地小舞", (RoutineStep("waving", 700), RoutineStep("jumping", 900), RoutineStep("waving", 700))),
    IdleRoutine("托腮发呆", (RoutineStep("waiting", 1200), RoutineStep("look_a", 1200), RoutineStep("idle", 500))),
    IdleRoutine("认真研究", (RoutineStep("review", 1200), RoutineStep("running", 900), RoutineStep("waving", 650))),
    IdleRoutine("打盹惊醒", (RoutineStep("failed", 1500), RoutineStep("idle", 500), RoutineStep("jumping", 750))),
    IdleRoutine(
        "诵读名篇",
        (RoutineStep("review", 3400), RoutineStep("look_a", 3300), RoutineStep("waving", 3300)),
        recites_classic=True,
    ),
)


class PetSpeechBubble(QWidget):
    def __init__(self):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFixedSize(300, 86)
        self.label = QLabel(self)
        self.label.setGeometry(18, 10, 258, 58)
        self.label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.label.setWordWrap(True)
        self.label.setFont(QFont(FONT_FAMILY, 9))
        self.label.setStyleSheet("color: #25324a; background: transparent;")

    def set_text(self, text: str, single_line: bool = False) -> None:
        value = str(text or "")
        self.label.setWordWrap(not single_line)
        if single_line:
            content_width = max(258, self.label.fontMetrics().horizontalAdvance(value) + 4)
            self.setFixedSize(content_width + 42, 86)
            self.label.setGeometry(18, 10, content_width, 58)
        elif "\n" in value:
            content_width = 318
            flags = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap
            bounds = self.label.fontMetrics().boundingRect(QRect(0, 0, content_width, 1000), flags, value)
            label_height = max(76, bounds.height() + 6)
            self.setFixedSize(360, label_height + 36)
            self.label.setGeometry(18, 10, content_width, label_height)
        else:
            self.setFixedSize(300, 86)
            self.label.setGeometry(18, 10, 258, 58)
        self.label.setText(value)

    def paintEvent(self, event) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(QColor("#cdd9e8"), 1))
        painter.setBrush(QColor(255, 255, 255, 246))
        path = QPainterPath()
        path.addRoundedRect(QRectF(4, 4, self.width() - 18, self.height() - 20), 12, 12)
        tail = QPainterPath()
        tail.moveTo(self.width() - 53, self.height() - 17)
        tail.lineTo(self.width() - 28, self.height() - 17)
        tail.lineTo(self.width() - 24, self.height() - 4)
        tail.closeSubpath()
        painter.drawPath(path)
        painter.drawPath(tail)
        painter.end()


class ClawdDesktopPet(QWidget):
    def __init__(
        self,
        root: str | Path,
        toggle_console: Callable[[], None],
        position_changed: Callable[[int, int], None] | None = None,
    ):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.root = Path(root)
        self._toggle_console = toggle_console
        self._position_changed = position_changed
        self._enabled = False
        self._busy = False
        self._scale = 1.0
        self._saved_position: QPoint | None = None
        self._state = "idle"
        self._frame_index = 0
        self._frames: dict[str, list[QPixmap]] = {}
        self._press_global: QPoint | None = None
        self._press_window: QPoint | None = None
        self._dragging = False
        self._bubble = PetSpeechBubble()

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFixedSize(BASE_WINDOW_SIZE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("单击显示或隐藏百度数据自动化控制台")

        self.sprite = QLabel(self)
        self.sprite.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.sprite.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sprite.setGeometry(7, 5, BASE_PET_SIZE.width(), BASE_PET_SIZE.height())

        self._animation_timer = QTimer(self)
        self._animation_timer.setSingleShot(True)
        self._animation_timer.timeout.connect(self._advance_frame)
        self._message_timer = QTimer(self)
        self._message_timer.setSingleShot(True)
        self._message_timer.timeout.connect(self._finish_temporary_message)
        self._return_state = "idle"
        self._rng = random.Random()
        self._routine_queue: list[int] = []
        self._passage_queue: list[int] = []
        self._routine: IdleRoutine | None = None
        self._routine_step = 0
        self._routine_origin: QPoint | None = None
        self._idle_timer = QTimer(self)
        self._idle_timer.setSingleShot(True)
        self._idle_timer.timeout.connect(self.trigger_idle_routine)
        self._routine_timer = QTimer(self)
        self._routine_timer.setSingleShot(True)
        self._routine_timer.timeout.connect(self._run_next_routine_step)
        self._movement = QPropertyAnimation(self, b"pos", self)
        self._movement.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._movement.valueChanged.connect(lambda _value: self._move_bubble())

        self.available = self._load_frames(self.root / "assets" / "clawd" / "spritesheet.webp")
        if self.available:
            self.set_state("idle")

    def _load_frames(self, atlas_path: Path) -> bool:
        atlas = QPixmap(str(atlas_path))
        if atlas.isNull() or atlas.size() != ATLAS_SIZE:
            return False
        for state, (row, durations) in ANIMATIONS.items():
            frames: list[QPixmap] = []
            for column in range(len(durations)):
                frame = atlas.copy(
                    column * CELL_SIZE.width(),
                    row * CELL_SIZE.height(),
                    CELL_SIZE.width(),
                    CELL_SIZE.height(),
                )
                frames.append(frame)
            self._frames[state] = frames
        return True

    def set_pet_scale(self, scale: float) -> None:
        self._cancel_idle_routine()
        value = max(0.5, min(1.2, float(scale)))
        old_position = self.pos()
        self._scale = value
        pet_size = QSize(round(BASE_PET_SIZE.width() * value), round(BASE_PET_SIZE.height() * value))
        window_size = QSize(round(BASE_WINDOW_SIZE.width() * value), round(BASE_WINDOW_SIZE.height() * value))
        self.setFixedSize(window_size)
        margin_x = max(4, round(7 * value))
        margin_y = max(3, round(5 * value))
        self.sprite.setGeometry(margin_x, margin_y, pet_size.width(), pet_size.height())
        self.move(old_position)
        self._show_current_frame()
        self._move_bubble()

    def pet_scale(self) -> float:
        return self._scale

    def restore_position(self, position: tuple[int, int] | None) -> None:
        self._saved_position = QPoint(*position) if position else None
        if self._enabled:
            self._apply_initial_position()

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled) and self.available
        if not self._enabled:
            self._cancel_idle_routine()
            self._bubble.hide()
            self.hide()
            return
        self._apply_initial_position()
        self.show()
        self.raise_()
        self._schedule_idle_routine()

    def _apply_initial_position(self) -> None:
        if self._saved_position is not None:
            self.move(self._saved_position)
            self._clamp_to_screen()
            self._move_bubble()
            return
        self.move_to_corner()

    def is_enabled(self) -> bool:
        return self._enabled

    def set_busy(self, busy: bool) -> None:
        self._busy = bool(busy)
        if self._busy:
            self._cancel_idle_routine()
        else:
            self._schedule_idle_routine()

    def move_to_corner(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        margin = 14
        self.move(area.right() - self.width() - margin + 1, area.bottom() - self.height() - margin + 1)
        self._move_bubble()

    def _move_bubble(self) -> None:
        screen = QApplication.screenAt(self.geometry().center()) or QApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        x = max(area.left() + 8, self.x() + self.width() - self._bubble.width())
        y = max(area.top() + 8, self.y() - self._bubble.height() + 20)
        self._bubble.move(x, y)

    def _clamp_to_screen(self) -> None:
        screen = QApplication.screenAt(self.geometry().center()) or QApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        x = min(max(self.x(), area.left()), area.right() - self.width() + 1)
        y = min(max(self.y(), area.top()), area.bottom() - self.height() + 1)
        self.move(x, y)

    def set_state(self, state: str) -> None:
        normalized = state if state in self._frames else "idle"
        if not self.available:
            return
        self._state = normalized
        self._frame_index = 0
        self._show_current_frame()

    def _show_current_frame(self) -> None:
        frames = self._frames.get(self._state) or []
        if not frames:
            return
        frame = frames[self._frame_index % len(frames)]
        self.sprite.setPixmap(
            frame.scaled(
                self.sprite.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation,
            )
        )
        durations = ANIMATIONS[self._state][1]
        self._animation_timer.start(durations[self._frame_index % len(durations)])

    def _advance_frame(self) -> None:
        frames = self._frames.get(self._state) or []
        if not frames:
            return
        self._frame_index = (self._frame_index + 1) % len(frames)
        self._show_current_frame()

    def announce(
        self,
        text: str,
        state: str = "running",
        timeout_ms: int = 0,
        return_state: str = "idle",
    ) -> None:
        if not self._enabled:
            return
        self._cancel_idle_routine()
        self.set_state(state)
        self._bubble.set_text(text)
        self._move_bubble()
        self._bubble.show()
        self._bubble.raise_()
        self.raise_()
        self._message_timer.stop()
        self._return_state = return_state
        if timeout_ms > 0:
            self._message_timer.start(timeout_ms)

    def clear_message(self, state: str = "idle") -> None:
        self._message_timer.stop()
        self._bubble.hide()
        self.set_state(state)
        self._schedule_idle_routine()

    def _finish_temporary_message(self) -> None:
        self._bubble.hide()
        self.set_state(self._return_state)
        self._schedule_idle_routine()

    def _schedule_idle_routine(self) -> None:
        self._idle_timer.stop()
        if self._enabled and not self._busy and self._routine is None and not self._bubble.isVisible():
            self._idle_timer.start(self._rng.randint(18000, 42000))

    def trigger_idle_routine(self, routine_name: str | None = None) -> bool:
        if not self._enabled or self._busy:
            return False
        self._cancel_idle_routine()
        if routine_name:
            routine = next((item for item in IDLE_ROUTINES if item.name == routine_name), None)
            if routine is None:
                return False
        else:
            if not self._routine_queue:
                self._routine_queue = list(range(len(IDLE_ROUTINES)))
                self._rng.shuffle(self._routine_queue)
            routine = IDLE_ROUTINES[self._routine_queue.pop()]
        self._routine = routine
        self._routine_step = 0
        self._routine_origin = self.pos()
        if routine.recites_classic:
            passage = self._next_classic_passage()
            self._bubble.set_text("".join(passage.lines), single_line=True)
            self._move_bubble()
            self._bubble.show()
            self._bubble.raise_()
        self._run_next_routine_step()
        return True

    def _next_classic_passage(self) -> ClassicPassage:
        if not self._passage_queue:
            self._passage_queue = list(range(len(CLASSIC_PASSAGES)))
            self._rng.shuffle(self._passage_queue)
        return CLASSIC_PASSAGES[self._passage_queue.pop()]

    def _run_next_routine_step(self) -> None:
        if self._routine is None or self._busy:
            self._cancel_idle_routine()
            return
        if self._routine_step >= len(self._routine.steps):
            self._finish_idle_routine()
            return
        step = self._routine.steps[self._routine_step]
        self._routine_step += 1
        self.set_state(step.state)
        if step.move_x:
            target = self.pos() + QPoint(round(step.move_x * self._scale), 0)
            target = self._clamped_position(target)
            self._movement.stop()
            self._movement.setDuration(step.duration_ms)
            self._movement.setStartValue(self.pos())
            self._movement.setEndValue(target)
            self._movement.start()
        self._routine_timer.start(step.duration_ms)

    def _finish_idle_routine(self) -> None:
        origin = self._routine_origin
        self._routine = None
        self._routine_step = 0
        self._routine_origin = None
        self._movement.stop()
        if origin is not None:
            self.move(self._clamped_position(origin))
        self._bubble.hide()
        self.set_state("idle")
        self._move_bubble()
        self._schedule_idle_routine()

    def _cancel_idle_routine(self, restore_origin: bool = True) -> None:
        self._idle_timer.stop()
        self._routine_timer.stop()
        self._movement.stop()
        origin = self._routine_origin
        self._routine = None
        self._routine_step = 0
        self._routine_origin = None
        if restore_origin and origin is not None:
            self.move(self._clamped_position(origin))
            self._move_bubble()
        self._bubble.hide()

    def _clamped_position(self, position: QPoint) -> QPoint:
        screen = QApplication.screenAt(position + QPoint(self.width() // 2, self.height() // 2)) or QApplication.primaryScreen()
        if screen is None:
            return position
        area = screen.availableGeometry()
        return QPoint(
            min(max(position.x(), area.left()), area.right() - self.width() + 1),
            min(max(position.y(), area.top()), area.bottom() - self.height() + 1),
        )

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._cancel_idle_routine(restore_origin=False)
            self._press_global = event.globalPosition().toPoint()
            self._press_window = self.pos()
            self._dragging = False
            event.accept()
            return
        event.ignore()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._press_global is None or self._press_window is None or not (event.buttons() & Qt.MouseButton.LeftButton):
            event.ignore()
            return
        delta = event.globalPosition().toPoint() - self._press_global
        if not self._dragging and delta.manhattanLength() < QApplication.startDragDistance():
            event.accept()
            return
        self._dragging = True
        self.move(self._press_window + delta)
        self._clamp_to_screen()
        self._move_bubble()
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            event.ignore()
            return
        was_dragging = self._dragging
        self._press_global = None
        self._press_window = None
        self._dragging = False
        if was_dragging:
            self._saved_position = self.pos()
            if self._position_changed:
                self._position_changed(self.x(), self.y())
        else:
            self._toggle_console()
        self._schedule_idle_routine()
        event.accept()

    def close_pet(self) -> None:
        self._animation_timer.stop()
        self._message_timer.stop()
        self._cancel_idle_routine()
        self._bubble.close()
        self.close()
