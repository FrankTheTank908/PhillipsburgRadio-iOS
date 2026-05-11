import Foundation

struct FeedConfig: Codable {
    let streamUrl: String
    let updatedAt: String?
    let message: String?
}

struct TranscriptEvent: Identifiable, Codable {
    let id: UUID
    let time: String
    let text: String

    init(id: UUID = UUID(), time: String, text: String) {
        self.id = id
        self.time = time
        self.text = text
    }
}
