# Swift Native vs Cross-Platform Web -- Decision Matrix

Version: 0.1 | Date: 2026-05-31

## Quick Summary

| | Swift Native | Web (FastAPI + JS) |
|---|---|---|
| **Primary user** | You, on a Mac | You + collaborators, any OS |
| **Time to working prototype** | 2-3 weeks | 1 week |
| **Code reuse with existing skills** | Low (new language) | High (same Python ecosystem) |
| **Graph rendering** | Same (3d-force-graph in both) | Same |
| **Distribution** | .dmg (macOS only) | `python app.py` (anywhere) |

## Detailed Comparison

### Development Speed

| Factor | Swift | Web | Notes |
|---|---|---|---|
| Language familiarity | New to learn | Python (already fluent) | Your skills, harness, vault_db are all Python |
| DB access | Rewrite vault_db.py in Swift | `from vault_db import VaultDB` | Web version imports existing code directly |
| LLM integration | URLSession + JSON parsing | httpx (2 lines) | Both hit same Ollama API |
| Subprocess mgmt | Foundation.Process | asyncio.subprocess | Both work, Python is simpler for piping |
| UI iteration | SwiftUI previews (fast for forms, slow for WebView) | Browser hot-reload | Web is faster for graph/layout iteration |
| Testing | XCTest | pytest | You already have pytest infrastructure |

**Winner: Web.** You avoid rewriting vault_db.py and skill runner in a new language. The API layer is ~200 lines of Python wrapping code you already have.

### Performance

| Factor | Swift | Web | Notes |
|---|---|---|---|
| Graph rendering | WebGL via WKWebView (Metal backend) | WebGL in Chrome/Safari | Identical -- same JS library, same GPU path |
| SQLite queries | C API direct, ~50us per query | Python sqlite3, ~200us per query | Both negligible for this workload |
| Memory overhead | ~80MB app + graph data | ~400MB Chrome + ~50MB Python | Chrome is heavy; Safari/WKWebView is lighter |
| Startup time | 1-2s (native app) | 2-3s (uvicorn + browser tab) | Marginal difference |
| 10k node graph | 60fps on M-series | 60fps on M-series | GPU-bound in both cases, same GPU |

**Winner: Tie.** The graph rendering is identical (same library, same GPU). SQLite difference is irrelevant. Memory difference exists but doesn't matter on a 32GB+ Mac.

### User Experience

| Factor | Swift | Web | Notes |
|---|---|---|---|
| Native macOS feel | Yes (SwiftUI) | No (browser tab) | Sidebar, menus, keyboard shortcuts feel native in Swift |
| File drag-and-drop | Native (NSView) | HTML5 drag-and-drop API | Both work; native is more polished |
| System integration | Spotlight, Services menu, dock icon | None | Swift-only advantage |
| Right-click menus | NSMenu (native) | Custom HTML/CSS | Native looks better, custom works fine |
| Window management | Native multi-window | Browser tabs | Swift supports split views, panels |
| Offline | Fully offline | Fully offline (localhost) | Both work identically |
| Keyboard shortcuts | Cmd+K style | Ctrl+K style | Minor |

**Winner: Swift.** A native app feels like a real tool, not a browser tab. But the functional difference is small.

### Distribution & Collaboration

| Factor | Swift | Web | Notes |
|---|---|---|---|
| macOS users | .dmg, one-click install | `pip install; python app.py` | .dmg is simpler for non-developers |
| Windows users | Not possible | Works | Dealbreaker if Windows users exist |
| Linux users | Not possible | Works | Dealbreaker if Linux users exist |
| Team sharing | Share .dmg file | Share git repo or Docker image | Web is easier to deploy |
| iPhone/iPad | Separate iOS app needed | Mobile Safari (read-only graph works) | Web works on mobile for free |
| Updates | Re-download .dmg | `git pull` | Web is easier to update |

**Winner: Web.** Unless your audience is exclusively Mac users.

### Maintainability

