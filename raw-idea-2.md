---
id: raw-idea-2
title: "emu-sync — đồng bộ thao tác giữa nhiều giả lập Android (capture ở host, bơm qua scrcpy)"
created: 2026-09-23
updated: 2026-09-24
status: building
maturity: mvp-verified
type: tool-project-idea
program: side-project
domain: [android, adb, emulator, input-injection, dev-tooling]
skills-match: [event-driven, microservices, data-engineering]
source: brainstorming session
tags: [android, adb, scrcpy, emulator, group-control, broadcast-input, getevent, multi-device]
related-files: [emu-sync/README.md]
---
# Raw Idea 2 — emu-sync: đồng bộ thao tác giữa các cửa sổ giả lập

## 1. Ý tưởng gốc (nguyên văn)

> "Tôi có khoảng 5 tab giả lập Android. Chọn vào máy giả lập nào thì sẽ thao tác trên giả lập đó, đồng thời các tab giả lập khác cũng đồng bộ thao tác theo tab đang được chọn."

Làm rõ sau đó: **thao tác trên cửa sổ giả lập gốc** (LDPlayer/AVD…), **web chỉ để xem màn hình từ xa**; ưu tiên số 1 là *thao tác đồng bộ chạy được*.

## 2. Hướng đi đã chốt

- **Capture = `getevent` bên trong máy master** (qua ADB): đọc thẳng sự kiện thiết bị cảm ứng trong nhân Android → toạ độ *chính xác tuyệt đối*, không phải đoán tỉ lệ/viền cửa sổ, chạy giống nhau trên macOS & Windows.
- **Inject = scrcpy-server v4.1 chế độ control-only** (`video=false audio=false control=true`): kênh bơm nhanh, hỗ trợ multi-touch, mọi giả lập chỉ cần ADB.
- **Chỉ nghe máy master** → không có vòng lặp echo. Master = cửa sổ bạn click (focus watcher — M3); có override thủ công.
- **Web viewer = phase sau** (xem 5 màn hình + nút chọn master/toggle sync).

```
cửa sổ master (bạn click/kéo/scroll)
      │ adb shell getevent -t   (chỉ master)
      ▼
 emu-sync (Python) ── chuẩn hoá 0..1 ──► serialize riêng cho từng máy nhận
      │ adb reverse + scrcpy control socket
      ▼
 scrcpy-server trên từng máy nhận ──► touch/key đúng vị trí
```

## 3. Đã làm & kiểm chứng (cập nhật 2026-09-24, trên Mac / 2 AVD)

Repo `~/Workspace/docs/emu-sync` (Python + adbutils + pytest; **28 unit test pass**, byte-exact với test vectors của scrcpy).

| Hạng mục | Kết quả đo được |
|---|---|
| M1 — inject control-only | `emu-sync key <serial> 3` đưa máy từ Settings về launcher ✓ |
| M2 — broadcast tap | tap lên master → **cả 2 máy mở cùng SearchActivity** (assert bằng foreground activity) ✓ |
| M2 — broadcast swipe/scroll | cuộn master → target cuộn theo, **screenshot similarity 1.000** (cùng vị trí) ✓ |
| Latency fan-out | p50 = 0.2 ms, p95 = 2.4 ms (nhận event → ghi xong control socket) |
| **Sync bàn phím** | gõ `zebra42` trên master → **cả 2 máy đều nhận** (uiautomator dump); pause → `nopass99` không lây sang target; resume → `okdone` lây lại ✓ |
| UI | Desktop app (pywebview) + panel web: quét/connect device, chọn máy chính, toggle sync, phím tắt `Ctrl+Alt+P` pause/resume, thao tác trực tiếp (tap/scroll/key/back/text), log input ✓ |

## 4. Phát hiện kỹ thuật quan trọng (đã trả giá để biết)

