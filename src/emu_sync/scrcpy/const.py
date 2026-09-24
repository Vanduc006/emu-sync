"""Hằng số protocol scrcpy — pin theo scrcpy v4.1.

Nguồn đối chiếu (đã verify từ source scrcpy):
- server/src/main/java/com/genymobile/scrcpy/control/ControlMessage.java (type IDs)
- server/src/main/java/com/genymobile/scrcpy/device/DesktopConnection.java (socket name, device meta)
- app/tests/test_control_msg_serialize.c (byte layout — dùng làm test vectors)
"""

SERVER_VERSION = "4.1"
SERVER_JAR_NAME = "scrcpy-server-v4.1.jar"
SERVER_DEVICE_PATH = "/data/local/tmp/emu-sync-scrcpy.jar"

SOCKET_NAME_PREFIX = "scrcpy"
DEVICE_NAME_FIELD_LENGTH = 64

# ControlMessage types
TYPE_INJECT_KEYCODE = 0
TYPE_INJECT_TEXT = 1
TYPE_INJECT_TOUCH_EVENT = 2
TYPE_INJECT_SCROLL_EVENT = 3
TYPE_BACK_OR_SCREEN_ON = 4
TYPE_EXPAND_NOTIFICATION_PANEL = 5
TYPE_EXPAND_SETTINGS_PANEL = 6
TYPE_COLLAPSE_PANELS = 7
TYPE_GET_CLIPBOARD = 8
TYPE_SET_CLIPBOARD = 9
TYPE_SET_DISPLAY_POWER = 10
TYPE_ROTATE_DEVICE = 11
TYPE_OPEN_HARD_KEYBOARD_SETTINGS = 15

# MotionEvent actions
ACTION_DOWN = 0
ACTION_UP = 1
ACTION_MOVE = 2

# KeyEvent actions
KEY_ACTION_DOWN = 0
KEY_ACTION_UP = 1

# Pointer ids (u64; control_msg.h)
POINTER_ID_MOUSE = 0xFFFFFFFFFFFFFFFF  # -1
POINTER_ID_GENERIC_FINGER = 0xFFFFFFFFFFFFFFFE  # -2

# MotionEvent buttons
BUTTON_PRIMARY = 1

# Android keycodes (subset dùng cho mirror bàn phím)
AKEYCODE_A = 29  # ... AKEYCODE_Z = 54 (theo alphabet)
AKEYCODE_BACK = 4
AKEYCODE_DPAD_UP = 19
AKEYCODE_DPAD_DOWN = 20
AKEYCODE_DPAD_LEFT = 21
AKEYCODE_DPAD_RIGHT = 22
AKEYCODE_DEL = 67  # backspace
AKEYCODE_ENTER = 66
AKEYCODE_ESCAPE = 111
AKEYCODE_TAB = 61
AKEYCODE_SPACE = 62

# Modifier keycodes (Android)
AKEYCODE_SHIFT_LEFT = 59
AKEYCODE_SHIFT_RIGHT = 60
AKEYCODE_ALT_LEFT = 57
AKEYCODE_ALT_RIGHT = 58
AKEYCODE_CTRL_LEFT = 113
AKEYCODE_CTRL_RIGHT = 114
AKEYCODE_META_LEFT = 117
AKEYCODE_META_RIGHT = 118
AKEYCODE_CAPS_LOCK = 115

# KeyEvent metastate (AMETA_*)
AMETA_SHIFT_ON = 0x1
AMETA_ALT_ON = 0x02
AMETA_CTRL_ON = 0x1000
AMETA_META_ON = 0x10000
AMETA_CAPS_LOCK_ON = 0x100000
