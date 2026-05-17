import Foundation

struct FeedConfig: Codable {
    let feedId: String?
    let title: String?
    let status: String?
    let listeners: Int?
    let bitrate: Int?
    let streamUrl: String
    let updatedAt: String?
    let expiresAt: String?
    let source: String?
    let message: String?
}

struct TranscriptEvent: Identifiable, Codable {
    let id: UUID
    let timestamp: String
    let text: String
    let confidence: Double?
    let keywords: [String]
    let channel: String?

    init(
        id: UUID = UUID(),
        timestamp: String,
        text: String,
        confidence: Double? = nil,
        keywords: [String] = [],
        channel: String? = nil
    ) {
        self.id = id
        self.timestamp = timestamp
        self.text = text
        self.confidence = confidence
        self.keywords = keywords
        self.channel = channel
    }

    enum CodingKeys: String, CodingKey {
        case id
        case timestamp
        case text
        case confidence
        case keywords
        case channel
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decodeIfPresent(UUID.self, forKey: .id) ?? UUID()
        timestamp = try container.decodeIfPresent(String.self, forKey: .timestamp) ?? "--:--"
        text = try container.decode(String.self, forKey: .text)
        confidence = try container.decodeIfPresent(Double.self, forKey: .confidence)
        keywords = try container.decodeIfPresent([String].self, forKey: .keywords) ?? []
        channel = try container.decodeIfPresent(String.self, forKey: .channel)
    }
}

struct TranscriptResponse: Codable {
    let events: [TranscriptEvent]
}
