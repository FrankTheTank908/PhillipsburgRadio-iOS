import Foundation
import Combine

#if canImport(GoogleMobileAds)
import GoogleMobileAds
#endif

@MainActor
final class RewardedAdStore: NSObject, ObservableObject {
    @Published private(set) var isLoading = false
    @Published private(set) var isReady = false
    @Published private(set) var lastError: String?

#if canImport(GoogleMobileAds)
    private var rewardedAd: RewardedAd?
    private var rewardContinuation: CheckedContinuation<Bool, Never>?
    private var didEarnReward = false
#endif

    func preload(adUnitID: String, customData: String) async {
        guard !adUnitID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            isReady = false
            return
        }

#if canImport(GoogleMobileAds)
        guard rewardedAd == nil, !isLoading else { return }
        isLoading = true
        defer { isLoading = false }

        do {
            let ad = try await RewardedAd.load(with: adUnitID, request: Request())
            let options = ServerSideVerificationOptions()
            options.customRewardText = customData
            ad.serverSideVerificationOptions = options
            ad.fullScreenContentDelegate = self
            rewardedAd = ad
            isReady = true
            lastError = nil
        } catch {
            isReady = false
            lastError = error.localizedDescription
        }
#else
        isReady = false
#endif
    }

    func show(adUnitID: String, customData: String) async -> Bool {
        guard !adUnitID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            return false
        }

#if canImport(GoogleMobileAds)
        if rewardedAd == nil {
            await preload(adUnitID: adUnitID, customData: customData)
        }

        guard let rewardedAd else {
            return false
        }

        let options = ServerSideVerificationOptions()
        options.customRewardText = customData
        rewardedAd.serverSideVerificationOptions = options
        didEarnReward = false
        isReady = false

        return await withCheckedContinuation { continuation in
            rewardContinuation = continuation
            rewardedAd.present(from: nil) { [weak self] in
                Task { @MainActor in
                    self?.didEarnReward = true
                }
            }
        }
#else
        return false
#endif
    }

#if canImport(GoogleMobileAds)
    private func finishRewardAttempt(_ rewarded: Bool) {
        rewardContinuation?.resume(returning: rewarded)
        rewardContinuation = nil
        rewardedAd = nil
        isReady = false
    }
#endif
}

#if canImport(GoogleMobileAds)
extension RewardedAdStore: FullScreenContentDelegate {
    func adDidDismissFullScreenContent(_ ad: FullScreenPresentingAd) {
        finishRewardAttempt(didEarnReward)
    }

    func ad(_ ad: FullScreenPresentingAd, didFailToPresentFullScreenContentWithError error: Error) {
        lastError = error.localizedDescription
        finishRewardAttempt(false)
    }
}
#endif
