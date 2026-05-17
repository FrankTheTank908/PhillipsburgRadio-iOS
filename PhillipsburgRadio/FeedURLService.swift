import Foundation

enum FeedURLError: LocalizedError {
    case missingConfigURL
    case invalidConfigURL
    case invalidStreamURL
    case badServerResponse
    case emptyResponse

    var errorDescription: String? {
        switch self {
        case .missingConfigURL:
            return "The feed config URL is missing."
        case .invalidConfigURL:
            return "The feed config URL is invalid."
        case .invalidStreamURL:
            return "The stream URL from the config file is invalid."
        case .badServerResponse:
            return "The server returned an invalid response."
        case .emptyResponse:
            return "The feed config response was empty."
        }
    }
}

final class FeedURLService {
    func fetchCurrentConfig(
        feedConfigURL: String,
        feedId: String? = nil,
        playToken: String? = nil,
        forceRefresh: Bool = false
    ) async throws -> FeedConfig {
        guard !feedConfigURL.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            throw FeedURLError.missingConfigURL
        }

        guard
            let baseURL = URL(string: feedConfigURL),
            var components = URLComponents(url: baseURL, resolvingAgainstBaseURL: false)
        else {
            throw FeedURLError.invalidConfigURL
        }

        if let feedId, !feedId.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            var queryItems = components.queryItems ?? []
            queryItems.removeAll { $0.name == "feedId" || $0.name == "feed_id" }
            queryItems.append(URLQueryItem(name: "feedId", value: feedId.trimmingCharacters(in: .whitespacesAndNewlines)))
            components.queryItems = queryItems
        }

        if let playToken, !playToken.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            var queryItems = components.queryItems ?? []
            queryItems.removeAll { $0.name == "playToken" || $0.name == "play_token" }
            queryItems.append(URLQueryItem(name: "playToken", value: playToken.trimmingCharacters(in: .whitespacesAndNewlines)))
            components.queryItems = queryItems
        }

        if forceRefresh {
            var queryItems = components.queryItems ?? []
            queryItems.removeAll { $0.name == "refresh" || $0.name == "_" }
            queryItems.append(URLQueryItem(name: "refresh", value: "1"))
            queryItems.append(URLQueryItem(name: "_", value: String(Int(Date().timeIntervalSince1970))))
            components.queryItems = queryItems
        }

        guard let url = components.url else {
            throw FeedURLError.invalidConfigURL
        }

        var request = URLRequest(url: url)
        request.cachePolicy = .reloadIgnoringLocalAndRemoteCacheData
        request.timeoutInterval = 12
        request.setValue("application/json", forHTTPHeaderField: "Accept")

        let (data, response) = try await URLSession.shared.data(for: request)

        guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
            throw FeedURLError.badServerResponse
        }

        guard !data.isEmpty else {
            throw FeedURLError.emptyResponse
        }

        let config = try JSONDecoder().decode(FeedConfig.self, from: data)
        _ = try validatedStreamURL(from: config)

        return config
    }

    func fetchCurrentStreamURL(feedConfigURL: String, feedId: String? = nil, playToken: String? = nil) async throws -> URL {
        let config = try await fetchCurrentConfig(feedConfigURL: feedConfigURL, feedId: feedId, playToken: playToken)
        return try validatedStreamURL(from: config)
    }

    func makeBackendURL(feedConfigURL: String, path: String, queryItems: [URLQueryItem] = []) throws -> URL {
        guard
            let url = URL(string: feedConfigURL),
            var components = URLComponents(url: url, resolvingAgainstBaseURL: false)
        else {
            throw FeedURLError.invalidConfigURL
        }

        components.path = path
        components.queryItems = queryItems.isEmpty ? nil : queryItems

        guard let builtURL = components.url else {
            throw FeedURLError.invalidConfigURL
        }

        return builtURL
    }

    func fetchCatalog(feedConfigURL: String, path: String, queryItems: [URLQueryItem] = []) async throws -> CatalogResponse {
        let url = try makeBackendURL(feedConfigURL: feedConfigURL, path: path, queryItems: queryItems)
        var request = URLRequest(url: url)
        request.cachePolicy = .reloadIgnoringLocalAndRemoteCacheData
        request.timeoutInterval = 14
        request.setValue("application/json", forHTTPHeaderField: "Accept")

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
            throw FeedURLError.badServerResponse
        }
        return try JSONDecoder().decode(CatalogResponse.self, from: data)
    }

    private func validatedStreamURL(from config: FeedConfig) throws -> URL {
        guard
            let streamURL = URL(string: config.streamUrl),
            let scheme = streamURL.scheme?.lowercased(),
            ["http", "https"].contains(scheme),
            streamURL.host?.isEmpty == false
        else {
            throw FeedURLError.invalidStreamURL
        }

        return streamURL
    }
}