| Factor | Swift | Web | Notes |
|---|---|---|---|
| Codebase size | ~2000 lines Swift + ~500 lines JS | ~500 lines Python + ~500 lines JS | Web is 2x smaller |
| Languages | Swift + JavaScript + Python (for skills) | Python + JavaScript | Web is one fewer language |
| vault_db.py changes | Must sync Swift VaultDatabase.swift | Automatic (same import) | Web avoids dual maintenance |
| Skill plugin changes | No impact (subprocess) | No impact (subprocess) | Same in both |
| Debugging | Xcode | Browser DevTools + print() | Browser DevTools are more accessible |
| Claude Code assistance | Good (Swift support) | Excellent (Python is strongest) | AI assistance is better for Python |

**Winner: Web.** One fewer language to maintain, no schema sync between Python and Swift.

### Apple Intelligence

| Factor | Swift | Web | Notes |
|---|---|---|---|
| On-device 3B model | Yes (Foundation Models) | No | Swift-only feature |
| Zero-setup LLM | Yes (built into macOS 26) | No (requires Ollama) | Convenience, not capability |
| Structured output | @Generable protocol | N/A | Nice for intent classification |
| Quality vs Ollama | Much weaker (3B vs 30B) | N/A | Ollama is better for real work |

**Winner: Swift, but marginal.** Apple Intelligence is a convenience for lightweight routing. Ollama does the real work in both architectures. You can replicate the routing with a small Ollama model (phi-4:14b).

### Security & Sandboxing

| Factor | Swift | Web | Notes |
|---|---|---|---|
| File system access | Full (notarized .dmg) | Full (runs as your user) | Same |
| Network access | Full | Full | Same |
| Subprocess execution | Full | Full | Same |
| App Store future | Blocked (subprocess + localhost) | N/A | Not relevant for this project |

**Winner: Tie.** Both run with full user permissions.

## Risk Assessment

### Swift Risks
1. **Learning curve.** SwiftUI + WKWebView bridging has sharp edges (async, security policies, JS context lifecycle). Budget extra time for unfamiliar problems.
2. **Dual schema maintenance.** Every change to vault_db.py must be mirrored in Swift. This will cause bugs.
3. **WKWebView quirks.** Local file loading, CORS for localhost, and JavaScript bridge memory management are common pain points.
4. **macOS version dependency.** Apple Intelligence requires macOS 26 (Tahoe). Users on older macOS versions lose that feature.

### Web Risks
1. **No native feel.** It's a browser tab. Power users may find this unsatisfying.
2. **Browser dependency.** Users must have a modern browser. Not a real risk in practice.
3. **Port conflicts.** localhost:8000 could conflict with other services. Mitigate with configurable port.
4. **Security exposure.** FastAPI on 0.0.0.0 exposes the DB to the network. Default to 127.0.0.1 (localhost only).

## Recommendation

**Start with Web. Graduate to Swift if justified.**

Reasoning:
1. You need the explorer NOW to improve your skills and data model. Web gets you there fastest.
2. The graph.js code is identical in both architectures. If you later build the Swift shell, you drop in the same graph.html/graph.js files.
3. vault_db.py is the foundation. Web uses it directly. Swift requires a rewrite that will drift.
4. Your collaborators may use Windows/Linux. Web doesn't exclude them.
5. The "feel" advantage of Swift is real but secondary to having a working tool.

### Hybrid Path (if you want native feel later)

```
Phase 1: Web app (FastAPI + vanilla JS)
  - Working in days
  - Graph, sidebar, detail, chat all functional
  - Iterate on data model and skills with visual feedback

Phase 2: Swift shell (if native feel matters)
  - Create a macOS app that embeds WKWebView pointed at localhost:8000
  - Reuse 100% of the web frontend
  - Add native chrome: sidebar as SwiftUI, drag-and-drop, dock icon
  - FastAPI still runs as a subprocess -- no need to rewrite in Swift
  - Apple Intelligence for routing (optional)

Phase 3: Full native (only if performance demands it)
  - Replace FastAPI with Swift SQLite access
  - Only if the Python server becomes a bottleneck (unlikely)
```

This way you never throw away work. Each phase builds on the last.
