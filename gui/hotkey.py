"""Customizable macOS global hotkey bridge."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QKeySequence


# macOS virtual key codes for the main alphanumeric keyboard.
_KEY_CODES = {
    "a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7,
    "c": 8, "v": 9, "b": 11, "q": 12, "w": 13, "e": 14, "r": 15,
    "y": 16, "t": 17, "1": 18, "2": 19, "3": 20, "4": 21, "6": 22,
    "5": 23, "9": 25, "7": 26, "8": 28, "0": 29, "o": 31, "u": 32,
    "i": 34, "p": 35, "l": 37, "j": 38, "k": 40, "n": 45, "m": 46,
}
_KEY_NAMES = {value: key for key, value in _KEY_CODES.items()}
_MODIFIER_VALUES = {
    "ctrl": 262144,
    "alt": 524288,
    "shift": 131072,
    "cmd": 1048576,
}
_UNSET = object()


@dataclass(frozen=True)
class HotkeyBinding:
    """A portable storage representation plus macOS key code and modifiers."""

    key: str
    modifiers: tuple[str, ...]

    DEFAULT = "ctrl+alt+cmd+o"

    @property
    def key_code(self) -> int:
        return _KEY_CODES[self.key]

    @property
    def modifier_mask(self) -> int:
        return sum(_MODIFIER_VALUES[name] for name in self.modifiers)

    @property
    def storage(self) -> str:
        return "+".join((*self.modifiers, self.key))

    @property
    def display(self) -> str:
        labels = {"ctrl": "Control", "alt": "Option", "shift": "Shift", "cmd": "Command"}
        return "+".join([*(labels[name] for name in self.modifiers), self.key.upper()])

    @classmethod
    def from_storage(cls, value: str | None) -> "HotkeyBinding | None":
        if value == "":
            return None
        raw = (cls.DEFAULT if value is None else value).lower().replace(" ", "")
        tokens = raw.split("+")
        if len(tokens) < 2:
            raise ValueError("快捷键必须包含至少一个修饰键和一个字母/数字键")
        key = tokens[-1]
        aliases = {"control": "ctrl", "option": "alt", "command": "cmd", "meta": "cmd"}
        modifiers = tuple(aliases.get(token, token) for token in tokens[:-1])
        if key not in _KEY_CODES or any(name not in _MODIFIER_VALUES for name in modifiers):
            raise ValueError("快捷键包含不支持的按键")
        if len(set(modifiers)) != len(modifiers):
            raise ValueError("快捷键修饰键不能重复")
        return cls(key, modifiers)

    @classmethod
    def from_qt_sequence(cls, sequence: QKeySequence) -> "HotkeyBinding | None":
        if sequence.isEmpty():
            return None
        if sequence.count() != 1:
            raise ValueError("请输入一个快捷键组合")
        combination = sequence[0]
        key = int(combination.key())
        key_name = None
        for name, code in _KEY_CODES.items():
            if (ord(name.upper()) if name.isalpha() else None) == key:
                key_name = name
                break
        if key_name is None and Qt.Key.Key_0 <= key <= Qt.Key.Key_9:
            key_name = chr(key)
        if key_name is None:
            raise ValueError("目前支持字母和数字作为快捷键主键")
        qt_modifiers = combination.keyboardModifiers()
        modifiers: list[str] = []
        if qt_modifiers & Qt.KeyboardModifier.ControlModifier:
            modifiers.append("ctrl")
        if qt_modifiers & Qt.KeyboardModifier.AltModifier:
            modifiers.append("alt")
        if qt_modifiers & Qt.KeyboardModifier.ShiftModifier:
            modifiers.append("shift")
        if qt_modifiers & Qt.KeyboardModifier.MetaModifier:
            modifiers.append("cmd")
        if not modifiers:
            raise ValueError("快捷键必须包含至少一个修饰键")
        return cls(key_name, tuple(modifiers))

    def qt_sequence(self) -> QKeySequence:
        modifier_map = {
            "ctrl": Qt.KeyboardModifier.ControlModifier,
            "alt": Qt.KeyboardModifier.AltModifier,
            "shift": Qt.KeyboardModifier.ShiftModifier,
            "cmd": Qt.KeyboardModifier.MetaModifier,
        }
        qt_key = getattr(Qt.Key, f"Key_{self.key.upper()}", None)
        if qt_key is None and self.key.isdigit():
            qt_key = getattr(Qt.Key, f"Key_{self.key}")
        modifiers = Qt.KeyboardModifier.NoModifier
        for name in self.modifiers:
            modifiers |= modifier_map[name]
        return QKeySequence(modifiers | qt_key)


class GlobalHotkey(QObject):
    """Listen for a user-selected global hotkey using AppKit monitors."""

    activated = Signal()

    def __init__(
        self,
        binding: HotkeyBinding | None | object = _UNSET,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.binding = HotkeyBinding.from_storage(None) if binding is _UNSET else binding
        self.available = False
        self._running = False
        self._global_monitor = None
        self._local_monitor = None
        self._nsevent = None
        self._event_mask = 0
        self._modifier_mask = self.binding.modifier_mask if self.binding is not None else 0
        try:
            from AppKit import NSEvent, NSEventMaskKeyDown
        except ImportError:
            return
        self._nsevent = NSEvent
        self._event_mask = NSEventMaskKeyDown
        self.available = True

    def start(self) -> bool:
        if not self.available or self._nsevent is None:
            return False
        if self.binding is None:
            return True
        if self._running:
            return True

        def handle_global(event):
            self._handle_event(event)

        def handle_local(event):
            self._handle_event(event)
            return event

        self._global_monitor = self._nsevent.addGlobalMonitorForEventsMatchingMask_handler_(
            self._event_mask, handle_global
        )
        self._local_monitor = self._nsevent.addLocalMonitorForEventsMatchingMask_handler_(
            self._event_mask, handle_local
        )
        self._running = self._global_monitor is not None or self._local_monitor is not None
        return self._running

    def set_binding(self, binding: HotkeyBinding | None) -> bool:
        was_running = self._running
        self.stop()
        self.binding = binding
        self._modifier_mask = binding.modifier_mask if binding is not None else 0
        if binding is None:
            return True
        return not was_running or self.start()

    def _handle_event(self, event) -> None:
        if self.binding is None:
            return
        try:
            if bool(event.isARepeat()):
                return
            key_code = int(event.keyCode())
            flags = int(event.modifierFlags())
        except Exception:
            return
        if key_code == self.binding.key_code and (flags & self._modifier_mask) == self._modifier_mask:
            self.activated.emit()

    def stop(self) -> None:
        if self._nsevent is not None:
            if self._global_monitor is not None:
                self._nsevent.removeMonitor_(self._global_monitor)
            if self._local_monitor is not None:
                self._nsevent.removeMonitor_(self._local_monitor)
        self._global_monitor = None
        self._local_monitor = None
        self._running = False
