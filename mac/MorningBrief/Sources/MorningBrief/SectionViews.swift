import SwiftUI

struct SinceYesterdayView: View {
    let events: [BriefEvent]
    var body: some View {
        Section(title: "SINCE YESTERDAY", badge: "\(events.count)") {
            ForEach(events.prefix(10)) { e in
                LinkRow(url: e.url) {
                    HStack(alignment: .top, spacing: 8) {
                        Text(glyph(e.kind)).font(.callout).frame(width: 16)
                        VStack(alignment: .leading, spacing: 1) {
                            Text(e.title).font(.callout).fontWeight(e.importance >= 3 ? .semibold : .regular)
                            if let d = e.detail, !d.isEmpty { Text(d).font(.caption).foregroundStyle(.secondary).lineLimit(2) }
                        }
                    }
                } trailing: { Text(timeLabel(e.at)).font(.caption2).foregroundStyle(.tertiary) }
            }
        }
    }
    func glyph(_ k: String) -> String {
        switch k {
        case "job.oa", "job.interview", "job.offer", "job.next_round": return "★"
        case "job.rejection": return "✕"
        case "assignment.due_changed", "assignment.due_soon", "site.changed": return "!"
        case "grade.new": return "✓"
        case "assignment.submitted": return "✓"
        case "piazza.instructor": return "💬"
        case "email.important": return "✉"
        default: return "•"
        }
    }
}

struct JobSearchView: View {
    let job: JobSearch
    private let order = ["OA", "INTERVIEW", "OFFER", "APPLICATION_RECEIVED", "REJECTION"]
    var body: some View {
        Section(title: "JOB SEARCH") {
            HStack(spacing: 14) {
                ForEach(order, id: \.self) { k in
                    VStack(spacing: 1) {
                        Text("\(job.counts7d[k] ?? 0)").font(.title3).fontWeight(.bold)
                        Text(label(k)).font(.caption2).foregroundStyle(.secondary)
                    }
                }
                Spacer()
                Text("last 7 days").font(.caption2).foregroundStyle(.tertiary)
            }.padding(.horizontal, 8)
            if job.items.isEmpty { EmptyLine(text: "No job-search email in the last 24 hours.") }
            ForEach(job.items) { j in
                LinkRow(url: j.url) {
                    VStack(alignment: .leading, spacing: 1) {
                        HStack(spacing: 6) {
                            Text(j.company ?? "Unknown").font(.callout).fontWeight(.semibold)
                            Pill(text: label(j.event), color: color(j.event))
                        }
                        Text(j.summary ?? j.subject ?? "").font(.caption).foregroundStyle(.secondary).lineLimit(2)
                    }
                } trailing: { Text(timeLabel(j.receivedAt)).font(.caption2).foregroundStyle(.tertiary) }
            }
        }
    }
    func label(_ k: String) -> String {
        switch k {
        case "OA": return "OA"; case "INTERVIEW": return "Interview"; case "OFFER": return "Offer"
        case "APPLICATION_RECEIVED": return "Applied"; case "REJECTION": return "Rejected"
        case "NEXT_ROUND": return "Next round"; case "RECRUITER": return "Recruiter"
        default: return k.capitalized
        }
    }
    func color(_ k: String) -> Color {
        switch k {
        case "OFFER", "INTERVIEW", "NEXT_ROUND": return .green
        case "OA": return .orange
        case "REJECTION": return .red
        default: return .secondary
        }
    }
}

struct EmailView: View {
    let emails: [ImportantEmail]
    let ignored: Int
    var body: some View {
        Section(title: "IMPORTANT EMAIL") {
            if emails.isEmpty { EmptyLine(text: "Nothing important from school in the last 24 hours.") }
            ForEach(emails) { e in
                LinkRow(url: e.url) {
                    VStack(alignment: .leading, spacing: 1) {
                        HStack(spacing: 6) {
                            Text(e.sender ?? e.senderEmail ?? "").font(.callout).fontWeight(.semibold)
                            if let r = e.role { Pill(text: r.replacingOccurrences(of: "_", with: " ")) }
                        }
                        Text("“" + (e.summary ?? e.subject ?? "") + "”").font(.caption).foregroundStyle(.secondary).lineLimit(2)
                    }
                } trailing: { Text(timeLabel(e.receivedAt)).font(.caption2).foregroundStyle(.tertiary) }
            }
            if ignored > 0 { Text("Ignored: \(ignored) newsletters / automated messages").font(.caption2).foregroundStyle(.tertiary).padding(.horizontal, 8) }
        }
    }
}

