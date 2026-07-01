"""
app/letters_of_light/release_server.py - Local campaign manager for release gates.

This server exposes local review controls and explicit per-platform publish
actions. It stays bound to localhost by default.
"""
from __future__ import annotations

import argparse
import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from app.letters_of_light.release import (
    approve_release,
    create_release_candidate,
    export_campaign,
    scan_letters,
    _letter_dir,
    _read_json,
)
from app.letters_of_light.release_site import publish_release_site
from app.letters_of_light.publishers.youtube import publish_youtube
from app.letters_of_light.wtpu_publication_dashboard import (
    handle_wtpu_publication_api,
    is_wtpu_publication_path,
    render_wtpu_publication_dashboard_page,
    wtpu_method_not_allowed_payload,
)


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


def _json_bytes(data: Any) -> bytes:
    return json.dumps(data, indent=2).encode("utf-8")


def _read_release(letter_id: str) -> Dict[str, Any]:
    return _read_json(_letter_dir(letter_id) / "release.json")


def _export_dir_for(letter_id: str) -> Path:
    return _letter_dir(letter_id) / "release_export"


def _public_release_log_for(letter_id: str) -> Dict[str, Any]:
    return _read_json(_letter_dir(letter_id) / "public_release_log.json")


def _folder_uri(path: Path) -> str:
    try:
        return path.resolve().as_uri()
    except ValueError:
        return ""


def _letters_payload() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for row in scan_letters():
        letter_id = row.get("letter_id", "")
        release = _read_release(letter_id)
        export_dir = _export_dir_for(letter_id)
        export_exists = export_dir.exists() and export_dir.is_dir()

        enriched = dict(row)
        targets = release.get("targets", {})
        site = targets.get("site", {}) if isinstance(targets.get("site"), dict) else {}
        youtube = targets.get("youtube", {}) if isinstance(targets.get("youtube"), dict) else {}
        log = _public_release_log_for(letter_id)
        enriched["approved"] = bool(release.get("approved", False))
        enriched["canonical_url"] = release.get("canonical_url")
        enriched["site_status"] = site.get("status")
        enriched["youtube_status"] = youtube.get("status")
        enriched["youtube_url"] = youtube.get("url")
        enriched["youtube_platform_id"] = youtube.get("platform_id") or youtube.get("video_id")
        enriched["youtube_error"] = youtube.get("error")
        enriched["release_log_path"] = str(_letter_dir(letter_id) / "public_release_log.json") if log else ""
        enriched["manual_social_urls"] = log.get("social_urls", {}) if isinstance(log.get("social_urls"), dict) else {}
        enriched["release_export_dir"] = str(export_dir) if export_exists else ""
        enriched["release_export_url"] = _folder_uri(export_dir) if export_exists else ""
        rows.append(enriched)
    return rows


def _extract_letter_id(body: Dict[str, Any]) -> str:
    letter_id = str(body.get("letter_id", "")).strip()
    if not letter_id:
        raise ValueError("letter_id is required")
    return letter_id


