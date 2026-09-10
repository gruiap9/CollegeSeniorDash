import Foundation
import UserNotifications

/// Only notifies for genuinely important events (importance == 3, plus new grades).
enum Notifier {
    static let notifyKinds: Set<String> = ["job.interview", "job.oa", "job.offer", "assignment.due_soon", "assignment.due_changed", "grade.new", "email.important"]

    static func requestPermission() {
        guard Bundle.main.bundleIdentifier != nil else { return }  // bare executable: no notification center
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound]) { _, _ in }
    }

    static func notify(for brief: Brief) {
        guard Bundle.main.bundleIdentifier != nil else { return }
        var seen = AppState.shared.lastNotifiedEventIds
        let center = UNUserNotificationCenter.current()
        for e in brief.sinceYesterday where notifyKinds.contains(e.kind) && (e.importance >= 3 || e.kind == "grade.new") {
            let key = e.kind + "|" + e.title + "|" + (e.at ?? "")
            if seen.contains(key) { continue }
            seen.append(key)
            let c = UNMutableNotificationContent()
            c.title = e.title
            c.body = e.detail ?? ""
            c.sound = .default
            if let u = e.url { c.userInfo = ["url": u] }
            center.add(UNNotificationRequest(identifier: key, content: c, trigger: nil))
        }
        AppState.shared.lastNotifiedEventIds = seen
    }
}
