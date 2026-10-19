import Foundation
import STTNative
import UIKit
import Combine

@MainActor final class LabStore: ObservableObject {
    @Published var coordinator = UserDefaults.standard.string(forKey: "coordinator") ?? ""
    @Published var models: [ModelManifest] = []
    @Published var installed: Set<String> = []
    @Published var selectedModelId = ""
    @Published var phase = "Idle"
    @Published var error = ""
    @Published var progress = 0.0
    @Published var entries: [Journal.Entry] = []
    @Published var localHistory: [(String, String, String)] = []
    @Published var latest: NativeResult?
    @Published var microphoneLatest: NativeResult?
    @Published var conditions: DeviceConditions?
    @Published var task: Task<Void, Never>?
    @Published var thermalObservations: [String] = []
    @Published var exportURL: URL?
    private let engine = NativeEngine()
    let root: URL
    private let cache: ModelCache
    private let journal: Journal

    init() {
        root = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0].appendingPathComponent("STTBenchmarkLab", isDirectory: true)
        do {
            try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
            cache = try ModelCache(root: root.appendingPathComponent("models", isDirectory: true))
            journal = try Journal(url: root.appendingPathComponent("experiments.sqlite3"))
            if let data = try? Data(contentsOf: root.appendingPathComponent("model-catalog.json")) {
                models = try LabJSON.decoder.decode([ModelManifest].self, from: data)
            }
        } catch { fatalError("Cannot initialize private storage: \(error)") }
        refreshHistory()
        Task { await refreshInstalled(); await observe() }
    }
    var selected: ModelManifest? { models.first { $0.id == selectedModelId } }
    var isBusy: Bool { task != nil }
    var client: CoordinatorClient? {
        guard let base = URL(string: coordinator), let token = Credentials.read() else { return nil }
        return try? CoordinatorClient(base: base, token: token)
    }
    func operate(_ operation: @escaping @MainActor () async throws -> Void) {
        guard task == nil else { return }
        error = ""
        task = Task {
            defer { task = nil; refreshHistory() }
            do { try await operation(); phase = "Complete" }
            catch is CancellationError { phase = "Cancelled — partial results retained" }
            catch { self.error = error.localizedDescription; phase = "Needs attention" }
        }
    }
    func cancel() { task?.cancel() }
    func refreshHistory() {
        do { entries = try journal.entries(); localHistory = try journal.localHistory() }
        catch { self.error = error.localizedDescription }
    }
    func exportEvidence() {
        do {
            let url = root.appendingPathComponent("STT-Lab-local-evidence-\(UUID().uuidString).sqlite3")
            try journal.export(to: url)
            exportURL = url
        } catch { self.error = error.localizedDescription }
    }
    func observe() async {
        conditions = await Measurements.conditions()
        if let conditions { thermalObservations.append("\(conditions.capturedAt) · \(conditions.thermalState) · \(conditions.residentMemoryBytes ?? 0) resident bytes") }
    }
    func refreshInstalled() async {
        var ids = Set<String>()
        for model in models { if await cache.isInstalled(model) { ids.insert(model.id) } }
        installed = ids
        if selectedModelId.isEmpty { selectedModelId = models.first(where: { ids.contains($0.id) })?.id ?? "" }
    }
    func pair(token: String) async throws {
        guard let base = URL(string: coordinator) else { throw LabError.invalid("Enter your Mac's local URL") }
        let pairing = try CoordinatorClient(base: base, token: token)
        struct Payload: Encodable { let name: String; let details: DeviceConditions }
        let details = await Measurements.conditions()
        let receipt: PairingReceipt = try await pairing.request("/api/v1/device/pair", method: "POST",
            body: LabJSON.encoder.encode(Payload(name: UIDevice.current.name, details: details)))
        try Credentials.save(receipt.token)
        UserDefaults.standard.set(coordinator, forKey: "coordinator")
        phase = "Paired with Mac"
        try await refreshModels()
    }
    func refreshModels() async throws {
        guard let client else { throw LabError.invalid("Pair with your Mac first") }
        models = try await client.request("/api/v1/device/models")
        try LabJSON.encoder.encode(models).write(to: root.appendingPathComponent("model-catalog.json"), options: .atomic)
        await refreshInstalled()
    }
    func install(_ model: ModelManifest) async throws {
        guard let client else { throw LabError.invalid("Pair with your Mac first") }
        phase = "Installing \(model.family)"
        try await cache.install(model, client: client) { done, total in
            await MainActor.run { self.progress = Double(done) / Double(max(1,total)); self.phase = "Verified \(done) / \(total) model files" }
        }
        await refreshInstalled()
    }
    func remove(_ model: ModelManifest) async throws {
        await engine.unload()
        try await cache.remove(model)
        await refreshInstalled()
    }
    func unload() async { await engine.unload(); phase = "Model unloaded" }
    func cacheJobs() async throws {
        guard let client else { throw LabError.invalid("Pair with your Mac first") }
        struct Claim: Encodable { let installedModelIds: [String] }
        var count = 0
        while true {
            try Task.checkCancellation()
            let job: DeviceJob? = try await client.request("/api/v1/device/claim", method: "POST",
                body: LabJSON.encoder.encode(Claim(installedModelIds: Array(installed))))
            guard let job else { break }
            phase = "Caching input \(count + 1)"
            let audio = root.appendingPathComponent("audio/\(job.id).wav")
            do {
                try await client.download(job.audioUrl, to: audio, sha256: job.audioSha256)
                try journal.store(job: job)
            } catch {
                struct Failure: Encodable { let attemptId: String; let error: String }
                let _: [String:String] = try await client.request("/api/v1/device/jobs/\(job.id)/failure", method: "POST",
                    body: LabJSON.encoder.encode(Failure(attemptId: job.attemptId, error: error.localizedDescription)))
                throw error
            }
            count += 1; refreshHistory()
        }
        phase = "\(count) inputs cached. Wi-Fi may now be disconnected."
    }
    func runCached() async throws {
        let pending = try journal.entries().filter { ["cached", "interrupted"].contains($0.state) }.reversed()
        guard !pending.isEmpty else { throw LabError.invalid("Cache jobs from a running iPhone experiment first") }
        // Claim order was randomized by the coordinator seed. No network call occurs in this loop.
        for entry in pending {
            try Task.checkCancellation()
            let job = try LabJSON.decoder.decode(DeviceJob.self, from: Data(entry.payload.utf8))
            let audio = root.appendingPathComponent("audio/\(job.id).wav")
            let modelRoot = try await cache.modelRoot(job.model)
            let request = NativeRequest(audio: audio.path, audioSha256: job.audioSha256, modelRoot: modelRoot.path,
                model: job.model, settings: job.settings, language: job.language)
            phase = "Running \(job.model.family) · repetition \(job.repetition + 1)"
            try journal.state(entry.id, state: "interrupted")
            do {
                let result = try await engine.run(request)
                try Task.checkCancellation()
                try journal.result(job: job, value: result)
                latest = result; refreshHistory(); await observe()
            } catch is CancellationError { throw CancellationError() }
            catch {
                try journal.state(entry.id, state: "failed", error: error.localizedDescription)
                refreshHistory()
            }
        }
        phase = "Local runs finished; synchronize results when connected"
    }
    func sync() async throws {
        guard let client else { throw LabError.invalid("Pair with your Mac first") }
        for entry in try journal.entries() where entry.state == "pending-sync" || entry.state == "failed" {
            do {
                let job = try LabJSON.decoder.decode(DeviceJob.self, from: Data(entry.payload.utf8))
                if entry.state == "pending-sync" {
                    let _: [String:String] = try await client.request("/api/v1/device/jobs/\(job.id)/result", method: "POST", body: Data(entry.result.utf8))
                    try journal.state(entry.id, state: "synchronized")
                } else {
                    let job = try LabJSON.decoder.decode(DeviceJob.self, from: Data(entry.payload.utf8))
                    struct Failure: Encodable { let attemptId: String; let error: String }
                    let _: [String:String] = try await client.request("/api/v1/device/jobs/\(job.id)/failure", method: "POST",
                        body: LabJSON.encoder.encode(Failure(attemptId: job.attemptId, error: entry.error)))
                    try journal.state(entry.id, state: "failure-synchronized", error: entry.error)
                }
            } catch {
                // Conflict/network errors retain the original envelope for explicit investigation/export.
                self.error = error.localizedDescription
            }
        }
        refreshHistory()
    }
    func dictate(audio: URL, captureSeconds: Double) async throws {
        guard let model = selected else { throw LabError.invalid("Install and select a supported model first") }
        let start = ContinuousClock().now
        let directory = try await cache.modelRoot(model)
        let request = NativeRequest(audio: audio.path, audioSha256: try AssetIntegrity.hash(audio),
            modelRoot: directory.path, model: model, settings: RunSettings(), language: "auto")
        phase = "Post-recording batch transcription — no native partials"
        let result = try await engine.run(request)
        try Task.checkCancellation()
        let finalization = Measurements.seconds(start.duration(to: ContinuousClock().now))
        try journal.local(kind: "microphone-post-recording-batch", request: request, result: result,
                          captureSeconds: captureSeconds, finalizationSeconds: finalization)
        latest = result; microphoneLatest = result; await observe()
    }
    func sustained(repetitions: Int, warmups: Int) async throws {
        guard let model = selected, let entry = try journal.entries().last else { throw LabError.invalid("Install a model and cache owner-recorded audio first") }
        let job = try LabJSON.decoder.decode(DeviceJob.self, from: Data(entry.payload.utf8))
        let audio = root.appendingPathComponent("audio/\(job.id).wav")
        let directory = try await cache.modelRoot(model)
        for index in 0..<repetitions {
            try Task.checkCancellation()
            phase = "Sustained local test \(index + 1) / \(repetitions)"
            let request = NativeRequest(audio: audio.path, audioSha256: job.audioSha256, modelRoot: directory.path,
                model: model, settings: RunSettings(warmups: index == 0 ? warmups : 0), language: job.language)
            let result = try await engine.run(request)
            try Task.checkCancellation()
            try journal.local(kind: "sustained", request: request, result: result, captureSeconds: nil, finalizationSeconds: nil)
            latest = result; refreshHistory(); await observe()
        }
    }
}