def _render_page() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Letters of Light Campaign Manager</title>
  <style>
    :root {
      --bg: #f7f7f4;
      --panel: #ffffff;
      --ink: #1f2528;
      --muted: #667075;
      --line: #d9ddd8;
      --green: #18623c;
      --green-bg: #e7f4ec;
      --red: #9a2d2d;
      --red-bg: #f7e8e5;
      --blue: #264f7a;
      --blue-bg: #e5eef7;
      --amber: #795600;
      --amber-bg: #fff3cf;
      --button: #2f3a40;
      --button-hover: #141a1e;
      font-family: Inter, "Segoe UI", Arial, sans-serif;
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-size: 14px;
      line-height: 1.45;
    }

    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 18px 22px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
    }

    h1 {
      margin: 0;
      font-size: 20px;
      font-weight: 650;
      letter-spacing: 0;
    }

    main {
      padding: 18px 22px 28px;
      width: 100%;
      overflow-x: auto;
    }

    .summary {
      display: flex;
      align-items: center;
      gap: 10px;
      color: var(--muted);
      white-space: nowrap;
    }

    button, .link-button {
      appearance: none;
      border: 1px solid transparent;
      background: var(--button);
      color: #fff;
      border-radius: 6px;
      padding: 7px 10px;
      min-height: 32px;
      font: inherit;
      font-weight: 600;
      letter-spacing: 0;
      text-decoration: none;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      white-space: nowrap;
    }

    button:hover, .link-button:hover { background: var(--button-hover); }
    button:disabled, .link-button[aria-disabled="true"] {
      background: #c6cbc8;
      color: #5d6668;
      cursor: not-allowed;
    }

    .toolbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 14px;
    }

    .status {
      min-height: 22px;
      color: var(--muted);
      font-size: 13px;
    }

    table {
      width: 100%;
      min-width: 1380px;
      border-collapse: collapse;
      background: var(--panel);
      border: 1px solid var(--line);
    }

    th, td {
      border-bottom: 1px solid var(--line);
      padding: 10px;
      text-align: left;
      vertical-align: middle;
    }

    th {
      position: sticky;
      top: 0;
      z-index: 1;
      background: #eef0ed;
      color: #3d4649;
      font-size: 12px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0;
    }

    tr:last-child td { border-bottom: 0; }
    td.id { font-family: Consolas, "SFMono-Regular", monospace; font-size: 13px; }
    td.title { min-width: 180px; font-weight: 620; }
    td.score, td.audio { font-variant-numeric: tabular-nums; }

    .badge {
      display: inline-flex;
      align-items: center;
      min-height: 24px;
      border-radius: 999px;
      padding: 3px 9px;
      font-size: 12px;
      font-weight: 700;
      white-space: nowrap;
    }

    .yes { color: var(--green); background: var(--green-bg); }
    .no { color: var(--red); background: var(--red-bg); }
    .state-exported, .state-approved, .state-published { color: var(--green); background: var(--green-bg); }
    .state-candidate { color: var(--blue); background: var(--blue-bg); }
    .state-manual_required, .state-failed { color: var(--red); background: var(--red-bg); }
    .state-unseen, .state-draft, .state-scheduled, .state-pending { color: var(--amber); background: var(--amber-bg); }

    .actions {
      display: flex;
      align-items: center;
      gap: 7px;
      min-width: 520px;
      flex-wrap: wrap;
    }

    select {
      min-height: 32px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: var(--ink);
      font: inherit;
      padding: 6px 8px;
    }

    .path {
      color: var(--muted);
      font-family: Consolas, "SFMono-Regular", monospace;
      font-size: 12px;
      max-width: 260px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    @media (max-width: 760px) {
      header, .toolbar {
        align-items: flex-start;
        flex-direction: column;
      }
      main { padding: 14px; }
      table { min-width: 1240px; }
    }
  </style>
</head>
<body>
  <header>
    <h1>Letters of Light Campaign Manager</h1>
    <div class="summary" id="summary">Loading...</div>
  </header>
  <main>
    <div class="toolbar">
      <div class="status" id="status"></div>
      <button id="refresh" type="button">Refresh</button>
    </div>
    <table aria-label="Letters">
      <thead>
        <tr>
          <th>Letter ID</th>
          <th>Title</th>
          <th>Theme</th>
          <th>Score</th>
          <th>Audio</th>
          <th>Eligibility</th>
          <th>Release State</th>
          <th>Canonical</th>
          <th>Site</th>
          <th>YouTube</th>
          <th>Manual Log</th>
          <th>Export Folder</th>
          <th>Actions</th>
        </tr>
      </thead>
      <tbody id="letters"></tbody>
    </table>
  </main>
  <script>
    const tbody = document.getElementById("letters");
    const statusEl = document.getElementById("status");
    const summaryEl = document.getElementById("summary");
    const refreshBtn = document.getElementById("refresh");

    function stateClass(value) {
      return "state-" + String(value || "unseen").replace(/[^a-z0-9_]+/gi, "_").toLowerCase();
    }

    function escapeHtml(value) {
      return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
    }

    function badge(text, cls) {
      return `<span class="badge ${cls}">${escapeHtml(text)}</span>`;
    }

    function setBusy(isBusy) {
      document.querySelectorAll("button").forEach((button) => {
        if (button.id !== "refresh") button.disabled = isBusy;
      });
      refreshBtn.disabled = isBusy;
    }

    async function api(path, body) {
      const response = await fetch(path, {
        method: body ? "POST" : "GET",
        headers: body ? {"Content-Type": "application/json"} : {},
        body: body ? JSON.stringify(body) : undefined
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || `Request failed: ${response.status}`);
      }
      return data;
    }

    async function runAction(path, letterId, extra = {}) {
      setBusy(true);
      statusEl.textContent = `${letterId}: working`;
      try {
        await api(path, {letter_id: letterId, ...extra});
        await loadLetters();
        statusEl.textContent = `${letterId}: updated`;
      } catch (error) {
        statusEl.textContent = `${letterId}: ${error.message}`;
      } finally {
        setBusy(false);
      }
    }

    function openExport(row) {
      if (!row.release_export_url) return;
      window.open(row.release_export_url, "_blank", "noopener");
    }

    async function copyManualPackage(row) {
      const lines = [
        `Letter: ${row.title || row.letter_id}`,
        `Canonical: ${row.canonical_url || ""}`,
        "Collection: https://brendonrcoleman.com/letters/",
        `Export: ${row.release_export_dir || ""}`
      ];
      await navigator.clipboard.writeText(lines.join("\\n"));
    }

    function render(rows) {
      const eligibleCount = rows.filter((row) => row.eligible).length;
      const exportedCount = rows.filter((row) => row.release_state === "exported").length;
      const publishedCount = rows.filter((row) => row.release_state === "published").length;
      summaryEl.textContent = `${rows.length} letters | ${eligibleCount} eligible | ${exportedCount} exported | ${publishedCount} published`;

      tbody.innerHTML = rows.map((row) => {
        const eligible = row.eligible ? badge("eligible", "yes") : badge("blocked", "no");
        const state = row.release_state || "unseen";
        const stateBadge = badge(state, stateClass(state));
        const exportDisabled = row.release_export_url ? "" : "disabled";
        const candidateDisabled = row.eligible ? "" : "disabled";
        const approveDisabled = row.eligible ? "" : "disabled";
        const exportActionDisabled = row.approved ? "" : "disabled";
        const siteActionDisabled = (row.release_state === "exported" || row.release_state === "published") ? "" : "disabled";
        const youtubeActionDisabled = (row.approved && row.release_export_dir && row.youtube_status !== "published") ? "" : "disabled";
        const exportPath = row.release_export_dir || "";
        const score = row.evaluation_total ?? "";
        const audio = row.audio_alignment ?? "";
        const letterId = escapeHtml(row.letter_id);
        const title = escapeHtml(row.title || "");
        const theme = escapeHtml(row.theme || "");
        const exportTitle = escapeHtml(exportPath);
        const canonical = row.canonical_url
          ? `<a href="${escapeHtml(row.canonical_url)}" target="_blank" rel="noopener">Open</a>`
          : "";
        const site = badge(row.site_status || "pending", stateClass(row.site_status || "pending"));
        const youtubeStatus = row.youtube_url
          ? `<a href="${escapeHtml(row.youtube_url)}" target="_blank" rel="noopener">${badge(row.youtube_status || "published", stateClass(row.youtube_status || "published"))}</a>`
          : badge(row.youtube_status || "pending", stateClass(row.youtube_status || "pending"));
        const logCount = Object.values(row.manual_social_urls || {}).filter(Boolean).length;
        const manualLog = row.release_log_path ? `${logCount} URLs` : "";

        return `<tr>
          <td class="id">${letterId}</td>
          <td class="title">${title}</td>
          <td>${theme}</td>
          <td class="score">${escapeHtml(score)}</td>
          <td class="audio">${escapeHtml(audio)}</td>
          <td>${eligible}</td>
          <td>${stateBadge}</td>
          <td>${canonical}</td>
          <td>${site}</td>
          <td>${youtubeStatus}</td>
          <td>${escapeHtml(manualLog)}</td>
          <td><div class="path" title="${exportTitle}">${exportTitle}</div></td>
          <td>
            <div class="actions">
              <button type="button" ${candidateDisabled} data-action="/api/candidate" data-id="${letterId}">Candidate</button>
              <button type="button" ${approveDisabled} data-action="/api/approve" data-id="${letterId}">Approve</button>
              <button type="button" ${exportActionDisabled} data-action="/api/export" data-id="${letterId}">Export</button>
              <button type="button" ${siteActionDisabled} data-action="/api/publish-site" data-id="${letterId}">Publish to Site</button>
              <select ${youtubeActionDisabled} data-youtube-privacy="${letterId}" aria-label="YouTube privacy">
                <option value="unlisted" selected>Unlisted</option>
                <option value="private">Private</option>
                <option value="public">Public</option>
              </select>
              <button type="button" ${youtubeActionDisabled} data-action="/api/publish/youtube" data-id="${letterId}">Publish YouTube</button>
              <button type="button" ${exportDisabled} data-copy="${letterId}">Copy Manual Package</button>
              <button type="button" ${exportDisabled} data-open="${letterId}">Open</button>
            </div>
          </td>
        </tr>`;
      }).join("");

      tbody.querySelectorAll("button[data-action]").forEach((button) => {
        button.addEventListener("click", () => {
          const extra = {};
          if (button.dataset.action === "/api/publish/youtube") {
            const select = tbody.querySelector(`select[data-youtube-privacy="${button.dataset.id}"]`);
            extra.privacy_status = select ? select.value : "unlisted";
          }
          runAction(button.dataset.action, button.dataset.id, extra);
        });
      });
      tbody.querySelectorAll("button[data-open]").forEach((button) => {
        const row = rows.find((item) => item.letter_id === button.dataset.open);
        button.addEventListener("click", () => openExport(row));
      });
      tbody.querySelectorAll("button[data-copy]").forEach((button) => {
        const row = rows.find((item) => item.letter_id === button.dataset.copy);
        button.addEventListener("click", () => {
          copyManualPackage(row)
            .then(() => { statusEl.textContent = `${row.letter_id}: manual package copied`; })
            .catch((error) => { statusEl.textContent = `${row.letter_id}: ${error.message}`; });
        });
      });
    }

    async function loadLetters() {
      const rows = await api("/api/letters");
      render(rows);
    }

    refreshBtn.addEventListener("click", () => {
      statusEl.textContent = "Refreshing";
      loadLetters()
        .then(() => { statusEl.textContent = "Refreshed"; })
        .catch((error) => { statusEl.textContent = error.message; });
    });

    loadLetters()
      .then(() => { statusEl.textContent = "Ready"; })
      .catch((error) => { statusEl.textContent = error.message; });
  </script>
</body>
</html>
"""


class ReleaseRequestHandler(BaseHTTPRequestHandler):
    server_version = "LettersReleaseServer/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        if getattr(self.server, "quiet", False):
            return
        super().log_message(fmt, *args)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/":
            self._send_html(_render_page())
            return

        if path == "/wtpu-publication":
            self._send_html(render_wtpu_publication_dashboard_page())
            return

        if path.startswith("/api/wtpu-publication"):
            payload, status = handle_wtpu_publication_api(path, parsed.query)
            self._send_json(payload, status)
            return

        if path == "/api/letters":
            self._send_json(_letters_payload())
            return

        self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if is_wtpu_publication_path(path):
            self._send_json(
                wtpu_method_not_allowed_payload("POST"),
                HTTPStatus.METHOD_NOT_ALLOWED,
            )
            return

        body, error = self._read_body()
        if error:
            self._send_json({"error": error}, HTTPStatus.BAD_REQUEST)
            return

        try:
            letter_id = _extract_letter_id(body)
            if path == "/api/candidate":
                result = create_release_candidate(letter_id)
            elif path == "/api/approve":
                result = approve_release(letter_id)
            elif path == "/api/export":
                result = export_campaign(letter_id)
            elif path in {"/api/publish-site", "/api/publish/site"}:
                result = publish_release_site(letter_id)
            elif path == "/api/publish/youtube":
                result = publish_youtube(
                    letter_id,
                    privacy_status=str(body.get("privacy_status", "unlisted")),
                    force=bool(body.get("force", False)),
                )
            else:
                self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
                return
        except Exception as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return

        self._send_json({"ok": True, "result": result, "letters": _letters_payload()})

    def do_PUT(self) -> None:
        self._handle_unsupported_wtpu_method("PUT")

    def do_PATCH(self) -> None:
        self._handle_unsupported_wtpu_method("PATCH")

    def do_DELETE(self) -> None:
        self._handle_unsupported_wtpu_method("DELETE")

    def _handle_unsupported_wtpu_method(self, method: str) -> None:
        path = urlparse(self.path).path
        if is_wtpu_publication_path(path):
            self._send_json(
                wtpu_method_not_allowed_payload(method),
                HTTPStatus.METHOD_NOT_ALLOWED,
            )
            return
        self.send_error(HTTPStatus.NOT_IMPLEMENTED)

    def _read_body(self) -> Tuple[Dict[str, Any], Optional[str]]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length == 0:
            return {}, "request body is required"

        raw = self.rfile.read(length)
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            return {}, f"invalid JSON: {exc}"

        if not isinstance(parsed, dict):
            return {}, "request body must be a JSON object"
        return parsed, None

    def _send_html(self, html: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        payload = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def _send_json(self, data: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        payload = _json_bytes(data)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)


class ReleaseServer(ThreadingHTTPServer):
    quiet: bool = False


def serve(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, quiet: bool = False) -> None:
    server = ReleaseServer((host, port), ReleaseRequestHandler)
    server.quiet = quiet
    print(f"Letters of Light campaign manager: http://{host}:{port}/")
    server.serve_forever()


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.letters_of_light.release_server",
        description="Local Letters of Light campaign manager",
    )
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    serve(host=args.host, port=args.port, quiet=args.quiet)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
