"""Bảng map Linux keycode → Android keycode (subset cho mirror bàn phím).

Linux:  include/uapi/linux/input-event-codes.h
Android: KeyEvent.KEYCODE_* (AKEYCODE)
"""

from __future__ import annotations

# Linux keycode → Android keycode
LINUX_TO_ANDROID: dict[int, int] = {
    1: 111,   # KEY_ESC → AKEYCODE_ESCAPE
    14: 67,   # KEY_BACKSPACE → AKEYCODE_DEL
    15: 61,   # KEY_TAB → AKEYCODE_TAB
    28: 66,   # KEY_ENTER → AKEYCODE_ENTER
    57: 62,   # KEY_SPACE → AKEYCODE_SPACE
    103: 19,  # KEY_UP → AKEYCODE_DPAD_UP
    105: 21,  # KEY_LEFT → AKEYCODE_DPAD_LEFT
    106: 22,  # KEY_RIGHT → AKEYCODE_DPAD_RIGHT
    108: 20,  # KEY_DOWN → AKEYCODE_DPAD_DOWN
}

# Chữ cái: Linux keycode xếp theo VỊ TRÍ QWERTY, Android xếp theo ALPHABET
# → phải dùng bảng tường minh (không thể suy ra bằng công thức).
LINUX_TO_ANDROID.update(
    {
        30: 29,  # KEY_A → AKEYCODE_A (29)
        48: 30,  # KEY_B
        46: 31,  # KEY_C
        32: 32,  # KEY_D
        18: 33,  # KEY_E
        33: 34,  # KEY_F
        34: 35,  # KEY_G
        35: 36,  # KEY_H
        23: 37,  # KEY_I
        36: 38,  # KEY_J
        37: 39,  # KEY_K
        38: 40,  # KEY_L
        50: 41,  # KEY_M
        49: 42,  # KEY_N
        24: 43,  # KEY_O
        25: 44,  # KEY_P
        16: 45,  # KEY_Q
        19: 46,  # KEY_R
        31: 47,  # KEY_S
        20: 48,  # KEY_T
        22: 49,  # KEY_U
        47: 50,  # KEY_V
        17: 51,  # KEY_W
        45: 52,  # KEY_X
        21: 53,  # KEY_Y
        44: 54,  # KEY_Z
    }
)

# Chữ số: Linux KEY_1..KEY_9 = 2..10, KEY_0 = 11; Android AKEYCODE_0..9 = 7..16
for _d in range(1, 10):
    LINUX_TO_ANDROID[1 + _d] = 7 + _d  # KEY_1(2)→8 ... KEY_9(10)→16
LINUX_TO_ANDROID[11] = 7  # KEY_0 → AKEYCODE_0

# Phím bổ trợ, dấu câu, điều hướng (mở rộng cho sync bàn phím)
LINUX_TO_ANDROID.update(
    {
        29: 113,   # KEY_LEFTCTRL → CTRL_LEFT
        97: 114,   # KEY_RIGHTCTRL → CTRL_RIGHT
        42: 59,    # KEY_LEFTSHIFT → SHIFT_LEFT
        54: 60,    # KEY_RIGHTSHIFT → SHIFT_RIGHT
        56: 57,    # KEY_LEFTALT → ALT_LEFT
        100: 58,   # KEY_RIGHTALT → ALT_RIGHT
        125: 117,  # KEY_LEFTMETA → META_LEFT
        126: 118,  # KEY_RIGHTMETA → META_RIGHT
        58: 115,   # KEY_CAPSLOCK → CAPS_LOCK
        51: 55,    # KEY_COMMA → COMMA
        52: 56,    # KEY_DOT → PERIOD
        12: 69,    # KEY_MINUS → MINUS
        13: 70,    # KEY_EQUAL → EQUALS
        53: 76,    # KEY_SLASH → SLASH
        39: 74,    # KEY_SEMICOLON → SEMICOLON
        40: 75,    # KEY_APOSTROPHE → APOSTROPHE
        41: 68,    # KEY_GRAVE → GRAVE
        26: 71,    # KEY_LEFTBRACE → LEFT_BRACKET
        27: 72,    # KEY_RIGHTBRACE → RIGHT_BRACKET
        43: 73,    # KEY_BACKSLASH → BACKSLASH
        111: 112,  # KEY_DELETE → FORWARD_DEL
        102: 122,  # KEY_HOME → MOVE_HOME
        107: 123,  # KEY_END → MOVE_END
        104: 92,   # KEY_PAGEUP → PAGE_UP
        109: 93,   # KEY_PAGEDOWN → PAGE_DOWN
        110: 124,  # KEY_INSERT → INSERT
        158: 4,    # KEY_BACK → AKEYCODE_BACK
    }
)


def linux_to_android(linux_keycode: int) -> int | None:
    return LINUX_TO_ANDROID.get(linux_keycode)
