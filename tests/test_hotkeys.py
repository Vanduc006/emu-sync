"""Test phím tắt toàn cục (label + keycode để chống gõ nhầm phím hotkey vào máy ảo)."""

from emu_sync.hotkeys import keycode_of_spec, label_of


def test_label_of():
    assert label_of("<ctrl>+<alt>+p") == "Ctrl+Alt+P"
    assert label_of("<cmd>+<shift>+s") == "Cmd+Shift+S"


def test_keycode_of_spec():
    assert keycode_of_spec("<ctrl>+<alt>+p") == 25  # KEY_P
    assert keycode_of_spec("<ctrl>+<alt>+1") == 2  # KEY_1
    assert keycode_of_spec("<ctrl>+<alt>+f12") is None
