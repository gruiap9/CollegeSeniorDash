import Foundation

enum Paths {
    static var dataDir: URL {
        if let o = ProcessInfo.processInfo.environment["MORNINGBRIEF_HOME"] { return URL(fileURLWithPath: o) }
        return FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("MorningBrief", isDirectory: true)
    }
    static var briefFile: URL { dataDir.appendingPathComponent("morning_brief.json") }
    static var backendFile: URL { dataDir.appendingPathComponent("backend.json") }
    static var stateFile: URL { dataDir.appendingPathComponent("app_state.json") }
}
