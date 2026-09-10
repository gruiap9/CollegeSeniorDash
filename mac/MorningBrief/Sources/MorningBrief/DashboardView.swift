import AppKit
import SwiftUI

struct DashboardView: View {
    @ObservedObject var store: BriefStore

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider()
            if let b = store.brief {
                ScrollView {
                    VStack(alignment: .leading, spacing: 14) {
                        if !b.sinceYesterday.isEmpty { SinceYesterdayView(events: b.sinceYesterday) }
                        JobSearchView(job: b.jobSearch)
                        EmailView(emails: b.importantEmail, ignored: b.ignoredEmailCount)
                        SchoolView(school: b.school)
                        PiazzaView(courses: b.piazza)
                        NewsView(items: b.news)
                        SyncFooter(status: b.syncStatus)
                    }
                    .padding(16)
                }
            } else {
                VStack(spacing: 12) {
                    Image(systemName: "sun.horizon").font(.system(size: 40)).foregroundStyle(.secondary)
                    Text(store.loadError ?? "Loading…").multilineTextAlignment(.center).foregroundStyle(.secondary)
                    Button("Refresh") { store.refresh() }
                }.frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .onAppear {
            if let b = store.brief { Notifier.notify(for: b) }
        }
        .onChange(of: store.brief?.generatedAt) { _, _ in if let b = store.brief { Notifier.notify(for: b) } }
    }

    private var header: some View {
        HStack(alignment: .firstTextBaseline) {
            VStack(alignment: .leading, spacing: 2) {
                Text(store.brief?.greeting.uppercased() ?? "MORNING BRIEF").font(.caption).fontWeight(.semibold).foregroundStyle(.secondary).tracking(1.2)
                Text(dateLine).font(.title2).fontWeight(.bold)
            }
            Spacer()
            VStack(alignment: .trailing, spacing: 4) {
                Button { store.refresh() } label: {
                    Label(store.isRefreshing ? "Refreshing…" : "Refresh", systemImage: "arrow.clockwise")
                }.disabled(store.isRefreshing)
                Text(store.lastRefreshMessage ?? store.generatedAtLabel).font(.caption2).foregroundStyle(.secondary).lineLimit(1)
            }
        }
        .padding(.horizontal, 16).padding(.vertical, 12)
    }

    private var dateLine: String {
        let f = DateFormatter(); f.dateFormat = "EEEE, MMM d • h:mm a"
        return f.string(from: Date())
    }
}

// MARK: - Shared pieces

struct Section<Content: View>: View {
    let title: String
    var badge: String? = nil
    @ViewBuilder var content: Content
    @State private var expanded = true

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Button { withAnimation(.easeInOut(duration: 0.15)) { expanded.toggle() } } label: {
                HStack(spacing: 8) {
                    Text(title).font(.caption).fontWeight(.bold).tracking(1.5).foregroundStyle(.secondary)
                    if let badge { Text(badge).font(.caption2).padding(.horizontal, 6).padding(.vertical, 1).background(.quaternary, in: Capsule()) }
                    Rectangle().fill(.quaternary).frame(height: 1)
                    Image(systemName: expanded ? "chevron.down" : "chevron.right").font(.caption2).foregroundStyle(.tertiary)
                }
            }.buttonStyle(.plain)
            if expanded { content }
        }
    }
}

struct LinkRow<Leading: View, Trailing: View>: View {
    let url: String?
    @ViewBuilder var leading: Leading
    @ViewBuilder var trailing: Trailing
    @State private var hover = false

    var body: some View {
        Button { Opener.open(url) } label: {
            HStack(alignment: .top, spacing: 8) {
                leading
                Spacer(minLength: 8)
                trailing
                if url != nil { Image(systemName: "arrow.up.right").font(.caption2).foregroundStyle(.tertiary).padding(.top, 3) }
            }
            .padding(.vertical, 5).padding(.horizontal, 8)
            .background(hover && url != nil ? Color.accentColor.opacity(0.08) : .clear, in: RoundedRectangle(cornerRadius: 6))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .onHover { hover = $0 }
        .disabled(url == nil)
    }
}

enum Opener {
    static func open(_ s: String?) {
        guard let s, let u = URL(string: s) else { return }
        NSWorkspace.shared.open(u)
    }
}

struct Pill: View {
    let text: String
    var color: Color = .secondary
    var body: some View {
        Text(text).font(.caption2).fontWeight(.semibold).foregroundStyle(color)
            .padding(.horizontal, 6).padding(.vertical, 2)
            .background(color.opacity(0.12), in: Capsule())
    }
}

struct EmptyLine: View {
    let text: String
    var body: some View { Text(text).font(.callout).foregroundStyle(.tertiary).padding(.horizontal, 8) }
}

func timeLabel(_ iso: String?) -> String {
    guard let d = ISO8601DateFormatter.parse(iso) else { return "" }
    let f = DateFormatter()
    f.dateFormat = Calendar.current.isDateInToday(d) ? "h:mm a" : "MMM d"
    return f.string(from: d)
}
