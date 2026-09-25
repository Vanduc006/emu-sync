# emu-sync

Đồng bộ thao tác giữa nhiều giả lập Android: bạn thao tác trên **cửa sổ giả lập gốc**
(BlueStacks, LDPlayer, MEmu, Nox, AVD…), các giả lập khác **chạy y hệt tại đúng vị trí** —
cả click/kéo/scroll lẫn **gõ bàn phím**.

## Cách hoạt động

1. **Capture**: đọc sự kiện input trong lòng Android của máy master qua ADB (`getevent`)
   → parse MT protocol B (touch), wheel, và bàn phím (`EV_KEY` + modifier Shift/Ctrl/Alt).
2. **Inject**: serialize control message của **scrcpy-server v4.1** (chế độ `control-only`)
   → bơm sang từng máy nhận, toạ độ nhân theo kích thước hiển thị của máy đó.

Chỉ **máy master** được nghe ⇒ không có vòng lặp echo. Không cài gì lên giả lập, không cần root.

```
cửa sổ master (bạn click/kéo/scroll/gõ phím)
      │  adb shell getevent   (chỉ master)
      ▼
  emu-sync (Python)  ── chuẩn hoá ──► serialize riêng cho từng máy nhận
      │  adb reverse + scrcpy control socket
      ▼
  scrcpy-server trên từng máy nhận  ──►  touch/key đúng vị trí
```

---

## Setup macOS (từ đầu)

```bash
# 1) Công cụ nền: adb + Android command-line tools + uv (python runner)
brew install --cask android-platform-tools android-commandlinetools
brew install uv            # hoặc: curl -LsSf https://astral.sh/uv/install.sh | sh

# 2) Vào thư mục dự án (repo này)
cd ~/Workspace/docs/emu-sync

# 3) Môi trường Python (tạo .venv + cài dependencies, gồm cả desktop app)
uv venv && uv pip install -e ".[dev,desktop]"

# 4) Tạo 2 máy ảo AVD (lần đầu tải SDK ~5GB, chỉ 1 lần)
scripts/dev_avd.sh create

# 5) Mở 2 máy ảo (có cửa sổ để thao tác)
scripts/dev_avd.sh start

# 6) Mở app quản lý
uv run emu-sync app        # hoặc double-click scripts/EmuSync.command
```

Trong app: **Tìm máy ảo** → **Chọn làm máy chính** ở máy bạn sẽ thao tác → click/kéo/scroll/gõ
trực tiếp trên **cửa sổ giả lập** đó, các máy còn lại chạy theo.

> `dev_avd.sh` tự bật `hw.keyboard=yes` khi tạo AVD (điều kiện để gõ phím + sync bàn phím).
> Lệnh hữu ích: `scripts/dev_avd.sh start --headless` (không cửa sổ, nhẹ máy),
> `--cold` (bỏ qua snapshot khi máy ảo bị treo/lỗi), `scripts/dev_avd.sh stop`.

## Setup Windows (từ đầu)

**Cách 1 — CMD, KHÔNG cần PowerShell (khuyến nghị):**

1. Cài **Python 3.11+** từ <https://www.python.org/downloads/windows/> —
   khi cài nhớ tick **“Add python.exe to PATH”**.
2. Trong thư mục repo: **double-click `scripts\install_windows.bat`**
   (tự tải adb nếu thiếu + tạo `.venv` + cài dependencies; cần mạng).
3. **Double-click `scripts\EmuSync.bat`** để mở app.

Chạy thủ công trong CMD (nếu muốn tự làm từng bước):

```bat
cd <thu-muc-repo>
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[desktop]"
.venv\Scripts\emu-sync.exe app
```

**Cách 2 — PowerShell (nếu muốn dùng `uv`):**

```powershell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
powershell -ExecutionPolicy ByPass -File scripts\install_windows.ps1
```

