// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "MorningBrief",
    platforms: [.macOS(.v14)],
    targets: [
        .executableTarget(
            name: "MorningBrief",
            path: "Sources/MorningBrief",
            swiftSettings: [.unsafeFlags(["-parse-as-library"])]
        )
    ]
)
