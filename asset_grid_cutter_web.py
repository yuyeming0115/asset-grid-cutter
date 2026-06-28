#!/usr/bin/env python3
"""Local browser UI for Asset Grid Cutter."""

from __future__ import annotations

import cgi
import html
import json
import socket
import subprocess
import time
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from PIL import Image, ImageDraw

from asset_grid_cutter import (
    CutSettings,
    choose_grid,
    cut_image,
    detect_grid,
    fixed_grid,
    safe_stem,
)


ROOT = Path(__file__).resolve().parent
WEB_WORK = ROOT / "web-work"
UPLOAD_DIR = WEB_WORK / "uploads"
OUTPUT_DIR = WEB_WORK / "outputs"
FILE_REGISTRY: dict[str, Path] = {}


def default_settings(rows: int | None = None, cols: int | None = None) -> CutSettings:
    return CutSettings(
        rows=rows,
        cols=cols,
        detect_grid=True,
        trim=True,
        padding=8,
        trim_tolerance=14,
        transparent_bg=False,
        transparent_tolerance=8,
        transparent_softness=24,
        preview=True,
        line_fraction=0.55,
    )


def register_file(path: Path) -> str:
    token = uuid.uuid4().hex
    FILE_REGISTRY[token] = path.resolve()
    return token


def file_url(path: Path) -> str:
    return f"/file/{register_file(path)}"


def save_upload(form: cgi.FieldStorage) -> Path:
    field = form["image"]
    filename = Path(field.filename or "asset-sheet.png")
    stem = safe_stem(filename)
    suffix = filename.suffix if filename.suffix else ".png"
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    out = UPLOAD_DIR / f"{stem}-{int(time.time())}-{uuid.uuid4().hex[:8]}{suffix}"
    out.write_bytes(field.file.read())
    return out


def parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def parse_int(value: str | None, default: int | None = None) -> int | None:
    if value is None or value == "":
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def settings_from_form(form: cgi.FieldStorage) -> CutSettings:
    rows = parse_int(form.getfirst("rows"), 6)
    cols = parse_int(form.getfirst("cols"), 12)
    return CutSettings(
        rows=rows,
        cols=cols,
        detect_grid=parse_bool(form.getfirst("detect_grid"), True),
        trim=parse_bool(form.getfirst("trim"), True),
        padding=parse_int(form.getfirst("padding"), 8) or 8,
        trim_tolerance=parse_int(form.getfirst("trim_tolerance"), 14) or 14,
        transparent_bg=parse_bool(form.getfirst("transparent_bg"), False),
        transparent_tolerance=parse_int(form.getfirst("transparent_tolerance"), 8) or 8,
        transparent_softness=parse_int(form.getfirst("transparent_softness"), 24) or 24,
        preview=True,
        line_fraction=0.55,
    )


def analyze_image(image_path: Path, rows: int | None, cols: int | None) -> dict:
    image = Image.open(image_path)

    grid = detect_grid(image, None, None, 0.55)
    source = "detected"
    if grid is None:
        rows = rows or 6
        cols = cols or 12
        grid = fixed_grid(image, rows, cols)
        source = "fixed fallback"

    preview_path = make_grid_preview(image_path, grid.boxes, grid.rows, grid.cols)
    return {
        "rows": grid.rows,
        "cols": grid.cols,
        "count": len(grid.boxes),
        "source": source,
        "image_size": image.size,
        "preview_url": file_url(preview_path),
    }


def make_grid_preview(
    image_path: Path,
    boxes: list[tuple[int, int, int, int]],
    rows: int,
    cols: int,
) -> Path:
    image = Image.open(image_path).convert("RGBA")
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    line = max(2, round(min(image.size) / 450))
    for box in boxes:
        draw.rectangle(box, outline=(37, 99, 235, 210), width=line)
    composed = Image.alpha_composite(image, overlay).convert("RGB")
    composed.thumbnail((1400, 900), Image.Resampling.LANCZOS)

    preview_dir = WEB_WORK / "analysis"
    preview_dir.mkdir(parents=True, exist_ok=True)
    out = preview_dir / f"{safe_stem(image_path)}-{rows}x{cols}-analysis.jpg"
    composed.save(out, quality=92)
    return out


