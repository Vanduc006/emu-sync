"""Cấu hình mặc định của emu-sync."""

# Hệ số quy đổi 1 tick lăn chuột → đơn vị scroll của scrcpy ([-16, 16]).
# Tinh chỉnh sau khi thử thực tế (M2).
SCROLL_UNITS_PER_TICK = 1.0

# Dấu của vscroll: REL_WHEEL dương (lăn lên) ⇒ slave phải cuộn cùng hướng
# như master. Chốt bằng thực nghiệm trên AVD (đổi dấu nếu ngược).
SCROLL_VSCROLL_SIGN = -1.0

# Chu kỳ poll cửa sổ foreground (giây) — dùng ở M3.
FOCUS_POLL_INTERVAL = 0.15

# Số mẫu latency giữ lại cho p50/p95.
LATENCY_WINDOW = 500

# Dải cổng ADB phổ biến của các giả lập (dùng khi "Quét cổng giả lập").
# AVD đăng ký sẵn với adb; LDPlayer/BlueStacks/MEmu/Nox thường cần `adb connect`.
EMULATOR_PORT_RANGES = [
    range(5554, 5586),    # AVD / LDPlayer / BlueStacks (adb thường = console + 1)
    range(62001, 62026),  # Nox
    range(21503, 21526),  # MEmu
]

# Thời gian chờ mỗi lần thử `adb connect` khi quét cổng (giây).
SCAN_CONNECT_TIMEOUT = 0.4
