import Foundation
import Combine
import StoreKit

@MainActor
final class MonetizationStore: ObservableObject {
    @Published private(set) var isPremium = false
    @Published private(set) var hasAdSession = false
    @Published private(set) var playToken: String?
    @Published private(set) var isWorking = false
    @Published private(set) var statusText = "Free access"
    @Published private(set) var lastError: String?

    private let feedService = FeedURLService()
    private let productID = AppConfig.premiumProductID
    private let accountTokenKey = "monetization.appAccountToken"
    private let defaults: UserDefaults
    private var logger: AppLogStore?

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
    }

    var canPlay: Bool {
        isPremium || hasAdSession
    }

    var appAccountToken: UUID {
        if
            let stored = defaults.string(forKey: accountTokenKey),
            let uuid = UUID(uuidString: stored)
        {
            return uuid
        }

        let uuid = UUID()
        defaults.set(uuid.uuidString, forKey: accountTokenKey)
        return uuid
    }

    func attachLogger(_ logger: AppLogStore) {
        self.logger = logger
    }

    func clearPlaySession() {
        hasAdSession = false
        playToken = nil
        statusText = isPremium ? "Premium active" : "Free access"
    }

    func refreshEntitlements(feedConfigURL: String) async {
        isWorking = true
        defer { isWorking = false }

        do {
            var foundPremium = false
            for await verification in Transaction.currentEntitlements {
                guard case .verified(let transaction) = verification else {
                    continue
                }
                guard transaction.productID == productID, transaction.revocationDate == nil else {
                    continue
                }
                if let expirationDate = transaction.expirationDate, expirationDate <= Date() {
                    continue
                }

                foundPremium = true
                await verifyWithPi(verification: verification, transaction: transaction, feedConfigURL: feedConfigURL)
            }

            isPremium = foundPremium
            statusText = foundPremium ? "Premium active" : "Free access"
            lastError = nil
        } catch {
            lastError = error.localizedDescription
            logger?.warning("Entitlement refresh failed: \(error.localizedDescription)")
        }
    }

    func purchasePremium(feedConfigURL: String) async {
        isWorking = true
        defer { isWorking = false }

        do {
            let products = try await Product.products(for: [productID])
            guard let product = products.first else {
                throw MonetizationError.productUnavailable
            }

            let result = try await product.purchase(options: [.appAccountToken(appAccountToken)])
            switch result {
            case .success(let verification):
                guard case .verified(let transaction) = verification else {
                    throw MonetizationError.unverifiedTransaction
                }
                await verifyWithPi(verification: verification, transaction: transaction, feedConfigURL: feedConfigURL)
                await transaction.finish()
                isPremium = true
                hasAdSession = false
                statusText = "Premium active"
                lastError = nil
            case .userCancelled:
                statusText = "Purchase cancelled"
            case .pending:
                statusText = "Purchase pending"
            @unknown default:
                statusText = "Purchase unavailable"
            }
        } catch {
            lastError = error.localizedDescription
            logger?.warning("Purchase failed: \(error.localizedDescription)")
        }
    }

    func requestRewardedPlay(feedConfigURL: String, feedId: String?) async -> Bool {
        isWorking = true
        defer { isWorking = false }

        do {
            let url = try feedService.makeBackendURL(feedConfigURL: feedConfigURL, path: "/access/play-session")
            var request = URLRequest(url: url)
            request.httpMethod = "POST"
            request.timeoutInterval = 10
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.setValue("application/json", forHTTPHeaderField: "Accept")
            request.httpBody = try JSONSerialization.data(
                withJSONObject: [
                    "deviceAccountToken": appAccountToken.uuidString,
                    "feedId": feedId ?? ""
                ],
                options: []
            )

            let (data, response) = try await URLSession.shared.data(for: request)
            guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
                throw URLError(.badServerResponse)
            }

            let decoded = try JSONDecoder().decode(PlaySessionResponse.self, from: data)
            hasAdSession = decoded.allowed
            playToken = decoded.playToken
            statusText = decoded.allowed ? "Ad session active" : "Free access"
            lastError = decoded.allowed ? nil : decoded.reason
            return decoded.allowed
        } catch {
            lastError = error.localizedDescription
            logger?.warning("Rewarded play failed: \(error.localizedDescription)")
            return false
        }
    }

    private func verifyWithPi(
        verification: VerificationResult<Transaction>,
        transaction: Transaction,
        feedConfigURL: String
    ) async {
        do {
            let url = try feedService.makeBackendURL(feedConfigURL: feedConfigURL, path: "/entitlements/apple/verify")
            var request = URLRequest(url: url)
            request.httpMethod = "POST"
            request.timeoutInterval = 10
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.setValue("application/json", forHTTPHeaderField: "Accept")
            request.httpBody = try JSONSerialization.data(
                withJSONObject: [
                    "appAccountToken": appAccountToken.uuidString,
                    "productId": transaction.productID,
                    "transactionId": String(transaction.id),
                    "signedTransactionInfo": verification.jwsRepresentation
                ],
                options: []
            )

            let (data, response) = try await URLSession.shared.data(for: request)
            guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
                throw URLError(.badServerResponse)
            }

            let decoded = try JSONDecoder().decode(AppleEntitlementResponse.self, from: data)
            logger?.info("Pi entitlement active=\(decoded.active)")
        } catch {
            logger?.warning("Pi entitlement verification failed: \(error.localizedDescription)")
        }
    }
}

enum MonetizationError: LocalizedError {
    case productUnavailable
    case unverifiedTransaction

    var errorDescription: String? {
        switch self {
        case .productUnavailable:
            return "The subscription product is not available."
        case .unverifiedTransaction:
            return "The App Store transaction could not be verified."
        }
    }
}