def html_page() -> bytes:
    return PAGE.encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return

    def send_json(self, data: dict, status: int = 200) -> None:
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            body = html_page()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path.startswith("/file/"):
            token = parsed.path.rsplit("/", 1)[-1]
            path = FILE_REGISTRY.get(token)
            if not path or not path.exists():
                self.send_error(404)
                return
            content_type = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
            data = path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        self.send_error(404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in {"/api/analyze", "/api/cut"}:
            form = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={
                    "REQUEST_METHOD": "POST",
                    "CONTENT_TYPE": self.headers.get("Content-Type", ""),
                    "CONTENT_LENGTH": self.headers.get("Content-Length", "0"),
                },
            )
            try:
                image_path = save_upload(form)
                rows = parse_int(form.getfirst("rows"), 6)
                cols = parse_int(form.getfirst("cols"), 12)
                analysis = analyze_image(image_path, rows, cols)
                if parsed.path == "/api/analyze":
                    self.send_json({"ok": True, **analysis})
                    return

                settings = settings_from_form(form)
                if settings.detect_grid:
                    # Let the cutter use the explicit values for validation; if
                    # that fails, use the analysis result as the best estimate.
                    settings.rows = analysis["rows"]
                    settings.cols = analysis["cols"]
                out_dir = OUTPUT_DIR / f"{safe_stem(image_path)}-{int(time.time())}"
                manifest = cut_image(image_path, out_dir, settings)
                preview = out_dir / str(manifest.get("preview"))
                self.send_json(
                    {
                        "ok": True,
                        "count": manifest["count"],
                        "rows": manifest["grid"]["rows"],
                        "cols": manifest["grid"]["cols"],
                        "source": manifest["grid"]["source"],
                        "output_dir": str(out_dir),
                        "preview_url": file_url(preview) if preview.exists() else None,
                    }
                )
            except Exception as exc:
                self.send_json({"ok": False, "error": str(exc)}, status=400)
            return

        if parsed.path == "/api/open":
            length = int(self.headers.get("Content-Length", "0"))
            data = parse_qs(self.rfile.read(length).decode("utf-8"))
            folder = data.get("folder", [""])[0]
            if folder:
                subprocess.run(["open", folder], check=False)
            self.send_json({"ok": True})
            return

        self.send_error(404)


def find_free_port(start: int = 8765) -> int:
    for port in range(start, start + 100):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError("Could not find a free local port.")


def main() -> int:
    WEB_WORK.mkdir(parents=True, exist_ok=True)
    port = find_free_port()
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"Asset Grid Cutter Web UI: {url}")
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


