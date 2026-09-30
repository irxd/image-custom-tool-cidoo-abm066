# CIDOO ABM066 LCD Custom Tool for macOS

Native macOS replacement for the Windows-only `Image Custom Tool 0703.exe`. This tool allows you to customize the 240×135 color LCD screen on your **CIDOO ABM066** mechanical keyboard directly from macOS, without needing a Windows machine or virtual machine.

---

## ✨ Features

- **Double-Click Web GUI**: Clean, dark-mode interface with a live 240×135 preview of your LCD screen.
- **Zero External Dependencies**: Built with native macOS `IOKit` / `CoreFoundation` via Python standard library `ctypes`.
- **Full GIF & Image Support**: Supports animated GIFs, PNG, JPG, BMP, and WebP.
- **Client-Side Frame Processing**: Fast frame extraction, resizing, and 16-bit Big-Endian RGB565 encoding.
- **Interactive Animation Controls**:
  - Play / Pause / Step through frames.
  - Frame timeline scrubber.
  - Animation speed slider (25ms to 200ms) with presets (Fast, Smooth, Normal, Slow).
  - Frame limit selector (up to 80 frames recommended for flash memory).
- **Aspect Ratio Fit Modes**:
  - **Cover**: Fills the entire 240×135 screen, cropping excess evenly.
  - **Contain**: Fits the whole image inside 240×135 with black letterbox bars.
  - **Stretch**: Stretches directly to 240×135 pixels.
- **Clock Synchronization**: One-click sync of your keyboard's LCD clock to current Mac local time.
- **Dual Slot Support**: Upload to Slot 1 (Custom 1) or Slot 2 (Custom 2).
- **Command Line Interface (CLI)**: For terminal users, automation, or shell scripting.

---

## 🚀 Quick Start (Web GUI)

### Option 1: Double-Click Launcher (Easiest)
In macOS Finder, simply double-click:
```
CIDOO ABM066 Tool.command
```
This will start the local server and automatically open the tool in your default web browser (`http://127.0.0.1:5000`).

### Option 2: Run via Terminal
```bash
python3 server.py
```
Then open `http://127.0.0.1:5000` in Safari, Chrome, or any browser.

---

## 💻 Command Line Interface (CLI)

You can also control the LCD directly from the terminal using `cli.py`:

### 1. Check Keyboard Connection & LCD Status
```bash
python3 cli.py status
```
Output:
```text
Keyboard: CIDOO ABM066 LCD Screen
Status:   Connected (USB HID)
Active:   Slot 2
Frames:   74
Interval: 25 ms
LCD Time: 2026-09-30 14:26:33
```

### 2. Synchronize Clock to Mac Local Time
```bash
python3 cli.py sync-time
```
Optional: specify slot:
```bash
python3 cli.py sync-time --slot 2
```

### 3. Upload an Image or Animated GIF
```bash
# Upload a GIF or image with auto-detected speed and cover fit:
python3 cli.py upload /path/to/animation.gif

# Specify custom delay (e.g. 40ms) and slot 1:
python3 cli.py upload /path/to/animation.gif --slot 1 --interval 40

# Choose fit mode ('cover', 'contain', or 'stretch'):
python3 cli.py upload /path/to/picture.png --fit contain
```

---

## 🛠️ Hardware Protocol & Technical Details

For developers or curious users, here is how the CIDOO ABM066 LCD communicates over USB HID:

| Parameter | Specification |
| :--- | :--- |
| **Vendor ID (VID)** | `0x320F` (Telink) or `0x0C45` (Sonix) |
| **Product ID (PID)** | `0x5055` (CIDOO ABM066) or `0x1007` |
| **Usage Page** | `0xFF1C` (65308) |
| **Usage** | `0x92` (146) |
| **Report ID** | `0x04` |
| **Report Length** | 64 bytes (Output) / 8 bytes (Input) |
| **LCD Resolution** | **240 × 135 pixels** |
| **Pixel Format** | **16-bit RGB565 Big-Endian** (`((r>>3)<<11) \| ((g>>2)<<5) \| (b>>3)`) |
| **Raw Frame Size** | `240 * 135 * 2` = 64,800 bytes (`0xFD20`) |
| **Flash Block Alignment** | Padded with zeros to 65,536 bytes (64 KB) per frame |

### Communication Flow:
1. **Command `0x23`**: Start custom screen transfer / flash erase prep.
2. **Command `0x01`**: Initialize / reset flash pointer.
3. **Command `0x21`**: Stream raw frame data in 56-byte chunks (`0x38`).
   - *Crucial*: A 500ms delay (`time.sleep(0.5)`) is enforced immediately after chunk 0 to give the keyboard MCU flash memory time to prepare.
4. **Command `0x02`**: Finalize / commit flash write.
5. **Command `0x06`**: Update the 48-byte configuration header (active slot, total frames, frame interval delay in ms, and BCD-encoded date & time).

---

## 📁 Repository Structure

```text
├── CIDOO ABM066 Tool.command  # Double-clickable macOS launcher
├── cidoo_driver.py            # Native macOS IOKit USB HID driver
├── server.py                  # Lightweight local HTTP API & static server
├── cli.py                     # Command-line interface
├── static/
│   ├── index.html             # Web UI layout
│   ├── style.css              # Modern dark-mode styling
│   ├── app.js                 # Frontend application & GIF processor
│   └── omggif.js              # Pure JavaScript GIF decoder
└── README.md                  # Documentation
```
