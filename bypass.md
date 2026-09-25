# bypass.md — Né bị phát hiện là giả lập (emulator detection bypass)

> **Mục đích:** test/QA app của bạn trên giả lập khi app/game chặn "máy ảo".
> Tài liệu tổng hợp các kỹ thuật công khai — chỉ dùng trên thiết bị/app bạn có quyền kiểm thử.
> Cập nhật: 2026-09-25 (số liệu thu trực tiếp từ AVD android-35 arm64).

---

## 1) App phát hiện giả lập bằng gì? (danh sách cần "dọn")

| Nhóm | Dấu hiệu điển hình (thực đo trên AVD) |
|---|---|
| **System props** | `ro.kernel.qemu`, `ro.boot.qemu`, `ro.boot.hardware=ranchu`, `ro.boot.hardware.vulkan=ranchu`, `ro.boot.boot_devices=…virtio_mmio`, `ro.hardware=ranchu`, `qemu.sf.lcd_density=420`, `init.svc.qemu-props=running`, `init.svc.goldfish-logcat=running`, `init.svc.ranchu-*` |
| **Build info** | `ro.build.fingerprint=google/sdk_gphone64_arm64/emu64a:15/…:userdebug/dev-keys`, `ro.build.type=userdebug`, `ro.debuggable=1`, `ro.product.model=sdk_gphone64_arm64` |
| **Đồ hoạ (GLES)** | `GLES: … Android Emulator OpenGL ES Translator (ANGLE… SwiftShader…)` — đọc qua GL_RENDERER |
| **Kernel/CPU** | `/proc/version` ("…-android15-8-…", build-host), `/proc/cpuinfo` (CPU ảo), `/proc/self/maps` |
| **File/device** | AVD đời mới **không còn** `/dev/qemu_pipe`, `/dev/socket/qemud` (đời cũ có) — đừng chỉ dựa vào 2 file này khi test |
| **Sensors/Pin/SIM** | không cảm biến thật, pin luôn trạng thái sạc ảo, IMEI/serial mặc định, không SIM thật |
| **Root/dev** | `su` có sẵn, `adb root` chạy được, SafetyNet/Play Integrity fail |

## 2) Audit nhanh (copy-paste)

```bash
adb shell "getprop | grep -iE 'qemu|goldfish|ranchu|virtio|vbox|genymotion'"
adb shell "getprop ro.build.fingerprint; getprop ro.hardware; getprop ro.build.type; getprop ro.debuggable; getprop ro.product.model; getprop ro.serialno"
adb shell cat /proc/version
adb shell "ls /dev/qemu_pipe /dev/socket/qemud /sys/qemu_trace 2>/dev/null; echo ---"
adb shell "dumpsys SurfaceFlinger | grep -iE 'GLES' | head -2"
```

## 3) Cách sửa theo tầng (từ dễ → khó)

### 3.1 Đổi props — "change thông tin device" (hiệu quả nhất, làm trước)

**a) AVD (Android Studio):** emulator có flag `-prop` (set lúc boot, đè giá trị ro.*):

```bash
emulator -avd emu1 -prop ro.kernel.qemu=0 -prop ro.boot.qemu=0 \
  -prop ro.hardware=qcom -prop ro.boot.hardware=qcom \
  -prop ro.product.model=SM-S911B -prop ro.product.brand=samsung \
  -prop ro.product.manufacturer=samsung \
  -prop ro.build.fingerprint=samsung/dm3qxxx/dm3q:14/UP1A.231005.007/S911BXXU1AWBD:user/release-keys
```

- Có thể truyền nhiều `-prop` (tên ≤32 ký tự, giá trị ≤92 ký tự).
- **Kiểm tra lại ngay**: `adb shell getprop ro.kernel.qemu` — nếu vẫn `1` thì có service (`qemu-props`) ghi đè sau boot → dùng cách (b) hoặc (3.3).

**b) Máy có root (LDPlayer/BlueStacks/MEmu, hoặc AVD + Magisk): `resetprop`**

```bash
su -c "resetprop ro.kernel.qemu 0"
su -c "resetprop ro.boot.qemu 0"
su -c "resetprop ro.hardware qcom"
su -c "resetprop ro.build.fingerprint samsung/dm3qxxx/dm3q:14/UP1A.231005.007/S911BXXU1AWBD:user/release-keys"
```

Tự động mỗi lần boot → tạo script Magisk `post-fs-data.sh`:

```sh
# /data/adb/modules/hideemu/post-fs-data.sh
#!/system/bin/sh
resetprop ro.kernel.qemu 0
resetprop ro.boot.qemu 0
resetprop ro.hardware qcom
# thêm các prop khác nếu detector còn kêu
```

**c) Trình giả lập có sẵn mục đổi model:**