PAGE = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Asset Grid Cutter</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f4f6f8;
      --panel: #ffffff;
      --text: #18212f;
      --muted: #667085;
      --border: #d0d5dd;
      --accent: #2563eb;
      --accent2: #10b981;
      --danger: #b42318;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--text);
    }
    main {
      max-width: 1180px;
      margin: 0 auto;
      padding: 24px;
    }
    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 18px;
    }
    h1 { margin: 0; font-size: 26px; }
    .status { color: var(--muted); font-size: 14px; }
    .layout {
      display: grid;
      grid-template-columns: 360px 1fr;
      gap: 18px;
      align-items: start;
    }
    .panel {
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 16px;
    }
    .drop {
      border: 2px dashed #98a2b3;
      border-radius: 8px;
      min-height: 112px;
      display: grid;
      place-items: center;
      text-align: center;
      padding: 14px;
      background: #f9fafb;
      cursor: pointer;
    }
    .drop.dragover {
      border-color: var(--accent);
      background: #eff6ff;
    }
    .drop strong { display: block; margin-bottom: 6px; }
    .drop small { color: var(--muted); }
    input[type="file"] { display: none; }
    label { display: block; font-size: 13px; font-weight: 650; margin-bottom: 6px; }
    input[type="number"] {
      width: 100%;
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 8px;
      font-size: 14px;
    }
    .grid2 {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
      margin-top: 14px;
    }
    .checks {
      display: grid;
      gap: 10px;
      margin-top: 14px;
    }
    .checks label {
      display: flex;
      align-items: center;
      gap: 8px;
      margin: 0;
      font-weight: 600;
    }
    button {
      border: 0;
      border-radius: 6px;
      padding: 10px 12px;
      font-weight: 700;
      color: white;
      background: var(--accent);
      cursor: pointer;
    }
    button.secondary { background: #475467; }
    button.green { background: var(--accent2); }
    button.language { background: #344054; min-width: 116px; }
    button:disabled { opacity: .45; cursor: not-allowed; }
    .actions {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
      margin-top: 14px;
    }
    .summary {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      background: #f9fafb;
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 10px 12px;
      margin-bottom: 14px;
    }
    .summary-text {
      font-weight: 750;
      overflow-wrap: anywhere;
    }
    .summary-sub {
      color: var(--muted);
      font-size: 12px;
    }
    .preview {
      min-height: 560px;
      display: grid;
      grid-template-rows: auto 1fr;
      gap: 12px;
    }
    .preview img {
      width: 100%;
      max-height: 640px;
      object-fit: contain;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: #fff;
    }
    .empty {
      border: 1px dashed var(--border);
      border-radius: 8px;
      display: grid;
      place-items: center;
      min-height: 420px;
      color: var(--muted);
      background: #f9fafb;
      text-align: center;
      padding: 18px;
    }
    .log {
      white-space: pre-wrap;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 12px;
      background: #101828;
      color: #f2f4f7;
      border-radius: 8px;
      padding: 12px;
      min-height: 96px;
      margin-top: 14px;
      overflow: auto;
    }
    .path {
      overflow-wrap: anywhere;
      color: var(--muted);
      font-size: 12px;
      margin-top: 10px;
    }
    @media (max-width: 880px) {
      .layout { grid-template-columns: 1fr; }
      .summary { align-items: flex-start; flex-direction: column; }
    }
  </style>
</head>
<body>
<main>
  <header>
    <div>
      <h1>Asset Grid Cutter</h1>
      <div class="status" id="status" data-i18n="status.ready">Drop an image to analyze its grid.</div>
    </div>
    <button id="langBtn" class="language">中文</button>
  </header>
  <div class="layout">
    <section class="panel">
      <div class="drop" id="drop">
        <div>
          <strong data-i18n="drop.title">Drag an image here</strong>
          <small data-i18n="drop.subtitle">or click to choose a PNG/JPG/WebP asset sheet</small>
        </div>
      </div>
      <input id="file" type="file" accept="image/*" />
      <div class="grid2">
        <div>
          <label for="rows" data-i18n="form.rows">Grid rows</label>
          <input id="rows" type="number" min="1" value="6" />
        </div>
        <div>
          <label for="cols" data-i18n="form.cols">Grid columns</label>
          <input id="cols" type="number" min="1" value="12" />
        </div>
        <div>
          <label for="padding" data-i18n="form.padding">Padding</label>
          <input id="padding" type="number" min="0" value="8" />
        </div>
        <div>
          <label for="trimTolerance" data-i18n="form.trimTolerance">Trim tolerance</label>
          <input id="trimTolerance" type="number" min="0" max="255" value="14" />
        </div>
      </div>
      <div class="checks">
        <label><input id="detectGrid" type="checkbox" checked /> <span data-i18n="form.detect">Detect grid lines</span></label>
        <label><input id="trim" type="checkbox" checked /> <span data-i18n="form.trim">Trim blank background</span></label>
        <label><input id="transparent" type="checkbox" /> <span data-i18n="form.transparent">Transparent background</span></label>
      </div>
      <div class="actions">
        <button id="analyzeBtn" class="secondary" disabled data-i18n="button.analyze">Analyze</button>
        <button id="cutBtn" class="green" disabled data-i18n="button.cut">Cut Assets</button>
        <button id="openBtn" class="secondary" disabled data-i18n="button.open">Open Output</button>
      </div>
      <div class="path" id="filePath"></div>
      <div class="log" id="log">Ready.</div>
    </section>
    <section class="panel preview">
      <div class="summary">
        <div>
          <div class="summary-text" id="summaryText" data-i18n="summary.empty">等待图片分析</div>
          <div class="summary-sub" id="summarySub" data-i18n="summary.hint">拖入图片后这里会显示网格结果</div>
        </div>
      </div>
      <div id="previewWrap" class="empty" data-i18n="preview.empty">Analysis preview and output preview will appear here.</div>
    </section>
  </div>
</main>
<script>
let currentFile = null;
let outputFolder = "";
let currentLang = localStorage.getItem("assetGridCutterLang") || "zh";
let latestSummary = null;
const $ = (id) => document.getElementById(id);
const drop = $("drop");
const fileInput = $("file");
const log = (message) => { $("log").textContent = message; };
const status = (message) => { $("status").textContent = message; $("status").removeAttribute("data-i18n"); };

const I18N = {
  en: {
    "status.ready": "Drop an image to analyze its grid.",
    "drop.title": "Drag an image here",
    "drop.subtitle": "or click to choose a PNG/JPG/WebP asset sheet",
    "form.rows": "Grid rows",
    "form.cols": "Grid columns",
    "form.padding": "Padding",
    "form.trimTolerance": "Trim tolerance",
    "form.detect": "Detect grid lines",
    "form.trim": "Trim blank background",
    "form.transparent": "Transparent background",
    "button.analyze": "Analyze",
    "button.cut": "Cut Assets",
    "button.open": "Open Output",
    "summary.empty": "Waiting for image analysis",
    "summary.hint": "Grid results will appear here after dropping an image",
    "summary.result": "{count} cells · {cols} columns x {rows} rows · {source}",
    "summary.output": "Output complete · {count} PNGs · {cols} columns x {rows} rows",
    "preview.empty": "Analysis preview and output preview will appear here.",
    "log.ready": "Ready.",
    "log.upload": "Uploading and analyzing {name} ...",
    "log.analysisOk": "Analysis OK: {count} cells ({cols}x{rows}, {source})",
    "log.cut": "Cutting {name} ...",
    "log.outputOk": "Output OK: {count} PNGs ({cols}x{rows}, {source})\n{folder}",
    "status.analyzing": "Analyzing grid...",
    "status.analyzeFailed": "Analyze failed",
    "status.detected": "Detected {cols} x {rows} grid",
    "status.loaded": "Image loaded. Analyzing automatically...",
    "status.cutting": "Cutting assets...",
    "status.cutFailed": "Cut failed",
    "status.output": "Output complete: {count} PNGs",
    "language": "中文"
  },
  zh: {
    "status.ready": "拖入图片后会自动分析网格。",
    "drop.title": "把图片拖到这里",
    "drop.subtitle": "或点击选择 PNG/JPG/WebP 素材表",
    "form.rows": "网格行数",
    "form.cols": "网格列数",
    "form.padding": "留白边距",
    "form.trimTolerance": "裁边容差",
    "form.detect": "检测网格线",
    "form.trim": "裁掉空白背景",
    "form.transparent": "透明背景",
    "button.analyze": "重新分析",
    "button.cut": "切割素材",
    "button.open": "打开输出",
    "summary.empty": "等待图片分析",
    "summary.hint": "拖入图片后这里会显示网格结果",
    "summary.result": "{count} 个格子 · {cols} 列 x {rows} 行 · {source}",
    "summary.output": "输出完成 · {count} 张 PNG · {cols} 列 x {rows} 行",
    "preview.empty": "分析预览和输出预览会显示在这里。",
    "log.ready": "就绪。",
    "log.upload": "正在上传并分析 {name} ...",
    "log.analysisOk": "分析完成：{count} 个格子（{cols}x{rows}，{source}）",
    "log.cut": "正在切割 {name} ...",
    "log.outputOk": "输出完成：{count} 张 PNG（{cols}x{rows}，{source}）\n{folder}",
    "status.analyzing": "正在分析网格...",
    "status.analyzeFailed": "分析失败",
    "status.detected": "检测到 {cols} x {rows} 网格",
    "status.loaded": "图片已载入，正在自动分析...",
    "status.cutting": "正在切割素材...",
    "status.cutFailed": "切割失败",
    "status.output": "输出完成：{count} 张 PNG",
    "language": "English"
  }
};

function t(key, vars = {}) {
  let text = I18N[currentLang][key] || I18N.en[key] || key;
  for (const [name, value] of Object.entries(vars)) {
    text = text.replaceAll(`{${name}}`, value);
  }
  return text;
}

function applyLanguage() {
  document.documentElement.lang = currentLang === "zh" ? "zh-CN" : "en";
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    el.textContent = t(el.dataset.i18n);
  });
  $("langBtn").textContent = t("language");
  renderSummary();
  if ($("log").textContent === "Ready." || $("log").textContent === "就绪。") {
    log(t("log.ready"));
  }
}

