"""Native macOS menu-bar status item for the frozen application."""

from __future__ import annotations

import weakref

import objc
from AppKit import (
    NSImage,
    NSMenu,
    NSMenuItem,
    NSStatusBar,
    NSStatusItemBehaviorRemovalAllowed,
    NSVariableStatusItemLength,
)
from Foundation import NSObject


class _StatusItemController(NSObject):
    """Objective-C target retained by NSStatusItem and its menu items."""

    def initWithWindow_(self, window):
        self = objc.super(_StatusItemController, self).init()
        if self is None:
            return None
        self._window_ref = weakref.ref(window)
        self._status_bar = NSStatusBar.systemStatusBar()
        self._status_item = self._status_bar.statusItemWithLength_(NSVariableStatusItemLength)
        button = self._status_item.button()
        image = NSImage.imageWithSystemSymbolName_accessibilityDescription_("function", "FormulaOCR")
        if image is not None:
            image.setTemplate_(True)
            button.setImage_(image)
        button.setToolTip_("FormulaOCR")
        self._status_item.setMenu_(self._build_menu())
        self._status_item.setAutosaveName_("FormulaOCR")
        self._status_item.setBehavior_(NSStatusItemBehaviorRemovalAllowed)
        self._status_item.setVisible_(True)
        button.setHidden_(False)
        return self

    def _build_menu(self):
        menu = NSMenu.alloc().init()
        self._add_item(menu, "打开 FormulaOCR", "openFormulaOCR:")
        self._add_item(menu, "截图 OCR", "captureOCR:")

        settings_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("设置", None, "")
        settings_menu = NSMenu.alloc().initWithTitle_("设置")
        self._add_item(settings_menu, "自定义模型与 API…", "apiSettings:")
        self._add_item(settings_menu, "修改截图快捷键…", "hotkeySettings:")
        self._add_item(settings_menu, "窗口行为…", "windowSettings:")
        self._add_item(settings_menu, "界面与布局…", "layoutSettings:")
        self._add_item(settings_menu, "历史记录…", "historySettings:")
        settings_item.setSubmenu_(settings_menu)
        menu.addItem_(settings_item)

        menu.addItem_(NSMenuItem.separatorItem())
        self._add_item(menu, "退出", "quitFormulaOCR:")
        return menu

    def _add_item(self, menu, title: str, selector: str) -> None:
        item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, selector, "")
        item.setTarget_(self)
        menu.addItem_(item)

    def _window(self):
        return self._window_ref()

    def openFormulaOCR_(self, _sender) -> None:
        window = self._window()
        if window is not None:
            window._show_from_tray()

    def captureOCR_(self, _sender) -> None:
        window = self._window()
        if window is not None:
            window.capture_screen()

    def hotkeySettings_(self, _sender) -> None:
        window = self._window()
        if window is not None:
            window.show_settings_center("hotkey")

    def apiSettings_(self, _sender) -> None:
        window = self._window()
        if window is not None:
            window.show_settings_center("api")

    def windowSettings_(self, _sender) -> None:
        window = self._window()
        if window is not None:
            window.show_settings_center("general")

    def historySettings_(self, _sender) -> None:
        window = self._window()
        if window is not None:
            window.show_settings_center("history")

    def layoutSettings_(self, _sender) -> None:
        window = self._window()
        if window is not None:
            window.show_settings_center("layout")

    def quitFormulaOCR_(self, _sender) -> None:
        window = self._window()
        if window is not None:
            window.quit_application()

    def close(self) -> None:
        if getattr(self, "_status_item", None) is not None:
            self._status_bar.removeStatusItem_(self._status_item)
            self._status_item = None


class MacStatusItem:
    """Small lifetime wrapper around the native status item controller."""

    def __init__(self, window) -> None:
        self._controller = _StatusItemController.alloc().initWithWindow_(window)

    def close(self) -> None:
        if self._controller is not None:
            self._controller.close()
            self._controller = None
