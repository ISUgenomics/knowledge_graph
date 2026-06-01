# Knowledge Graph Explorer -- Swift Native Implementation Spec

Version: 0.1 | Date: 2026-05-31 | Depends on: SPEC-CORE.md

## 1. Architecture Overview

```
+-----------------------------------------------------------+
|  SwiftUI App (macOS, notarized .dmg distribution)         |
|                                                           |
|  +-- Sidebar --------+  +-- WKWebView ----------------+  |
|  |  SwiftUI List      |  |  3d-force-graph (JS/WebGL)  |  |
|  |  Auto from schema  |  |  Metal-backed via WebKit     |  |
|  |  Search/filter     |  |  Right-click context menus   |  |
|  +--------------------+  +-----------------------------+  |
|                                                           |
|  +-- Detail Panel (SwiftUI) ----------------------------+ |
|  |  Markdown rendered via AttributedString or WKWebView  | |
|  |  On-demand from SQLite, never saved to disk           | |
|  +------------------------------------------------------+ |
|                                                           |
|  +-- Chat Panel (SwiftUI) ------------------------------+ |
|  |  TextEditor + message list                            | |
|  |  Apple Intelligence for routing (optional)            | |
|  |  Ollama API for SQL generation + skill dispatch       | |
|  +------------------------------------------------------+ |
|                                                           |
|  +-- Data Layer ----------------------------------------+ |
|  |  SQLite.swift or raw sqlite3 C API                    | |
|  |  Direct access to vault.db (no intermediary)          | |
|  +------------------------------------------------------+ |
|                                                           |
|  +-- Process Manager -----------------------------------+ |
|  |  Foundation.Process for Python skill subprocess       | |
|  |  Pipe stdout/stderr to log panel                      | |
|  +------------------------------------------------------+ |
+-----------------------------------------------------------+
```

## 2. Technology Choices

| Component | Technology | Rationale |
|---|---|---|
| UI framework | SwiftUI | Native macOS look, declarative, fast iteration with previews |
| Graph rendering | WKWebView + 3d-force-graph.js | Mature JS graph library, WebGL runs on Metal via WebKit, no need to reimplement force physics |
| SQLite access | sqlite3 C API (via Swift bridging) or SQLite.swift | No ORM -- direct queries matching vault_db.py patterns |
| JS-Swift bridge | WKScriptMessageHandler + evaluateJavaScript | Bidirectional: click events JS->Swift, data updates Swift->JS |
| Markdown rendering | swift-markdown + AttributedString | Native rendering without WebView overhead |
| LLM (lightweight) | Apple Foundation Models framework | On-device 3B model, zero setup, Swift-native API |
| LLM (heavy) | Ollama HTTP API via URLSession | `http://localhost:11434/api/chat`, streaming via AsyncBytes |
| Subprocess mgmt | Foundation.Process | Spawn Python scripts, pipe stdout/stderr |
| Distribution | Notarized .dmg | Full system access, no sandbox restrictions |

## 3. Project Structure

```
KnowledgeGraphExplorer/
  KnowledgeGraphExplorer.xcodeproj
  Sources/
    App/
      KnowledgeGraphExplorerApp.swift      -- @main entry, window setup
      ContentView.swift                     -- main split view layout
    Views/
      SidebarView.swift                     -- dynamic entity type list
      GraphContainerView.swift              -- WKWebView wrapper
      DetailPanelView.swift                 -- entity detail rendering
      ChatPanelView.swift                   -- chat input + message list
      SetupView.swift                       -- first-launch configuration
      ContextMenuActions.swift              -- right-click menu definitions
    Models/
      VaultDatabase.swift                   -- SQLite wrapper (mirrors vault_db.py)
      Entity.swift                          -- Codable struct for entities
      Relationship.swift                    -- Codable struct for relationships
      GraphData.swift                       -- JSON-serializable graph for JS
      ChatMessage.swift                     -- chat message model
    Services/
      DatabaseService.swift                 -- DB queries, watch for changes
      OllamaService.swift                   -- Ollama API client (streaming)
      AppleIntelligenceService.swift        -- Foundation Models wrapper
      SkillRunner.swift                     -- Python subprocess manager
      GraphBridge.swift                     -- WKScriptMessageHandler impl
    Resources/
      graph.html                            -- HTML page embedding 3d-force-graph
      graph.js                              -- graph initialization + event handlers
      graph.css                             -- graph styling
  Tests/
    VaultDatabaseTests.swift
    GraphBridgeTests.swift
```

