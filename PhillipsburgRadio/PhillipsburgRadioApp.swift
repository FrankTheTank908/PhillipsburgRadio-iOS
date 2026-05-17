import SwiftUI
import AVFoundation

#if canImport(GoogleMobileAds)
import GoogleMobileAds
#endif

@main
struct PhillipsburgRadioApp: App {
    init() {
        configureAudioSession()
        configureMobileAds()
    }

    var body: some Scene {
        WindowGroup {
            ContentView()
        }
    }

    private func configureAudioSession() {
        do {
            try AVAudioSession.sharedInstance().setCategory(.playback, mode: .default, options: [])
            try AVAudioSession.sharedInstance().setActive(true)
        } catch {
            print("Audio session setup failed: \(error.localizedDescription)")
        }
    }

    private func configureMobileAds() {
#if canImport(GoogleMobileAds)
        MobileAds.shared.start()
#endif
    }
}
