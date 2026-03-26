# ADR-002: Desktop App Shell

**Date:** 2026-03-23
**Status:** Accepted
**Supersedes:** Original PRD assumption of browser-tab web application

## Context

The original PRD designed MoLabel as a web application accessed via `localhost` in the user's browser. While functional, this delivery model has significant UX friction for a local-first desktop tool:

- **No app identity:** The tool is a browser tab, indistinguishable from dozens of other tabs. Users lose it, accidentally close it, and can't Cmd+Tab to it.
- **No system integration:** No system tray icon to show background processing status. No native file dialogs for importing datasets. No OS-level notifications when long-running agent jobs complete.
- **Manual startup:** Users must remember to start a Python process, then open a specific URL. If the process dies, the browser tab shows a connection error with no recovery guidance.
- **No auto-update:** Users must manually pull updates, reinstall dependencies, and restart the server.
- **No offline resilience:** A browser tab has no service worker by default, and building a full PWA adds complexity without delivering the native feel users expect from a desktop tool.

MoLabel is fundamentally a desktop productivity tool that happens to use web technologies for its UI. It should feel like a native application.

## Decision

Ship MoLabel as a **Tauri v2** native desktop application from day one.

### Architecture

```
+------------------------------------------------------+
|  Tauri Shell (Rust)                                  |
|  - Window management, system tray, native dialogs    |
|  - Auto-updater, app lifecycle                       |
|  +------------------------------------------------+  |
|  |  System Webview                                |  |
|  |  React Frontend (from ADR-001)                 |  |
|  |  - All UI rendering                            |  |
|  |  - Communicates with backend via localhost HTTP |  |
|  +------------------------------------------------+  |
|                                                      |
|  Sidecar Process Manager                             |
|  - Spawns Python/FastAPI backend as child process    |
|  - Monitors health, restarts on crash                |
|  - Manages graceful shutdown                         |
+------------------------------------------------------+
        |
        | localhost HTTP (127.0.0.1:port)
        |
+------------------------------------------------------+
|  Python/FastAPI Backend (sidecar)                    |
|  - All business logic, data processing, agent runs   |
|  - SQLite database, file-based project storage       |
|  - Bundled as PyInstaller/PyApp binary or managed    |
|    Python environment                                |
+------------------------------------------------------+
```

### Key Design Choices

- **Tauri v2 over Electron:** Tauri uses the system's native webview (WebKit on macOS, WebView2 on Windows, WebKitGTK on Linux) instead of bundling Chromium. This results in a ~5-10MB app binary versus Electron's ~200MB+. Tauri v2 adds stable mobile support, multi-window, and a refined plugin system.

- **Python as sidecar, not embedded:** The Python backend runs as a separate OS process managed by Tauri's sidecar API. This keeps the Python and Rust worlds cleanly separated. The sidecar can be a PyInstaller-frozen binary (no Python installation required on the user's machine) or a managed Python environment for development.

- **Localhost HTTP communication:** The frontend in the webview communicates with the Python backend via standard HTTP on `127.0.0.1`. This is the same protocol used in development mode, ensuring no behavioral differences between dev and production.

- **System tray:** A persistent tray icon shows whether workflows are running, provides quick access to active projects, and allows the app to remain running in the background to complete long agent jobs even when the window is closed.

- **Native file dialogs:** Dataset import and export use OS-native file pickers via Tauri's dialog API, providing a familiar experience and proper access to the filesystem.

- **Auto-updater:** Tauri's built-in updater checks for new versions on startup (configurable) and applies updates with user consent. Updates are differential when possible.

### Development Mode

In development, the system runs as a plain web application:

1. `uv run fastapi dev` starts the Python backend with hot reload.
2. `npm run dev` starts the Vite dev server with HMR.
3. The Vite dev server proxies API requests to the FastAPI backend.

Developers never need to compile Rust or build a Tauri binary during normal feature development. The Tauri shell is only built for integration testing and release packaging.

## Alternatives Considered

- **Browser-tab web app (original PRD):** Rejected because it provides poor UX for a local-first tool. No app identity, no system integration, manual startup, no auto-update. Acceptable for a developer tool used by its own authors, but not for a product targeting data practitioners.

- **Electron:** The dominant desktop-web hybrid framework. Rejected primarily for bundle size (~200MB+ due to bundled Chromium) and memory usage. Also, Tauri v2 has reached stability and provides all the features MoLabel needs (system tray, native dialogs, sidecar management, auto-update) at a fraction of the resource cost.

- **Wails (Go-based):** Similar concept to Tauri but using Go instead of Rust for the shell. Rejected because the ecosystem is less mature, the plugin system is less developed, and there is no advantage since MoLabel's shell logic is minimal (the Rust code is thin glue, not business logic).

- **PyWebView:** A Python-native option that wraps system webviews. Rejected because it lacks system tray support, auto-update infrastructure, and robust sidecar management. It also conflates the UI shell with the Python process, making crash recovery harder.

- **Flutter:** Considered for true native rendering. Rejected because it would require rewriting the entire frontend in Dart, abandoning the React ecosystem chosen in ADR-001, and adding a third language to the stack.

## Consequences

1. **Rust in the toolchain:** The project now includes Rust code for the Tauri shell. However, this code is thin (window config, tray setup, sidecar spawn) and changes infrequently. Most developers never need to touch it.

2. **Build complexity:** Release builds require `cargo tauri build`, which compiles the Rust shell, bundles the frontend assets, and packages the Python sidecar. CI/CD must build for macOS, Windows, and Linux separately.

3. **Python packaging:** The Python backend must be distributable as a standalone binary (via PyInstaller, PyApp, or similar) so end users don't need a Python installation. This adds a packaging step and requires testing the frozen binary's behavior.

4. **Dev mode parity:** The app must work identically as a browser-tab web app (dev mode) and as a Tauri desktop app (production). All features must be available in both modes, with Tauri-specific features (system tray, native dialogs) gracefully degrading to web equivalents in dev mode.

5. **Platform testing:** The app must be tested on macOS, Windows, and Linux. System webview differences (WebKit vs. WebView2 vs. WebKitGTK) may cause rendering or behavior variations that need to be caught in CI.

6. **Distribution:** The app can be distributed as `.dmg` (macOS), `.msi`/`.exe` (Windows), `.AppImage`/`.deb` (Linux). Auto-update infrastructure must be hosted (GitHub Releases or a custom update server).