## 4. Key Implementation Details

### 4.1 SQLite Access (VaultDatabase.swift)

Mirrors `vault_db.py` API exactly. Same schema, same queries, same normalization.

```swift
class VaultDatabase {
    private let db: OpaquePointer  // sqlite3*

    init(path: URL) throws { ... }

    // Graph data (two queries for entire graph)
    func allNodes() -> [GraphNode]        // SELECT id, type, name FROM entities
    func allEdges() -> [GraphEdge]        // SELECT source_id, target_id, rel_type FROM relationships

    // Dynamic schema discovery
    func entityTypes() -> [String]        // SELECT DISTINCT type FROM entities
    func relationshipTypes() -> [String]  // SELECT DISTINCT rel_type FROM relationships
    func entityCount(type: String) -> Int

    // Detail (on demand)
    func getEntity(id: String) -> Entity?
    func getRelationships(entityId: String) -> [Relationship]
    func neighbors(entityId: String) -> [Entity]

    // Mutations (for chat-driven updates)
    func execute(sql: String, params: [Any]) throws  // with confirmation gate
}
```

### 4.2 JS-Swift Bridge (GraphBridge.swift)

```swift
class GraphBridge: NSObject, WKScriptMessageHandler {
    weak var webView: WKWebView?
    var onNodeClick: ((String) -> Void)?
    var onNodeRightClick: ((String, CGPoint) -> Void)?

    // JS -> Swift: receive events
    func userContentController(_ controller: WKUserContentController,
                                didReceive message: WKScriptMessage) {
        // Parse: { event: "nodeClick", nodeId: "andrew-severin" }
        // Parse: { event: "nodeRightClick", nodeId: "...", x: 100, y: 200 }
    }

    // Swift -> JS: push data
    func loadGraph(nodes: [GraphNode], edges: [GraphEdge]) {
        let json = encodeGraphJSON(nodes, edges)
        webView?.evaluateJavaScript("updateGraph(\(json))")
    }

    func highlightNodes(ids: [String]) {
        webView?.evaluateJavaScript("highlightNodes(\(encode(ids)))")
    }

    func hideNode(id: String) {
        webView?.evaluateJavaScript("hideNode('\(id.escaped)')")
    }
}
```

### 4.3 Graph HTML/JS (graph.html + graph.js)

Single HTML page loaded into WKWebView. Uses `3d-force-graph` library (bundled, not CDN).

```javascript
// graph.js (key functions called from Swift)

const Graph = ForceGraph3D()(document.getElementById('graph-container'));

function updateGraph(data) {
    Graph.graphData({ nodes: data.nodes, links: data.edges });
    Graph.nodeColor(node => typeColorMap[node.type] || '#999');
    Graph.nodeLabel(node => node.name);
    Graph.linkColor(link => relColorMap[link.rel_type] || '#444');
}

function highlightNodes(ids) { /* pulse animation on matching nodes */ }
function hideNode(id) { /* remove from current view, not from data */ }
function setLayout(preset) { /* force-directed, hierarchical, clustered */ }

// Events -> Swift
Graph.onNodeClick(node => {
    window.webkit.messageHandlers.bridge.postMessage(
        { event: 'nodeClick', nodeId: node.id }
    );
});
Graph.onNodeRightClick((node, event) => {
    window.webkit.messageHandlers.bridge.postMessage(
        { event: 'nodeRightClick', nodeId: node.id, x: event.clientX, y: event.clientY }
    );
});
```

### 4.4 Ollama Integration (OllamaService.swift)

```swift
class OllamaService {
    let endpoint: URL  // http://localhost:11434

    func chat(messages: [ChatMessage], model: String = "qwen3-coder:30b") -> AsyncStream<String> {
        // POST /api/chat with streaming response
        // Parse NDJSON chunks, yield content tokens
    }

    func generateSQL(question: String, schema: String) async throws -> String {
        // System prompt with DB schema + examples
        // Returns raw SQL string
    }

    func classifyIntent(input: String) async throws -> Intent {
        // Returns: .query(sql), .mutation(sql), .skillDispatch(skillName, args)
    }

    func isAvailable() async -> Bool {
        // GET /api/tags -- check if Ollama is running
    }
}
```

### 4.5 Apple Intelligence Integration (AppleIntelligenceService.swift)