| Giả lập | Ở đâu |
|---|---|
| **LDPlayer** | Settings → **Model / Device info** (đổi brand, model, IMEI, Android ID, MAC…); hoặc CLI `ldconsole modify --index 0 --model SM-S911B --manufacturer samsung --imei 35… --androidid … --mac …` (tuỳ phiên bản) |
| **BlueStacks 5** | Settings → **Device profile** (Samsung / OnePlus / Pixel…) — đã spoof sẵn khá tốt |
| **MEmu** | Settings → Device model; hoặc `memuc` |

### 3.2 Dọn service/file/đồ hoạ lộ dấu

- **Service names**: `init.svc.qemu-props`, `init.svc.goldfish-*`, `init.svc.ranchu-*` là prop → cùng cách 3.1 (resetprop không xoá được init.svc.*; phải dùng **kernel/ramdisk tự build** hoặc ẩn ở tầng khác). Nhiều app không soi nhóm này.
- **Đồ hoạ GLES** (`Android Emulator … SwiftShader`): trên AVD có thể đổi bằng GPU mode khác (`-gpu host / angle / swiftshader_indirect`) nhưng chuỗi nhận diện vẫn còn; cách triệt để là **kernel/driver ảo tự build** hoặc chấp nhận (ít app soi GL renderer).
- **File cũ** (`/dev/qemu_pipe`…): nếu còn thì ẩn bằng Magisk module bind-mount `/dev/null` đè lên.
- **Lib đặc trưng**: `/system/lib*/libc_malloc_debug_qemu.so` — ẩn/mask bằng Magisk module nếu app soi.

### 3.3 Kernel / boot / QEMU args — "change kernel"

- **`-kernel <file>`**: AVD hỗ trợ boot kernel tự build (bỏ chuỗi "ranchu/goldfish" trong config kernel, đổi `CONFIG_ARCH_*`/cmdline). Đây là cách sâu nhất, cũng tốn công nhất.
- **Kernel cmdline** (`androidboot.*`) chính là nguồn sinh `ro.boot.qemu`, `ro.boot.hardware` → sửa trong kernel/ramdisk hoặc qua `-qemu` args.
- **QEMU args trực tiếp** (đổi DMI — một số app đọc `/sys/class/dmi/id/*`):

```bash
emulator -avd emu1 -qemu -smbios type=1,manufacturer=ASUSTeK,product=ROG
```

- **`/proc/version`**: chỉ đổi được bằng kernel tự build (chuỗi do kernel in ra).

### 3.4 Root + Play Integrity (SafetyNet) — quan trọng nhất khi app "khó tính"

1. Cài **Magisk** → bật **Zygisk** → thêm app mục tiêu vào **DenyList**.
2. Cài **Shamiko** (ẩn root/Zygisk kỹ hơn, có whitelist).
3. Cài **PlayIntegrityFix (PIF)** để pass `MEETS_BASIC_INTEGRITY` + `MEETS_DEVICE_INTEGRITY`.
4. **Giới hạn cứng**: `MEETS_STRONG_INTEGRITY` (hardware key attestation) **không thể pass trên giả lập** — app nào bắt buộc mức này thì chỉ có dùng máy thật.
5. Kiểm tra: **YASNAC**, **Play Integrity API Checker**, **RootBeer**.

### 3.5 Nếu app vẫn chặn — soi tiếp

- `adb logcat | grep -iE "emulator|root|integrity|detect"` (nhiều app in lý do).
- **Frida** (`frida-trace`) hook các hàm detect phổ biến: `Build.getFingerprint`, `File.exists`, `Runtime.exec("su")`, `GLES20.glGetString`, `SensorManager.getDefaultSensor`… (chỉ dùng khi bạn test app của mình).
- Đối chiếu danh sách ở mục 1 xem còn dấu nào chưa dọn.

## 4) Kiểm tra lại sau khi sửa

```bash
adb shell "getprop | grep -iE 'qemu|goldfish|ranchu'"   # → rỗng (trừ init.svc.* nếu chưa kernel-patch)
adb shell "dumpsys SurfaceFlinger | grep -i GLES"        # → renderer không còn "Android Emulator"
adb shell "getprop ro.build.fingerprint"                 # → fingerprint thiết bị thật hợp lệ
```

## 5) Ghi chú thực tế

- Thứ tự làm hiệu quả nhất: **3.1 (props) → 3.4 (root/integrity) → 3.2 (file/GL) → 3.3 (kernel)**.
- Nhiều app VN/game chỉ check **vài prop cơ bản** → 3.1 là đủ; app ngân hàng/anti-cheat nặng thì cần tới 3.4 và có thể bó tay ở STRONG integrity.
- Props đặt **sau khi boot** bằng `setprop` không ăn với `ro.*` (read-only) — phải `-prop` lúc boot hoặc `resetprop` (Magisk).
- Anti-cheat (Tencent ACE, VNG, Garena…) còn phát hiện Frida/hooking/debugger → khi test app có anti-cheat, tránh mọi tool hooking trừ khi đã ẩn kỹ.
- Ý tưởng mở rộng cho emu-sync: thêm **editor props theo từng AVD** (lưu danh sách `-prop` vào profile của AVD và tự truyền khi bấm "Chạy") — nói nếu bạn muốn, tôi làm.
