#!/usr/bin/env bash
# Quản lý 2 AVD cho dev emu-sync (macOS / Apple Silicon).
#
# Usage:
#   dev_avd.sh create            # cài image (nếu thiếu) + tạo emu1, emu2
#   dev_avd.sh start             # chạy 2 AVD có cửa sổ (để click chuột vào)
#   dev_avd.sh start --headless  # chạy không cửa sổ (tiết kiệm CPU)
#   dev_avd.sh stop              # tắt 2 AVD
set -euo pipefail

SDK="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-$HOME/Library/Android/sdk}}"
IMAGE="system-images;android-35;google_apis;arm64-v8a"
EMU="$SDK/emulator/emulator"
ADB="$(command -v adb || echo "$SDK/platform-tools/adb")"
SDKMGR_LOCAL="$SDK/cmdline-tools/latest/bin/sdkmanager"
AVDMGR_LOCAL="$SDK/cmdline-tools/latest/bin/avdmanager"
# Ưu tiên tools trong chính SDK root (avdmanager cần đúng root để thấy system-images).
SDKMANAGER="${SDKMANAGER:-$([ -x "$SDKMGR_LOCAL" ] && echo "$SDKMGR_LOCAL" || command -v sdkmanager)}"
AVDMANAGER="${AVDMANAGER:-$([ -x "$AVDMGR_LOCAL" ] && echo "$AVDMGR_LOCAL" || command -v avdmanager)}"
export ANDROID_HOME="$SDK"

# Cài package SDK: cmdline-tools mới (23.0) có CLI `android sdk install` — **tự chấp nhận license**.
# `sdkmanager --licenses` đã bị bỏ (in "--licenses option is no longer needed" và KHÔNG tạo file
# license) nên nếu dùng nó, package sẽ bị skip: "license is not accepted".
ANDROIDCLI="${ANDROIDCLI:-$([ -x "$SDK/cmdline-tools/latest/bin/android" ] && echo "$SDK/cmdline-tools/latest/bin/android" || command -v android || true)}"

install_packages() {
  if [ -n "$ANDROIDCLI" ]; then
    "$ANDROIDCLI" sdk --sdk="$SDK" install "$@"
  else
    # cmdline-tools cũ: chấp nhận license bằng pipe "y" rồi cài
    yes | "$SDKMANAGER" --sdk_root="$SDK" --licenses >/dev/null 2>&1 || true
    "$SDKMANAGER" --sdk_root="$SDK" "$@"
  fi
}

create() {
  # Cài cmdline-tools vào CHÍNH SDK root để avdmanager tìm đúng system-images.
  install_packages "platform-tools" "emulator" "cmdline-tools;latest" "$IMAGE"

  # Kiểm tra cài thật sự thành công (tránh lỗi dây chuyền khó hiểu ở bước sau)
  if [ ! -x "$EMU" ]; then
    echo "[LỖI] Chưa cài được emulator ($EMU). Xem thông báo phía trên." >&2
    return 1
  fi
  local image_dir="$SDK/${IMAGE//;//}"
  if [ ! -d "$image_dir" ]; then
    echo "[LỖI] Chưa cài được system image $IMAGE ($image_dir)." >&2
    return 1
  fi

  # avdmanager trong SDK root giờ đã có → dùng nó (avdmanager của brew tìm sai SDK root)
  if [ -x "$AVDMGR_LOCAL" ]; then AVDMANAGER="$AVDMGR_LOCAL"; fi
  for name in emu1 emu2; do
    if "$EMU" -list-avds 2>/dev/null | grep -qx "$name"; then
      echo "AVD $name đã tồn tại"
    else
      echo no | "$AVDMANAGER" create avd -n "$name" -k "$IMAGE" -d pixel_6 --force
      # Bật bàn phím phần cứng: cho phép gõ từ bàn phím host + sync bàn phím
      local cfg="$HOME/.android/avd/$name.avd/config.ini"
      if [ ! -f "$cfg" ]; then
        echo "[LỖI] Tạo AVD $name thất bại (không thấy $cfg)." >&2
        return 1
      fi
      if grep -q '^hw.keyboard=' "$cfg"; then
        sed -i.bak 's/^hw.keyboard=.*/hw.keyboard=yes/' "$cfg"
      else
        printf '\nhw.keyboard=yes\n' >>"$cfg"
      fi
      rm -f "$cfg.bak"
      echo "Đã tạo AVD $name (hw.keyboard=yes)"
    fi
  done
}

boot_wait() {
  for serial in emulator-5554 emulator-5556; do
    local avd="emu1"
    [[ "$serial" == *5556 ]] && avd="emu2"
    local log="/tmp/${avd}.log"
    printf "chờ %s boot" "$serial"
    local waited=0
    until [[ "$("$ADB" -s "$serial" shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" == "1" ]]; do
      # fail nhanh nếu process emulator đã chết — nhưng bỏ qua 12s đầu (qemu cần thời gian spawn)
      if (( waited >= 12 )) && ! pgrep -f "qemu-system.*-avd ${avd}( |$)" >/dev/null; then
        echo " — EMULATOR ĐÃ THOÁT. 12 dòng cuối $log:"
        tail -12 "$log"
        return 1
      fi
      printf "."
      sleep 2
      waited=$((waited + 2))
      if (( waited >= 300 )); then
        echo " TIMEOUT — xem log: $log"
        return 1
      fi
    done
    echo " ready"
  done
}

start() {
  local extra=(-no-audio -no-boot-anim)
  case "${1:-}" in
    --headless) extra+=(-no-window) ;;
    --cold) extra+=(-no-snapshot-load -no-snapshot-save) ;;
    --cold-headless) extra+=(-no-window -no-snapshot-load -no-snapshot-save) ;;
  esac
  "$EMU" -avd emu1 -port 5554 "${extra[@]}" > /tmp/emu1.log 2>&1 &
  "$EMU" -avd emu2 -port 5556 "${extra[@]}" > /tmp/emu2.log 2>&1 &
  boot_wait
}

stop() {
  for serial in emulator-5554 emulator-5556; do
    "$ADB" -s "$serial" emu kill 2>/dev/null || true
  done
  # đợi process thoát HẲN (emulator có thể mất ~15s để lưu snapshot khi thoát;
  # nếu start ngay sẽ bị lỗi "multiple emulators with the same AVD")
  for _ in $(seq 1 60); do
    pgrep -f "qemu-system.*-avd emu" >/dev/null || break
    sleep 1
  done
  if pgrep -f "qemu-system.*-avd emu" >/dev/null; then
    echo "CẢNH BÁO: emulator vẫn chưa thoát hẳn — chờ thêm hoặc kill thủ công."
  fi
}

case "${1:-}" in
  create) create ;;
  start) start "${2:-}" ;;
  stop) stop ;;
  *)
    echo "Usage: $0 {create|start [--headless|--cold|--cold-headless]|stop}"
    echo "  --cold: bỏ qua snapshot (cold boot) — dùng khi snapshot bị lỗi/ANR"
    exit 2
    ;;
esac
