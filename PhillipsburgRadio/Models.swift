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

struct CatalogResponse: Codable {
    let source: String?
    let action: String?
    let count: Int?
    let items: [CatalogItem]
    let message: String?
}

struct CatalogItem: Identifiable, Codable, Hashable {
    let id: String
    let name: String
    let type: String?
    let feedId: String?
    let countryId: String?
    let stateId: String?
    let countyId: String?
    let genre: String?
    let status: String?
    let listeners: Int?
    let bitrate: Int?
    let subtitle: String?

    var displaySubtitle: String {
        [subtitle, genre, status]
            .compactMap { value in
                let trimmed = value?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
                return trimmed.isEmpty ? nil : trimmed
            }
            .joined(separator: " | ")
    }

    var resolvedFeedId: String {
        feedId ?? id
    }
}

struct PlaySessionResponse: Codable {
    let ok: Bool
    let allowed: Bool
    let reason: String?
    let feedId: String?
    let playToken: String?
    let expiresAt: String?
}

struct AppleEntitlementResponse: Codable {
    let ok: Bool
    let active: Bool
    let message: String?
}

struct TranscriptEvent: Identifiable, Codable {
    let id: UUID
    let timestamp: String
    let startedAt: String?
    let endedAt: String?
    let text: String
    let confidence: Double?
    let keywords: [String]
    let channel: String?
    let incidentId: String?
    let incidentTitle: String?
    let durationSeconds: Double?
    let speechSeconds: Double?
    let source: String?

    init(
        id: UUID = UUID(),
        timestamp: String,
        startedAt: String? = nil,
        endedAt: String? = nil,
        text: String,
        confidence: Double? = nil,
        keywords: [String] = [],
        channel: String? = nil,
        incidentId: String? = nil,
        incidentTitle: String? = nil,
        durationSeconds: Double? = nil,
        speechSeconds: Double? = nil,
        source: String? = nil
    ) {
        self.id = id
        self.timestamp = timestamp
        self.startedAt = startedAt
        self.endedAt = endedAt
        self.text = text
        self.confidence = confidence
        self.keywords = keywords
        self.channel = channel
        self.incidentId = incidentId
        self.incidentTitle = incidentTitle
        self.durationSeconds = durationSeconds
        self.speechSeconds = speechSeconds
        self.source = source
    }

    enum CodingKeys: String, CodingKey {
        case id
        case timestamp
        case startedAt
        case endedAt
        case text
        case confidence
        case keywords
        case channel
        case incidentId
        case incidentTitle
        case durationSeconds
        case speechSeconds
        case source
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decodeIfPresent(UUID.self, forKey: .id) ?? UUID()
        timestamp = try container.decodeIfPresent(String.self, forKey: .timestamp) ?? "--:--"
        startedAt = try container.decodeIfPresent(String.self, forKey: .startedAt)
        endedAt = try container.decodeIfPresent(String.self, forKey: .endedAt)
        text = try container.decode(String.self, forKey: .text)
        confidence = try container.decodeIfPresent(Double.self, forKey: .confidence)
        keywords = try container.decodeIfPresent([String].self, forKey: .keywords) ?? []
        channel = try container.decodeIfPresent(String.self, forKey: .channel)
        incidentId = try container.decodeIfPresent(String.self, forKey: .incidentId)
        incidentTitle = try container.decodeIfPresent(String.self, forKey: .incidentTitle)
        durationSeconds = try container.decodeIfPresent(Double.self, forKey: .durationSeconds)
        speechSeconds = try container.decodeIfPresent(Double.self, forKey: .speechSeconds)
        source = try container.decodeIfPresent(String.self, forKey: .source)
    }
}

struct TranscriptResponse: Codable {
    let events: [TranscriptEvent]
    let incidents: [IncidentSummary]?
    let pipeline: TranscriptPipelineStatus?
}

struct IncidentSummary: Identifiable, Codable {
    let id: String
    let createdAt: String?
    let updatedAt: String?
    let title: String?
    let summary: String?
    let status: String?
    let keywords: [String]
    let transcriptCount: Int?
    let latestText: String?
    let aiReviewedAt: String?
    let aiModel: String?
}

struct TranscriptPipelineStatus: Codable {
    let ok: Bool?
    let state: String?
    let message: String?
    let updatedAt: String?
    let hasOpenAIKey: Bool?
    let transcribeModel: String?
    let incidentModel: String?
}

struct IncidentMessage: Identifiable, Codable {
    let id: UUID
    let timestamp: String
    let author: String
    let text: String
    let tags: [String]
    let channel: String?

    init(
        id: UUID = UUID(),
        timestamp: String,
        author: String,
        text: String,
        tags: [String] = [],
        channel: String? = nil
    ) {
        self.id = id
        self.timestamp = timestamp
        self.author = author
        self.text = text
        self.tags = tags
        self.channel = channel
    }

    enum CodingKeys: String, CodingKey {
        case id
        case timestamp
        case author
        case text
        case tags
        case channel
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decodeIfPresent(UUID.self, forKey: .id) ?? UUID()
        timestamp = try container.decodeIfPresent(String.self, forKey: .timestamp) ?? "--:--"
        author = try container.decodeIfPresent(String.self, forKey: .author) ?? "Local Debug"
        text = try container.decode(String.self, forKey: .text)
        tags = try container.decodeIfPresent([String].self, forKey: .tags) ?? []
        channel = try container.decodeIfPresent(String.self, forKey: .channel)
    }
}

struct IncidentResponse: Codable {
    let messages: [IncidentMessage]
}