function formData() {
  const data = new FormData();
  data.append("image", currentFile);
  data.append("rows", $("rows").value);
  data.append("cols", $("cols").value);
  data.append("padding", $("padding").value);
  data.append("trim_tolerance", $("trimTolerance").value);
  data.append("detect_grid", $("detectGrid").checked ? "1" : "0");
  data.append("trim", $("trim").checked ? "1" : "0");
  data.append("transparent_bg", $("transparent").checked ? "1" : "0");
  return data;
}

function showPreview(url, label) {
  $("previewWrap").className = "";
  $("previewWrap").innerHTML = `<img src="${url}?t=${Date.now()}" alt="${label}">`;
}

function updateMetrics(data) {
  latestSummary = { ...data, mode: data.mode || "analysis" };
  renderSummary();
  if (data.rows) $("rows").value = data.rows;
  if (data.cols) $("cols").value = data.cols;
}

function renderSummary() {
  if (!latestSummary) {
    $("summaryText").textContent = t("summary.empty");
    $("summarySub").textContent = t("summary.hint");
    return;
  }
  const key = latestSummary.mode === "output" ? "summary.output" : "summary.result";
  $("summaryText").textContent = t(key, latestSummary);
  $("summarySub").textContent = latestSummary.image_size
    ? `${latestSummary.image_size[0]} x ${latestSummary.image_size[1]}`
    : latestSummary.output_dir || "";
}