1. **Listener phải dual-stack (IPv6 + IPv4-mapped)**: adb reverse không kết nối tới listener IPv4-only (macOS + adb 37). IPv4-only ⇒ server không bao giờ cắm vào (và không log lỗi gì!).
2. **Emulator bỏ qua POSITION events khi con trỏ không di chuyển**: tap thứ hai cùng toạ độ chỉ có TRACKING_ID + SYN ⇒ parser phải *kế thừa vị trí cuối*, nếu không touch sẽ rơi vào (0,0).
3. **`getevent` chỉ nhận 1 device**: chạy không tham số (nghe tất cả) rồi **lọc theo số device** trong parser.
4. **`getevent -p` (không `-l`)** cho mã hex dạng số; `-pl` cho label — parser hỗ trợ cả hai.
5. **AVD có 11 thiết bị `virtio_input_multi_touch_1..11`**: thiết bị thật nhận chuột là `..._1` (/dev/input/event1).
6. **AVD không có thiết bị wheel & không có bàn phím phần cứng**: wheel được emulator dịch thành gesture (vẫn đồng bộ qua touch); mirror bàn phím chỉ hoạt động với máy lộ keyboard device.
7. **Control-only ⇒ toạ độ RAW theo pixel thiết bị** (không map/drop); nếu bật video thì bắt buộc `screen_size` == kích thước video frame của *từng* máy nhận.
8. `scid` là **hex 31-bit** (không vượt 0x7FFFFFFF); version server phải khớp đúng `"4.1"`.
9. **AVD mặc định `hw.keyboard=no`** → không có thiết bị bàn phím trong nhân ⇒ gõ phím từ host **không vào guest**, `getevent` cũng không thấy gì. Bật `hw.keyboard=yes` (config.ini) + restart → xuất hiện `qwerty2` (/dev/input/event12) → vừa gõ được vừa sync được. (`dev_avd.sh` tự bật khi tạo AVD mới)
10. **Linux keycode xếp theo vị trí QWERTY, Android xếp theo alphabet** — không suy ra được bằng công thức, phải dùng bảng tường minh (bug "gõ s ra b" đã fix nhờ unit test).
11. Snapshot quickboot có thể "nhiễm" trạng thái lỗi (ANR dialog lưu vào snapshot → mọi lần boot sau đều dính ANR). Xử lý: `dev_avd.sh start --cold` (`-no-snapshot-load -no-snapshot-save`).
12. Chỉ được chạy **1 server sync** cho một master — 2 instance cùng nghe 1 máy ⇒ inject trùng lặp.

## 5. Bối cảnh OSS & đối thủ

- **LDPlayer (Synchronizer)** và **BlueStacks 5 (Sync operations)** đã có sync sẵn — dùng ngay được nếu chỉ một loại giả lập. emu-sync hơn ở: trộn nhiều loại giả lập, luật master/toggle riêng, viewer từ xa.
- **Escrcpy** (~11.9k⭐, broadcast input) / **QtScrcpy** (~32.1k⭐, group control): cùng dùng scrcpy nhưng thao tác **trên cửa sổ của tool**, không phải trên cửa sổ giả lập gốc.
- **ws-scrcpy / DeviceFarmer STF / android-web-mirror**: viewer web, không broadcast.

## 6. Bước tiếp theo

- [ ] **M3**: FocusWatcher (click cửa sổ nào = máy chính đó; macOS + Windows) + hotkey toggle sync từng máy.
- [ ] **Quản lý máy ảo trong app**: tạo/start/stop/xoá AVD (`avdmanager` + `sdkmanager`), quản lý profile (`config.ini`, snapshot); trên Windows: LDPlayer (`ldconsole`), MEmu (`memuc`) đầy đủ; BlueStacks hạn chế (chỉ launch/stop instance).
- [ ] **Windows test**: `install_windows.ps1` + `EmuSync.bat`; xác nhận `getevent` thấy bàn phím/chuột của LDPlayer/BlueStacks (nếu vendor inject qua InputManager → fallback bắt sự kiện mức OS).
- [ ] Xem màn hình real-time (WebCodecs) — hiện đã có preview ảnh tuỳ chọn.
- [ ] Ghi/replay input stream (regression), screenshot batch, cài APK hàng loạt.

## 7. Từ khoá tra cứu thêm

- scrcpy control protocol / control-only mode
- Linux input MT protocol B (ABS_MT_SLOT/TRACKING_ID/POSITION), evdev, getevent
- adb reverse vs forward với localabstract socket (dual-stack!)
- emulator console (`adb emu event mouse/send/text`)
- redroid (Android in Docker) — scale nhiều instance
- Appium multi-device parallel / Airtest batch execution (hướng automation alternative)
