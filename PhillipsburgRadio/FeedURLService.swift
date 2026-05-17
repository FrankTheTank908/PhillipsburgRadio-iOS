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
    func fetchCurrentConfig(feedConfigURL: String, forceRefresh: Bool = false) async throws -> FeedConfig {
        guard !feedConfigURL.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            throw FeedURLError.missingConfigURL
        }

        guard
            let baseURL = URL(string: feedConfigURL),
            var components = URLComponents(url: baseURL, resolvingAgainstBaseURL: false)
        else {
            throw FeedURLError.invalidConfigURL
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

    func fetchCurrentStreamURL(feedConfigURL: String) async throws -> URL {
        let config = try await fetchCurrentConfig(feedConfigURL: feedConfigURL)
        return try validatedStreamURL(from: config)
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
