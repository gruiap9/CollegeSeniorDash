import AppKit
import Foundation

/// Persists tiny app state (last day the brief was shown, preferences).
final class AppState {
    static let shared = AppState()
    private var dict: [String: Any] = [:]

    private init() {
        if let d = try? Data(contentsOf: Paths.stateFile), let js = try? JSONSerialization.jsonObject(with: d) as? [String: Any] { dict = js }
    }
    private func save() {
        try? FileManager.default.createDirectory(at: Paths.dataDir, withIntermediateDirectories: true)
        if let d = try? JSONSerialization.data(withJSONObject: dict, options: [.prettyPrinted, .sortedKeys]) { try? d.write(to: Paths.stateFile) }
    }
    var lastBriefShownDate: String? {
        get { dict["last_brief_shown_date"] as? String }
        set { dict["last_brief_shown_date"] = newValue; save() }
    }
    var autoShow: Bool {
        get { dict["auto_show"] as? Bool ?? true }
        set { dict["auto_show"] = newValue; save() }
    }
    var lastNotifiedEventIds: [String] {
        get { dict["notified_ids"] as? [String] ?? [] }
        set { dict["notified_ids"] = Array(newValue.suffix(500)); save() }
    }
}

/// Shows the dashboard on the first launch / wake / unlock of each calendar day.
@MainActor
final class FirstOpenController {
    private var observers: [Any] = []

    static func todayString() -> String {
        let f = DateFormatter(); f.dateFormat = "yyyy-MM-dd"; f.timeZone = .current
        return f.string(from: Date())
    }

    func start() {
        let dnc = DistributedNotificationCenter.default()
        observers.append(dnc.addObserver(forName: Notification.Name("com.apple.screenIsUnlocked"), object: nil, queue: .main) { [weak self] _ in self?.check() })
        let wnc = NSWorkspace.shared.notificationCenter
        observers.append(wnc.addObserver(forName: NSWorkspace.didWakeNotification, object: nil, queue: .main) { [weak self] _ in
            DispatchQueue.main.asyncAfter(deadline: .now() + 2) { self?.check() }
        })
        observers.append(wnc.addObserver(forName: NSWorkspace.sessionDidBecomeActiveNotification, object: nil, queue: .main) { [weak self] _ in self?.check() })
        // Also poll once a minute so a Mac left open still gets the brief at the day boundary.
        Timer.scheduledTimer(withTimeInterval: 60, repeats: true) { [weak self] _ in self?.check() }
        DispatchQueue.main.asyncAfter(deadline: .now() + 1) { [weak self] in self?.check() }
    }

    func check() {
        guard AppState.shared.autoShow else { return }
        let today = Self.todayString()
        if AppState.shared.lastBriefShownDate != today {
            AppState.shared.lastBriefShownDate = today
            Self.openDashboard()
        }
    }

    static func openDashboard() {
        DashboardWindow.shared.show()
    }
}
