import Combine
import Foundation

/// Loads morning_brief.json, watches it for changes, and can trigger a backend sync.
@MainActor
final class BriefStore: ObservableObject {
    static let shared = BriefStore()

    @Published var brief: Brief?
    @Published var loadError: String?
    @Published var isRefreshing = false
    @Published var lastRefreshMessage: String?

    private var watcher: DispatchSourceFileSystemObject?
    private var dirWatcher: DispatchSourceFileSystemObject?
    private var syncProcess: Process?

    init() {
        load()
        watch()
    }

    func load() {
        do {
            let data = try Data(contentsOf: Paths.briefFile)
            brief = try JSONDecoder().decode(Brief.self, from: data)
            loadError = nil
        } catch {
            if !FileManager.default.fileExists(atPath: Paths.briefFile.path) {
                loadError = "No brief yet. Run `morningbrief sync` once, or press Refresh."
            } else {
                loadError = "Could not read brief: \(error.localizedDescription)"
            }
        }
    }

    /// The backend writes the brief atomically via rename, so watch the directory too.
    private func watch() {
        try? FileManager.default.createDirectory(at: Paths.dataDir, withIntermediateDirectories: true)
        let fd = open(Paths.dataDir.path, O_EVTONLY)
        guard fd >= 0 else { return }
        let src = DispatchSource.makeFileSystemObjectSource(fileDescriptor: fd, eventMask: [.write, .rename, .delete], queue: .main)
        src.setEventHandler { [weak self] in self?.load() }
        src.setCancelHandler { close(fd) }
        src.resume()
        dirWatcher = src
    }

    /// Runs `python -m morningbrief.main sync` using the interpreter recorded by `morningbrief init`.
    func refresh() {
        guard !isRefreshing else { return }
        guard let cmd = Backend.command() else {
            lastRefreshMessage = "Backend not configured: run `morningbrief init` in backend/."
            return
        }
        isRefreshing = true
        lastRefreshMessage = "Refreshing…"
        let p = Process()
        p.executableURL = URL(fileURLWithPath: cmd.python)
        p.arguments = cmd.args + ["sync"]
        p.environment = ProcessInfo.processInfo.environment.merging(["PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"]) { a, _ in a }
        let pipe = Pipe()
        p.standardOutput = pipe
        p.standardError = pipe
        p.terminationHandler = { [weak self] proc in
            let out = String(data: pipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
            Task { @MainActor in
                self?.isRefreshing = false
                self?.lastRefreshMessage = proc.terminationStatus == 0 ? "Updated \(Self.timeString(Date()))" : "Sync failed (\(proc.terminationStatus)): " + out.suffix(300)
                self?.load()
            }
        }
        do { try p.run(); syncProcess = p } catch {
            isRefreshing = false
            lastRefreshMessage = "Could not start backend: \(error.localizedDescription)"
        }
    }

    static func timeString(_ d: Date) -> String {
        let f = DateFormatter(); f.dateFormat = "h:mm a"; return f.string(from: d)
    }

    var generatedAtLabel: String {
        guard let b = brief, let d = ISO8601DateFormatter.flexible.date(from: b.generatedAt) else { return "" }
        return "Updated " + Self.timeString(d)
    }
}

enum Backend {
    struct Command { let python: String; let args: [String] }

    static func command() -> Command? {
        guard let data = try? Data(contentsOf: Paths.backendFile),
              let js = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let py = js["python"] as? String else { return nil }
        let args = js["args"] as? [String] ?? ["-m", "morningbrief.main"]
        return Command(python: py, args: args)
    }
}

extension ISO8601DateFormatter {
    static let flexible: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f
    }()
    static let plain: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime]
        return f
    }()
    static func parse(_ s: String?) -> Date? {
        guard let s else { return nil }
        return flexible.date(from: s) ?? plain.date(from: s)
    }
}