- Cần **WebView2 runtime** (Windows 10/11 hầu hết có sẵn; nếu thiếu tải "WebView2 Evergreen
  Runtime" từ Microsoft).
- Bật ADB trong giả lập: **BlueStacks 5** → Settings → Advanced → **Android Debug Bridge**;
  **LDPlayer / MEmu / Nox** thường đã bật sẵn. Rồi bấm **Tìm máy ảo** — emu-sync tự
  `adb connect` các cổng phổ biến (5555/5557…, Nox 62001…, MEmu 21503…).
- **adb**: nếu máy chưa có adb trong PATH, `install_windows.bat` tự tải **platform-tools**
  vào `tools\platform-tools\` (app tự dùng bản đó, không cần thêm PATH).

### Chạy máy ảo Android (AVD/QEMU) trên Windows

Không bắt buộc — nếu bạn dùng BlueStacks/LDPlayer/MEmu thì bỏ qua mục này.

**Cách A — Android Studio (dễ nhất):** cài Android Studio → *Device Manager* →
*Create Device* → chọn system image → **Run** (cửa sổ máy ảo hiện ra để thao tác trực tiếp).

**Cách B — CMD, không cần Android Studio, không cần PowerShell**
(cần **Java 17+**: tải tại <https://adoptium.net>):

```bat
scripts\dev_avd_windows.bat create   :: tải emulator + system image (~2GB), tạo emu1/emu2
scripts\dev_avd_windows.bat start    :: mở 2 máy ảo (mỗi máy 1 cửa sổ)
scripts\dev_avd_windows.bat stop
```

- Script tự bật `hw.keyboard=yes` (điều kiện để gõ phím + sync bàn phím).
- Nếu emulator báo thiếu tăng tốc: bật **Windows Hypervisor Platform** trong
  *Turn Windows features on or off* rồi khởi động lại máy.

**Build file `.exe`** (chạy trên Windows, PyInstaller không cross-compile):

- CMD: **double-click `scripts\build_windows.bat`**
- PowerShell: `powershell -ExecutionPolicy ByPass -File scripts\build_windows.ps1`

→ Kết quả: `dist\EmuSync\EmuSync.exe` (double-click để chạy).

## Dùng với giả lập có sẵn (không cần tạo AVD)

1. Mở giả lập của bạn (BlueStacks / LDPlayer / MEmu / Nox…) và **bật ADB** trong settings của nó.
2. Mở emu-sync → bấm **Tìm máy ảo** (hoặc nhập địa chỉ vào *Nâng cao → Kết nối ADB thủ công*,
   vd `127.0.0.1:5555`).

---

## Dùng app (khuyến nghị)

1. **Tìm máy ảo** — tự dò AVD/BlueStacks/LDPlayer/MEmu/Nox đang chạy và tự `adb connect`.
2. **Chọn làm máy chính** ở máy bạn sẽ thao tác (ô viền vàng = máy chính).
3. Thao tác trực tiếp trên **cửa sổ giả lập gốc** của máy chính (click/kéo/scroll/gõ bàn phím) —
   các máy còn lại chạy y hệt tại đúng vị trí.
4. Công tắc **Nhận thao tác đồng bộ**: tắt ở máy nào thì máy đó không chạy theo.
5. **Phím tắt `Ctrl+Alt+P`**: tạm dừng / tiếp tục đồng bộ **bất cứ lúc nào** (kể cả khi đang thao
   tác cửa sổ giả lập) — dùng khi cần thao tác riêng từng máy. Đổi phím:
   `uv run emu-sync app --hotkey "<ctrl>+<shift>+s"`; tắt bằng `--hotkey none`.
6. **Hiện màn hình**: bật xem trước từng máy (mặc định tắt cho nhẹ).
   **Hiển thị**: chọn **1/2/3/4/5 máy mỗi hàng** (kiểu grid, lưu theo máy bạn dùng).
7. **Nhật ký input** + mục **Nâng cao** trong từng máy: tap/scroll/key/back/gõ chữ, nghe thử
   input, kết nối ADB thủ công, thống kê — tương đương CLI.
8. **Máy ảo (AVD)** — quản lý ngay trong app: **tạo máy ảo mới** (chọn image, RAM, cores,
   độ phân giải, bàn phím), **Chạy / Tắt**, **💾 Lưu state**, **⟲ Chạy sạch** (khi máy lỗi),
   **✎ Cấu hình** (profile lưu theo từng máy trong `config.ini`).
   Máy ảo **tự lưu state khi tắt** (quickboot snapshot) — mở lại đúng chỗ đang dùng,
   app/data đã cài vẫn còn nguyên, **không phải máy mới từ đầu**.

## Dùng nhanh (CLI — cho phần nâng cao)

```bash
uv run emu-sync devices                    # liệt kê máy + kích thước màn hình
uv run emu-sync tap emulator-5554 540 1200 # tap 1 điểm
uv run emu-sync text emulator-5554 "hello" # gõ chữ
uv run emu-sync sniff emulator-5554        # xem event parse được (debug)
uv run emu-sync run --master emulator-5554 # đồng bộ (không cần app)
uv run emu-sync ui                         # panel web (không cửa sổ native)
```

## Kiểm tra / tự test

```bash
uv run pytest -q                                        # 28 unit test (protocol, parser, engine)
uv run python scripts/e2e_sync_check.py --master emulator-5554 --action swipe   # touch sync
uv run python scripts/e2e_keyboard_check.py --master emulator-5554 --text hello # bàn phím sync
```

## Xử lý sự cố

| Hiện tượng | Cách xử lý |
|---|---|
| App không thấy máy ảo | Bật ADB trong giả lập rồi bấm **Tìm máy ảo**; kiểm tra `adb devices` (nếu trống: `adb kill-server && adb start-server`) |
| Gõ phím không vào máy ảo AVD | Cần `hw.keyboard=yes` trong `~/.android/avd/<tên>.avd/config.ini`, rồi **restart** AVD (script `dev_avd.sh` tự bật khi tạo AVD mới) |
| AVD treo / "Application Not Responding" liên tục | Snapshot bị nhiễm lỗi: `scripts/dev_avd.sh start --cold` (hoặc xoá `~/.android/avd/<tên>.avd/snapshots`) |
| Phím tắt `Ctrl+Alt+P` không hoạt động (macOS) | Cấp quyền **Accessibility + Input Monitoring** cho Terminal/EmuSync trong System Settings → Privacy & Security |
| Session "lỗi kết nối" | Bấm **Thử lại kết nối** trong Nâng cao (app cũng tự thử lại mỗi 10s) |
| Cổng bận khi mở app | App tự chọn cổng trống kế tiếp — xem dòng `UI nội bộ: http://…` trong terminal |
| Chạy nhầm 2 app cùng lúc | Chỉ chạy **1** app/`ui` cho mỗi master (2 instance sẽ inject trùng) |

## Cấu trúc

- `src/emu_sync/scrcpy/` — client control-only cho scrcpy-server (byte-exact protocol v4.1)
- `src/emu_sync/capture/` — parser `getevent` (MT-B, wheel, bàn phím + metastate)
- `src/emu_sync/sync_engine.py` — chuẩn hoá toạ độ + fan-out (touch/scroll/key)
- `src/emu_sync/controller.py`, `webapp.py`, `static/index.html` — app quản lý
- `scripts/dev_avd.sh` — tạo/chạy/tắt AVD (tự bật `hw.keyboard`)
- `scripts/e2e_*.py` — script kiểm thử E2E (touch / bàn phím)
- `scripts/EmuSync.command` (macOS) · `scripts/EmuSync.bat` + `install_windows.ps1` + `build_windows.ps1` (Windows)

## Trạng thái & lộ trình

| Hạng mục | Trạng thái |
|---|---|
| Inject control-only (scrcpy v4.1) + CLI tap/scroll/key/back/text | ✅ verified |
| Sync touch / scroll (đúng vị trí) | ✅ verified E2E (tap → cùng activity; swipe → similarity 1.000) |
| **Sync bàn phím** (kể cả Shift/Ctrl/Alt) | ✅ verified E2E (gõ `zebra42` → cả 2 máy; pause → không lây) |
| App quản lý + phím tắt pause/resume + log input | ✅ verified |
| Quản lý máy ảo trong app (tạo/chạy/tắt/lưu state/cấu hình profile) | ✅ verified |
| Master tự động theo cửa sổ đang thao tác (M3) | ⏳ |
| Viewer real-time (WebCodecs) — hiện có preview ảnh tuỳ chọn | ⏳ |
| Test trên Windows với LDPlayer/BlueStacks | ⏳ |

## Lưu ý quan trọng

- **Sync bàn phím** cần giả lập "lộ" thiết bị bàn phím ra nhân Android:
  - **AVD**: `hw.keyboard=yes` (script tự bật; AVD cũ sửa tay + restart) → có thiết bị `qwerty2`.
  - **LDPlayer/BlueStacks/MEmu**: thường nhận bàn phím trực tiếp; kiểm tra bằng `emu-sync sniff`
    (thấy dòng `EV_KEY` là sync được).
- Bàn phím mirror được: chữ cái, chữ số, dấu câu phổ biến, mũi tên, Enter/Backspace/Tab/Space/
  Esc, Shift/Ctrl/Alt/CapsLock. Phím ngoài bảng mã bị bỏ qua.
- Gõ tiếng Việt **có dấu** qua lệnh `text` có thể không vào (Android KeyCharacterMap); gõ dấu
  phụ thuộc IME bên trong máy ảo.
- LDPlayer (Synchronizer) và BlueStacks 5 (Sync operations) **đã có sẵn tính năng sync** — nếu chỉ
  dùng một loại giả lập, thử built-in trước. emu-sync dành cho: trộn nhiều loại giả lập, luật
  master/toggle riêng, và tương lai viewer từ xa.
- Nên đặt **cùng resolution + orientation** cho các máy để "đúng vị trí" là tuyệt đối.
- App/game **phát hiện giả lập** và chặn? Xem hướng dẫn né detect (đổi props, root/Play
  Integrity, kernel/QEMU args): [`bypass.md`](./bypass.md).

## Ghi công

- [scrcpy](https://github.com/Genymobile/scrcpy) (Genymobile, Apache-2.0) — `scrcpy-server-v4.1.jar`
  được vendor trong `src/emu_sync/assets/` để đảm bảo đúng version protocol.
- [adbutils](https://github.com/openatx/adbutils) — ADB client Python.
