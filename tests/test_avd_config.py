"""Test module quản lý AVD: đọc/ghi config.ini (profile) + dò SDK."""

from pathlib import Path

from emu_sync import avd


def test_read_write_config(tmp_path):
    cfg: Path = tmp_path / "config.ini"
    cfg.write_text("hw.lcd.width=1080\nhw.keyboard=no\n# ghi chú\nhw.ramSize=2048\n", encoding="utf-8")

    data = avd.read_config(cfg)
    assert data["hw.keyboard"] == "no"
    assert data["hw.ramSize"] == "2048"

    avd.write_config(cfg, {"hw.keyboard": "yes", "hw.lcd.height": "2400"})
    updated = avd.read_config(cfg)
    assert updated["hw.keyboard"] == "yes"
    assert updated["hw.lcd.height"] == "2400"
    assert updated["hw.lcd.width"] == "1080"  # giá trị cũ giữ nguyên
    assert "# ghi chú" in cfg.read_text(encoding="utf-8")


def test_sdk_root_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("ANDROID_HOME", str(tmp_path))
    assert avd.sdk_root() == tmp_path


def test_installed_images(tmp_path, monkeypatch):
    image_dir = tmp_path / "system-images" / "android-35" / "google_apis" / "arm64-v8a"
    image_dir.mkdir(parents=True)
    monkeypatch.setenv("ANDROID_HOME", str(tmp_path))
    assert avd.installed_images() == ["system-images;android-35;google_apis;arm64-v8a"]


def test_list_avds_reads_config(tmp_path, monkeypatch):
    avd_home = tmp_path / "avd"
    folder = avd_home / "test1.avd"
    folder.mkdir(parents=True)
    (folder / "config.ini").write_text(
        "hw.lcd.width=720\nhw.lcd.height=1600\nhw.lcd.density=320\nhw.ramSize=2048\nhw.cpu.ncore=2\nhw.keyboard=yes\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ANDROID_AVD_HOME", str(avd_home))
    monkeypatch.setenv("PATH", "")  # không có emulator binary → fallback quét thư mục

    infos = avd.list_avds()
    assert [i.name for i in infos] == ["test1"]
    info = infos[0]
    assert (info.width, info.height) == (720, 1600)
    assert info.dpi == 320
    assert info.ram_mb == 2048
    assert info.cores == 2
    assert info.keyboard is True
    assert info.running is False


def test_set_config_with_dpi(tmp_path, monkeypatch):
    """Đổi độ phân giải qua profile (config.ini) — ghi cả hw.lcd.density."""
    avd_home = tmp_path / "avd"
    folder = avd_home / "t.avd"
    folder.mkdir(parents=True)
    (folder / "config.ini").write_text("hw.lcd.width=1080\nhw.lcd.height=2400\n", encoding="utf-8")
    monkeypatch.setenv("ANDROID_AVD_HOME", str(avd_home))
    monkeypatch.setenv("ANDROID_HOME", str(tmp_path / "sdk"))  # SDK rỗng → không có emulator
    monkeypatch.setenv("PATH", "")

    info = avd.set_config("t", width=720, height=1600, dpi=320)
    assert (info.width, info.height) == (720, 1600)
    cfg = avd.read_config(folder / "config.ini")
    assert cfg["hw.lcd.width"] == "720"
    assert cfg["hw.lcd.height"] == "1600"
    assert cfg["hw.lcd.density"] == "320"