async function analyze() {
  if (!currentFile) return;
  status(t("status.analyzing"));
  log(t("log.upload", { name: currentFile.name }));
  $("analyzeBtn").disabled = true;
  $("cutBtn").disabled = true;
  const res = await fetch("/api/analyze", { method: "POST", body: formData() });
  const data = await res.json();
  $("analyzeBtn").disabled = false;
  if (!data.ok) {
    status(t("status.analyzeFailed"));
    log("ERROR " + data.error);
    return;
  }
  updateMetrics(data);
  showPreview(data.preview_url, "analysis preview");
  $("cutBtn").disabled = false;
  status(t("status.detected", data));
  log(t("log.analysisOk", data));
}

async function cut() {
  if (!currentFile) return;
  status(t("status.cutting"));
  log(t("log.cut", { name: currentFile.name }));
  $("cutBtn").disabled = true;
  const res = await fetch("/api/cut", { method: "POST", body: formData() });
  const data = await res.json();
  $("cutBtn").disabled = false;
  if (!data.ok) {
    status(t("status.cutFailed"));
    log("ERROR " + data.error);
    return;
  }
  outputFolder = data.output_dir;
  updateMetrics({ ...data, mode: "output" });
  if (data.preview_url) showPreview(data.preview_url, "output preview");
  $("openBtn").disabled = false;
  status(t("status.output", data));
  log(t("log.outputOk", { ...data, folder: data.output_dir }));
}

async function openOutput() {
  if (!outputFolder) return;
  const body = new URLSearchParams({ folder: outputFolder });
  await fetch("/api/open", { method: "POST", body });
}

function setFile(file) {
  currentFile = file;
  outputFolder = "";
  latestSummary = null;
  renderSummary();
  $("filePath").textContent = file.name + " (" + Math.round(file.size / 1024) + " KB)";
  $("analyzeBtn").disabled = false;
  $("cutBtn").disabled = true;
  $("openBtn").disabled = true;
  status(t("status.loaded"));
  analyze();
}

drop.addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", () => {
  if (fileInput.files.length) setFile(fileInput.files[0]);
});
["dragenter", "dragover"].forEach((eventName) => {
  drop.addEventListener(eventName, (event) => {
    event.preventDefault();
    drop.classList.add("dragover");
  });
});
["dragleave", "drop"].forEach((eventName) => {
  drop.addEventListener(eventName, (event) => {
    event.preventDefault();
    drop.classList.remove("dragover");
  });
});
drop.addEventListener("drop", (event) => {
  const file = event.dataTransfer.files[0];
  if (file) setFile(file);
});
$("analyzeBtn").addEventListener("click", analyze);
$("cutBtn").addEventListener("click", cut);
$("openBtn").addEventListener("click", openOutput);
$("langBtn").addEventListener("click", () => {
  currentLang = currentLang === "en" ? "zh" : "en";
  localStorage.setItem("assetGridCutterLang", currentLang);
  applyLanguage();
});
applyLanguage();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    raise SystemExit(main())