```swift
import FoundationModels

@Generable
struct IntentClassification {
    var category: String    // "query", "mutation", "skill"
    var confidence: Double
}

class AppleIntelligenceService {
    let session = LanguageModelSession()

    func classifyIntent(input: String) async throws -> IntentClassification {
        // Fast on-device classification
        // Falls back to Ollama if Foundation Models unavailable
    }

    func summarizeEntity(entity: Entity) async throws -> String {
        // Quick summary for detail panel
    }

    var isAvailable: Bool {
        // Check if Foundation Models framework is available (macOS 26+)
    }
}
```

### 4.6 Skill Runner (SkillRunner.swift)

```swift
class SkillRunner: ObservableObject {
    @Published var isRunning = false
    @Published var output: [String] = []

    struct Config {
        var pythonPath: URL      // /usr/bin/python3 or venv
        var skillsDir: URL       // path to skills/
        var ollamaModel: String  // qwen3-coder:30b
    }

    func run(skill: String, args: [String], config: Config) async throws {
        // Map skill name to run script:
        //   "person-research" -> skills/person_research/run.py
        //   "signal-capture"  -> skills/signal_capture/run_signal.py
        //   "event-research"  -> skills/event_research/run_event.py
        //   "center-research" -> skills/center_research/run_center.py
        let process = Process()
        process.executableURL = config.pythonPath
        process.arguments = [scriptPath] + args + ["--model", config.ollamaModel]

        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = pipe

        // Stream output line by line
        pipe.fileHandleForReading.readabilityHandler = { handle in
            let line = String(data: handle.availableData, encoding: .utf8) ?? ""
            Task { @MainActor in self.output.append(line) }
        }

        try process.run()
        process.waitUntilExit()
    }
}
```

### 4.7 First-Launch Setup (SetupView.swift)

Presented once, results saved to UserDefaults or a config.json.

Checks:
1. Ollama installed? --> `which ollama` or check `/usr/local/bin/ollama`
2. Ollama running? --> `GET http://localhost:11434/api/tags`
3. Model pulled? --> check response for `qwen3-coder:30b`
4. Python available? --> `which python3`
5. Skills directory? --> file picker, validate `harness/skill_harness.py` exists
6. vault.db path? --> file picker or "Create new"

## 5. Distribution

```bash
# Build
xcodebuild archive -scheme KnowledgeGraphExplorer -archivePath build/KGE.xcarchive

# Export
xcodebuild -exportArchive -archivePath build/KGE.xcarchive \
  -exportOptionsPlist ExportOptions.plist -exportPath build/

# Sign
codesign --deep --force --sign "Developer ID Application: ..." build/KnowledgeGraphExplorer.app

# Package DMG
hdiutil create -volname "Knowledge Graph Explorer" -srcfolder build/KnowledgeGraphExplorer.app \
  -ov -format UDZO build/KnowledgeGraphExplorer.dmg

# Notarize
xcrun notarytool submit build/KnowledgeGraphExplorer.dmg \
  --apple-id you@email.com --team-id XXXXX --password @keychain:notary --wait

# Staple
xcrun stapler staple build/KnowledgeGraphExplorer.dmg
```

Users: double-click .dmg, drag to Applications, run. No Gatekeeper warning.

## 6. Build Order

| Phase | Deliverable | Depends on |
|---|---|---|
| 1 | VaultDatabase.swift + tests | vault_db.py schema (exists) |
| 2 | SwiftUI shell: sidebar + empty graph container | Phase 1 |
| 3 | graph.html/js + GraphBridge: render nodes/edges from DB | Phase 2 |
| 4 | Click handler: detail panel from DB | Phase 3 |
| 5 | Right-click: context menu + hide/expand | Phase 3 |
| 6 | OllamaService: chat-to-SQL for read queries | Phase 1 |
| 7 | Chat panel UI wired to OllamaService | Phase 6 |
| 8 | SkillRunner: spawn Python subprocesses | Phase 1 |
| 9 | Right-click "Research this person" --> SkillRunner | Phase 5, 8 |
| 10 | Apple Intelligence routing (optional, macOS 26+) | Phase 6 |
| 11 | Layout presets, clustering, embedding viz | Phase 3 |
| 12 | Notarized .dmg packaging | All |

Phases 1-5 produce a working graph explorer. Phases 6-9 add the chat + skill integration. Phases 10-12 are polish.
