import Foundation

// Mirrors backend/morningbrief/services/brief_builder.py (version 1).

struct Brief: Codable {
    var version: Int
    var generatedAt: String
    var date: String
    var greeting: String
    var sinceYesterday: [BriefEvent]
    var jobSearch: JobSearch
    var importantEmail: [ImportantEmail]
    var ignoredEmailCount: Int
    var school: School
    var piazza: [PiazzaCourse]
    var news: [NewsItem]
    var syncStatus: [String: SyncStatus]

    enum CodingKeys: String, CodingKey {
        case version, date, greeting, piazza, news, school
        case generatedAt = "generated_at"
        case sinceYesterday = "since_yesterday"
        case jobSearch = "job_search"
        case importantEmail = "important_email"
        case ignoredEmailCount = "ignored_email_count"
        case syncStatus = "sync_status"
    }
}

struct BriefEvent: Codable, Identifiable {
    var kind: String
    var title: String
    var detail: String?
    var url: String?
    var course: String?
    var importance: Int
    var at: String?
    var id: String { kind + title + (at ?? "") }
}

struct JobSearch: Codable {
    var counts7d: [String: Int]
    var items: [JobItem]
    enum CodingKeys: String, CodingKey { case items; case counts7d = "counts_7d" }
}

struct JobItem: Codable, Identifiable {
    var company: String?
    var event: String
    var summary: String?
    var subject: String?
    var url: String?
    var receivedAt: String?
    var importance: Int
    var id: String { (url ?? "") + event + (subject ?? "") }
    enum CodingKeys: String, CodingKey { case company, event, summary, subject, url, importance; case receivedAt = "received_at" }
}

struct ImportantEmail: Codable, Identifiable {
    var sender: String?
    var senderEmail: String?
    var role: String?
    var subject: String?
    var summary: String?
    var url: String?
    var receivedAt: String?
    var id: String { (url ?? "") + (subject ?? "") }
    enum CodingKeys: String, CodingKey {
        case sender, role, subject, summary, url
        case senderEmail = "sender_email"; case receivedAt = "received_at"
    }
}

struct AssignmentItem: Codable, Identifiable {
    var course: String
    var title: String
    var due: String?
    var dueLabel: String
    var status: String?
    var grade: String?
    var url: String?
    var source: String?
    var hoursRemaining: Double?
    var id: String { course + title + (due ?? "") }
    enum CodingKeys: String, CodingKey {
        case course, title, due, status, grade, url, source
        case dueLabel = "due_label"; case hoursRemaining = "hours_remaining"
    }
}

struct NewGrade: Codable, Identifiable {
    var course: String?
    var title: String
    var grade: String?
    var url: String?
    var at: String?
    var id: String { (course ?? "") + title }
}

struct SchoolChange: Codable, Identifiable {
    var course: String?
    var title: String
    var detail: String?
    var url: String?
    var id: String { title + (detail ?? "") }
}

struct School: Codable {
    var overdue: [AssignmentItem]
    var today: [AssignmentItem]
    var tomorrow: [AssignmentItem]
    var next3Days: [AssignmentItem]
    var next7Days: [AssignmentItem]
    var later: [AssignmentItem]
    var newGrades: [NewGrade]
    var changes: [SchoolChange]
    enum CodingKeys: String, CodingKey {
        case overdue, today, tomorrow, later, changes
        case next3Days = "next_3_days"; case next7Days = "next_7_days"; case newGrades = "new_grades"
    }
}

struct PiazzaImportant: Codable, Identifiable {
    var label: String
    var summary: String
    var url: String?
    var id: String { label + summary }
}

struct PiazzaCourse: Codable, Identifiable {
    var course: String
    var newCount: Int
    var important: [PiazzaImportant]
    var otherSummary: String?
    var url: String?
    var id: String { course }
    enum CodingKeys: String, CodingKey {
        case course, important, url
        case newCount = "new_count"; case otherSummary = "other_summary"
    }
}

struct NewsItem: Codable, Identifiable {
    var rank: Int
    var title: String
    var summary: String?
    var source: String?
    var sources: [String]?
    var url: String
    var publishedAt: String?
    var id: String { url }
    enum CodingKeys: String, CodingKey { case rank, title, summary, source, sources, url; case publishedAt = "published_at" }
}

struct SyncStatus: Codable {
    var lastSuccess: String?
    var lastError: String?
    enum CodingKeys: String, CodingKey { case lastSuccess = "last_success"; case lastError = "last_error" }
}