struct SchoolView: View {
    let school: School
    var body: some View {
        Section(title: "SCHOOL") {
            group("OVERDUE", school.overdue, .red)
            group("DUE TODAY", school.today, .red)
            group("TOMORROW", school.tomorrow, .orange)
            group("NEXT 3 DAYS", school.next3Days, .primary)
            group("NEXT 7 DAYS", school.next7Days, .secondary)
            if school.overdue.isEmpty && school.today.isEmpty && school.tomorrow.isEmpty && school.next3Days.isEmpty && school.next7Days.isEmpty {
                if let n = school.later.first {
                    Text("NEXT").font(.caption2).fontWeight(.bold).foregroundStyle(.tertiary).padding(.horizontal, 8)
                    row(n, .secondary)
                } else { EmptyLine(text: "Nothing due in the next week.") }
            }
            if !school.changes.isEmpty {
                Text("CHANGES").font(.caption2).fontWeight(.bold).foregroundStyle(.orange).padding(.horizontal, 8).padding(.top, 4)
                ForEach(school.changes) { c in
                    LinkRow(url: c.url) {
                        VStack(alignment: .leading, spacing: 1) {
                            Text("⚠ " + c.title).font(.callout)
                            if let d = c.detail { Text(d).font(.caption).foregroundStyle(.secondary).lineLimit(2) }
                        }
                    } trailing: { EmptyView() }
                }
            }
            if !school.newGrades.isEmpty {
                Text("NEW GRADES").font(.caption2).fontWeight(.bold).foregroundStyle(.green).padding(.horizontal, 8).padding(.top, 4)
                ForEach(school.newGrades) { g in
                    LinkRow(url: g.url) {
                        Text("\(g.course ?? "") — \(g.title)").font(.callout)
                    } trailing: { Text(g.grade ?? "Grade available").font(.callout).fontWeight(.semibold).foregroundStyle(.green) }
                }
            }
        }
    }

    @ViewBuilder func group(_ name: String, _ items: [AssignmentItem], _ color: Color) -> some View {
        if !items.isEmpty {
            Text(name).font(.caption2).fontWeight(.bold).foregroundStyle(color).padding(.horizontal, 8).padding(.top, 2)
            ForEach(items) { a in row(a, color) }
        }
    }

    func row(_ a: AssignmentItem, _ color: Color) -> some View {
        LinkRow(url: a.url) {
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 6) {
                    Text(a.course).font(.callout).fontWeight(.semibold)
                    Text(a.title).font(.callout)
                }
                HStack(spacing: 6) {
                    if let s = a.status, s != "unknown" { Text(s.capitalized).font(.caption).foregroundStyle(s == "unsubmitted" ? .orange : .secondary) }
                    if let h = a.hoursRemaining, h > 0, h < 48, a.status != "submitted", a.status != "graded" {
                        ProgressView(value: max(0, min(1, 1 - h / 48))).frame(width: 90)
                        Text("\(Int(h))h remaining").font(.caption2).foregroundStyle(.secondary)
                    }
                }
            }
        } trailing: { Text(a.dueLabel).font(.caption).fontWeight(.semibold).foregroundStyle(color) }
    }
}

struct PiazzaView: View {
    let courses: [PiazzaCourse]
    var body: some View {
        Section(title: "PIAZZA") {
            if courses.isEmpty { EmptyLine(text: "No Piazza activity captured. Enable Piazza email notifications to feed this section.") }
            ForEach(courses) { c in
                LinkRow(url: c.url) {
                    HStack(spacing: 6) {
                        Text(c.course).font(.callout).fontWeight(.semibold)
                        Text("• \(c.newCount) new").font(.caption).foregroundStyle(.secondary)
                    }
                } trailing: { EmptyView() }
                if c.important.isEmpty {
                    Text(c.otherSummary?.isEmpty == false ? c.otherSummary! : "No important activity.").font(.caption).foregroundStyle(.tertiary).padding(.leading, 20)
                }
                ForEach(c.important) { i in
                    LinkRow(url: i.url) {
                        HStack(alignment: .top, spacing: 6) {
                            Text("•").foregroundStyle(.secondary)
                            VStack(alignment: .leading, spacing: 0) {
                                Text(i.label).font(.caption).fontWeight(.semibold)
                                Text(i.summary).font(.caption).foregroundStyle(.secondary)
                            }
                        }.padding(.leading, 12)
                    } trailing: { EmptyView() }
                }
                if !c.important.isEmpty, let o = c.otherSummary, !o.isEmpty {
                    Text("Other: " + o).font(.caption2).foregroundStyle(.tertiary).padding(.leading, 20)
                }
            }
        }
    }
}

struct NewsView: View {
    let items: [NewsItem]
    var body: some View {
        Section(title: "TECH") {
            if items.isEmpty { EmptyLine(text: "No news collected yet.") }
            ForEach(items) { n in
                LinkRow(url: n.url) {
                    HStack(alignment: .top, spacing: 8) {
                        Text("\(n.rank)").font(.callout).fontWeight(.bold).foregroundStyle(.tertiary).frame(width: 14, alignment: .trailing)
                        VStack(alignment: .leading, spacing: 1) {
                            Text(n.title).font(.callout).fontWeight(.medium).lineLimit(2)
                            if let s = n.summary, !s.isEmpty { Text(s).font(.caption).foregroundStyle(.secondary).lineLimit(2) }
                            Text((n.sources ?? [n.source ?? ""]).joined(separator: " · ")).font(.caption2).foregroundStyle(.tertiary)
                        }
                    }
                } trailing: { EmptyView() }
            }
        }
    }
}

struct SyncFooter: View {
    let status: [String: SyncStatus]
    var body: some View {
        let errs = status.filter { $0.value.lastError != nil }
        if !errs.isEmpty {
            VStack(alignment: .leading, spacing: 2) {
                ForEach(errs.keys.sorted(), id: \.self) { k in
                    Text("⚠ \(k): \(errs[k]!.lastError!)").font(.caption2).foregroundStyle(.orange).lineLimit(1)
                }
            }.padding(.top, 6)
        }
    }
}
