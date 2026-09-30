#!/usr/bin/env python3
"""
HTTP Backend Server for CIDOO ABM066 Keyboard LCD Tool.
Provides REST API endpoints for device discovery, time sync, and frame uploads.
Serves the modern Web UI from the static/ directory.
Zero external dependencies (uses Python standard library).
"""

import sys
import os
import json
import base64
import threading
import mimetypes
import traceback
import webbrowser
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# Import the native IOKit driver
from cidoo_driver import CidooABM066, from_bcd

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')

# Device lock and upload state
dev_lock = threading.Lock()
upload_state = {
    "busy": False,
    "percent": 0,
    "message": "Idle",
    "error": None,
    "last_result": None
}


class CidooAPIHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        try:
            msg = format % args
        except Exception:
            msg = str(format) + " " + str(args)
        if '/api/progress' in msg:
            return
        sys.stdout.write(f"[{self.log_date_time_string()}] {msg}\n")
        sys.stdout.flush()

    def send_json(self, status: int, data: dict):
        body = json.dumps(data).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-Slot, X-Interval, X-Frame-Count')
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == '/api/status':
            self.handle_get_status()
        elif path == '/api/progress':
            self.handle_get_progress()
        elif path == '/' or path == '/index.html':
            self.serve_static_file('index.html')
        elif path.startswith('/static/'):
            subpath = path[len('/static/'):]
            self.serve_static_file(subpath)
        else:
            # Check if file exists directly in static
            clean_path = path.lstrip('/')
            potential_file = os.path.join(STATIC_DIR, clean_path)
            if os.path.isfile(potential_file):
                self.serve_static_file(clean_path)
            else:
                self.send_error(404, "Not Found")

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == '/api/sync-time':
            self.handle_sync_time()
        elif path == '/api/upload':
            self.handle_upload()
        else:
            self.send_error(404, "Endpoint Not Found")

    def handle_get_status(self):
        # If currently uploading, return busy status without reopening HID
        if upload_state["busy"]:
            self.send_json(200, {
                "connected": True,
                "busy": True,
                "message": upload_state["message"],
                "percent": upload_state["percent"]
            })
            return

        with dev_lock:
            dev = CidooABM066()
            try:
                if not dev.find_and_open():
                    self.send_json(200, {
                        "connected": False,
                        "device": None,
                        "error": "CIDOO ABM066 keyboard not detected. Please ensure USB connection."
                    })
                    return

                try:
                    cfg1 = dev.read_config(0)
                    slot1_active = (cfg1[33] == 1)
                    cfg_active = cfg1
                    time_str = "20{:02d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format(
                        from_bcd(cfg_active[41]), from_bcd(cfg_active[40]), from_bcd(cfg_active[39]),
                        from_bcd(cfg_active[37]), from_bcd(cfg_active[36]), from_bcd(cfg_active[35])
                    )
                    self.send_json(200, {
                        "connected": True,
                        "device": "CIDOO ABM066",
                        "slot": cfg_active[33],
                        "frames": cfg_active[34],
                        "interval": cfg_active[46],
                        "lcd_time": time_str
                    })
                except Exception as e:
                    self.send_json(200, {
                        "connected": True,
                        "device": "CIDOO ABM066",
                        "error": f"Failed reading config: {e}"
                    })
            finally:
                dev.close()

    def handle_get_progress(self):
        self.send_json(200, {
            "busy": upload_state["busy"],
            "percent": upload_state["percent"],
            "message": upload_state["message"],
            "error": upload_state["error"],
            "last_result": upload_state["last_result"]
        })

    def handle_sync_time(self):
        if upload_state["busy"]:
            self.send_json(409, {"success": False, "error": "Device is busy with upload."})
            return

        slot = 1
        content_len = int(self.headers.get('Content-Length', 0))
        if content_len > 0:
            try:
                body = self.rfile.read(content_len)
                data = json.loads(body.decode('utf-8'))
                slot = int(data.get('slot', 1))
            except Exception:
                pass

        with dev_lock:
            dev = CidooABM066()
            try:
                if not dev.find_and_open():
                    self.send_json(503, {"success": False, "error": "Device not connected"})
                    return
                now = dev.sync_time(slot - 1)
                self.send_json(200, {
                    "success": True,
                    "synced_time": now.strftime("%Y-%m-%d %H:%M:%S")
                })
            except Exception as e:
                self.send_json(500, {"success": False, "error": str(e)})
            finally:
                dev.close()

    def handle_upload(self):
        if upload_state["busy"]:
            self.send_json(409, {"success": False, "error": "Another upload is already in progress."})
            return

        content_type = self.headers.get('Content-Type', '')
        content_len = int(self.headers.get('Content-Length', 0))

        if content_len <= 0:
            self.send_json(400, {"success": False, "error": "No content received"})
            return

        # Parse request: either application/octet-stream or application/json
        slot = int(self.headers.get('X-Slot', 1))
        interval_ms = int(self.headers.get('X-Interval', 40))
        frames = []

        if 'application/octet-stream' in content_type:
            raw_bytes = self.rfile.read(content_len)
            frame_size = CidooABM066.RAW_FRAME_SIZE  # 30,720 (96x160 RGB565)
            if len(raw_bytes) % frame_size != 0:
                self.send_json(400, {
                    "success": False,
                    "error": f"Payload size ({len(raw_bytes)}) is not a multiple of frame size ({frame_size})"
                })
                return

            frame_count = len(raw_bytes) // frame_size
            for i in range(frame_count):
                frames.append(raw_bytes[i * frame_size : (i + 1) * frame_size])
        else:
            # Assume JSON
            raw_body = self.rfile.read(content_len)
            try:
                data = json.loads(raw_body.decode('utf-8'))
                slot = int(data.get('slot', 1))
                interval_ms = int(data.get('interval', 40))
                b64_frames = data.get('frames', [])
                if not b64_frames:
                    self.send_json(400, {"success": False, "error": "No frames specified in JSON"})
                    return
                for b64 in b64_frames:
                    f = base64.b64decode(b64)
                    if len(f) != CidooABM066.RAW_FRAME_SIZE:
                        self.send_json(400, {
                            "success": False,
                            "error": f"Frame has invalid size: {len(f)} (expected {CidooABM066.RAW_FRAME_SIZE})"
                        })
                        return
                    frames.append(f)
            except Exception as e:
                self.send_json(400, {"success": False, "error": f"Invalid JSON payload: {e}"})
                return

        # Start upload in background thread so the client can poll progress
        def _bg_upload(frames_to_send, target_slot, target_interval):
            upload_state["busy"] = True
            upload_state["percent"] = 0
            upload_state["message"] = "Opening device..."
            upload_state["error"] = None
            upload_state["last_result"] = None

            def _on_progress(sent, total, msg):
                if total > 0:
                    pct = int((sent * 100) / total)
                    upload_state["percent"] = min(100, max(0, pct))
                upload_state["message"] = msg

            with dev_lock:
                dev = CidooABM066()
                try:
                    if not dev.find_and_open():
                        raise RuntimeError("CIDOO ABM066 keyboard not detected.")
                    dev.upload_frames(
                        frames_to_send,
                        slot=target_slot,
                        interval_ms=target_interval,
                        progress_cb=_on_progress
                    )
                    upload_state["percent"] = 100
                    upload_state["message"] = "Upload completed successfully!"
                    upload_state["last_result"] = {
                        "success": True,
                        "slot": target_slot,
                        "frames": len(frames_to_send),
                        "interval": target_interval
                    }
                except Exception as e:
                    traceback.print_exc()
                    upload_state["error"] = str(e)
                    upload_state["message"] = f"Error: {e}"
                finally:
                    dev.close()
                    upload_state["busy"] = False

        thread = threading.Thread(target=_bg_upload, args=(frames, slot, interval_ms), daemon=True)
        thread.start()

        self.send_json(202, {
            "success": True,
            "status": "started",
            "frame_count": len(frames),
            "slot": slot,
            "interval": interval_ms
        })

    def serve_static_file(self, filename: str):
        filepath = os.path.normpath(os.path.join(STATIC_DIR, filename))
        if not filepath.startswith(STATIC_DIR) or not os.path.isfile(filepath):
            self.send_error(404, f"File {filename} not found")
            return

        mime_type, _ = mimetypes.guess_type(filepath)
        if mime_type is None:
            mime_type = 'application/octet-stream'

        try:
            with open(filepath, 'rb') as f:
                content = f.read()

            self.send_response(200)
            self.send_header('Content-Type', mime_type)
            self.send_header('Content-Length', str(len(content)))
            if filepath.endswith('.html'):
                self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            self.send_error(500, f"Error reading file: {e}")


def run_server(port: int = 8066, host: str = '127.0.0.1', auto_open: bool = True):
    # Enable address reuse to avoid [Errno 48]
    ThreadingHTTPServer.allow_reuse_address = True

    httpd = None
    active_port = port
    for p in range(port, port + 20):
        try:
            httpd = ThreadingHTTPServer((host, p), CidooAPIHandler)
            active_port = p
            break
        except OSError as e:
            if e.errno == 48:  # Address already in use
                continue
            raise

    if not httpd:
        print(f"Error: Could not bind to any port between {port} and {port + 20}")
        sys.exit(1)

    url = f"http://{host}:{active_port}/"
    print("==================================================")
    print(" CIDOO ABM066 LCD Web Server running at:")
    print(f" {url}")
    print(" (Press Ctrl+C to stop the server)")
    print("==================================================")

    if auto_open:
        # Launch browser 0.3s after the server is actively listening
        threading.Timer(0.3, lambda: webbrowser.open(url)).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
    finally:
        httpd.server_close()


if __name__ == '__main__':
    port = 8066
    auto_open = '--no-open' not in sys.argv
    for arg in sys.argv[1:]:
        if arg.isdigit():
            port = int(arg)
    run_server(port=port, auto_open=auto_open)
