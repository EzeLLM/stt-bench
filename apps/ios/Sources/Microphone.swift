import AVFoundation
import Foundation
import STTNative
import Combine

@MainActor final class Microphone: ObservableObject {
    @Published var isRecording = false
    private var recorder: AVAudioRecorder?
    private var started: ContinuousClock.Instant?
    private(set) var captureSeconds: Double = 0
    func start(to url: URL) async throws {
        let allowed = await AVAudioApplication.requestRecordPermission()
        guard allowed else { throw NSError(domain: "Microphone permission is required", code: 1) }
        let session = AVAudioSession.sharedInstance()
        try session.setCategory(.record, mode: .measurement, options: [])
        try session.setActive(true)
        // Native capture format is retained. Model-specific conversion is inside the adapter and timed there.
        recorder = try AVAudioRecorder(url: url, settings: [AVFormatIDKey: kAudioFormatLinearPCM,
            AVSampleRateKey: 48000, AVNumberOfChannelsKey: 1, AVLinearPCMBitDepthKey: 16,
            AVLinearPCMIsFloatKey: false, AVLinearPCMIsBigEndianKey: false])
        guard recorder?.record() == true else { throw NSError(domain: "Cannot start audio capture", code: 2) }
        started = ContinuousClock().now; isRecording = true
    }
    func stop() {
        recorder?.stop(); isRecording = false
        if let started { captureSeconds = STTNative.Measurements.seconds(started.duration(to: ContinuousClock().now)) }
        try? AVAudioSession.sharedInstance().setActive(false)
    }
}
