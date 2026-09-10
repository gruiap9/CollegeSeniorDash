import AppKit
import SwiftUI

@main
struct MorningBriefApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var delegate
    @ObservedObject private var store = BriefStore.shared

    var body: some Scene {
        MenuBarExtra {
            MenuContent(store: store)
        } label: {
            Image(systemName: "sun.horizon.fill")
        }
        .menuBarExtraStyle(.menu)
    }
}

struct MenuContent: View {
    @ObservedObject var store: BriefStore

    var body: some View {
        Button("Open Morning Brief") { DashboardWindow.shared.show() }
            .keyboardShortcut("m")
        Button(store.isRefreshing ? "Refreshing…" : "Refresh now") { store.refresh() }
            .disabled(store.isRefreshing)
        if let msg = store.lastRefreshMessage { Text(msg) } else if !store.generatedAtLabel.isEmpty { Text(store.generatedAtLabel) }
        Divider()
        Toggle("Launch at login", isOn: Binding(get: { LaunchAtLogin.isEnabled }, set: { LaunchAtLogin.set($0) }))
        Toggle("Show brief on first unlock of the day", isOn: Binding(get: { AppState.shared.autoShow }, set: { AppState.shared.autoShow = $0 }))
        Button("Open data folder") { NSWorkspace.shared.open(Paths.dataDir) }
        Divider()
        Button("Quit Morning Brief") { NSApplication.shared.terminate(nil) }
            .keyboardShortcut("q")
    }
}

/// AppKit-managed dashboard window (reliable for LSUIElement menu-bar apps).
@MainActor
final class DashboardWindow: NSObject, NSWindowDelegate {
    static let shared = DashboardWindow()
    private var window: NSWindow?

    func show() {
        if window == nil {
            let host = NSHostingController(rootView: DashboardView(store: BriefStore.shared))
            let w = NSWindow(contentViewController: host)
            w.title = "Morning Brief"
            w.styleMask = [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView]
            w.titlebarAppearsTransparent = true
            w.setContentSize(NSSize(width: 600, height: 820))
            w.minSize = NSSize(width: 520, height: 500)
            w.isReleasedWhenClosed = false
            w.delegate = self
            w.center()
            w.setFrameAutosaveName("MorningBriefDashboard")
            window = w
        }
        NSApp.activate(ignoringOtherApps: true)
        window?.makeKeyAndOrderFront(nil)
    }

    func windowWillClose(_ notification: Notification) {
        // keep the window instance for fast re-open; nothing to do
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    private var firstOpen: FirstOpenController?

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)
        Notifier.requestPermission()
        firstOpen = FirstOpenController()
        firstOpen?.start()
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        DashboardWindow.shared.show()
        return true
    }
}
