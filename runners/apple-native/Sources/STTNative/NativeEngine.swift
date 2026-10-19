@preconcurrency import WhisperKit
@preconcurrency import FluidAudio
import AVFoundation
import CoreML
import Foundation

/// Only local assets enter this actor. It has no coordinator or network client.
public actor NativeEngine {
    private var whisper: WhisperKit?
    private var parakeet: AsrManager?
    private var loadedIdentity: String?
    public init() {}

    public func unload() async {
        whisper = nil
        await parakeet?.cleanup()
        parakeet = nil
        loadedIdentity = nil
    }

    public func run(_ request: NativeRequest) async throws -> NativeResult {
        try Task.checkCancellation()
        let clock = ContinuousClock()
        let verifyStart = clock.now
        func checkDeadline() throws {
            try Task.checkCancellation()
            guard Measurements.seconds(verifyStart.duration(to: clock.now)) <= Double(request.settings.timeoutSeconds) else {
                throw LabError.invalid("Native job deadline exceeded; output was rejected")
            }
        }
        guard request.settings.timeoutSeconds > 0 else { throw LabError.invalid("Job deadline must be positive") }
        if request.model.runtime == "fluidaudio" && request.settings.languageMode != "auto" {
            throw LabError.invalid("FluidAudio batch adapter currently supports automatic language only")
        }
        let root = URL(fileURLWithPath: request.modelRoot, isDirectory: true)
        try AssetIntegrity.verify(request.model, root: root)
        guard try AssetIntegrity.hash(URL(fileURLWithPath: request.audio)) == request.audioSha256 else {
            throw LabError.invalid("Audio input checksum mismatch")
        }
        let verification = Measurements.seconds(verifyStart.duration(to: clock.now))
        let version: String
        switch request.model.runtime {
        case "whisperkit": version = "WhisperKit/9f99b5cb6a907730543823ad271b82532782a899"
        case "fluidaudio": version = "FluidAudio/2d6c42ca5f3accc0faf9fee9e0fff5b9b2cf6042"
        default: throw LabError.invalid("Unsupported native adapter; Qwen requires a separately validated architecture runtime")
        }
        guard version == request.model.runtimeVersion else { throw LabError.invalid("Native runtime revision differs from the manifest") }
        guard request.settings.temperature == 0 else { throw LabError.invalid("Native adapters currently support greedy decoding only") }
        let before = await Measurements.conditions()
        let identity = request.model.id + "@" + request.model.revision
        let reused = loadedIdentity == identity
        if !reused { await unload() }
        try checkDeadline()
        let loadStart = clock.now
        if !reused {
            if request.model.runtime == "whisperkit" {
                for file in ["tokenizer.json", "tokenizer_config.json"] {
                    guard request.model.files.contains(where: { $0.path == file }) else {
                        throw LabError.invalid("WhisperKit needs locally staged and hashed tokenizer.json and tokenizer_config.json")
                    }
                }
                let units: MLComputeUnits
                switch request.model.nativeOptions?.computeUnits ?? "cpuAndNeuralEngine" {
                case "cpuOnly": units = .cpuOnly
                case "cpuAndGPU": units = .cpuAndGPU
                case "all": units = .all
                case "cpuAndNeuralEngine": units = .cpuAndNeuralEngine
                default: throw LabError.invalid("Unknown Core ML compute-unit configuration")
                }
                // Tokenizer files must be staged locally too. No model download or prewarm during load timing.
                whisper = try await WhisperKit(modelFolder: root.path, tokenizerFolder: root,
                    computeOptions: ModelComputeOptions(melCompute: .cpuAndGPU, audioEncoderCompute: units, textDecoderCompute: units),
                    verbose: false, prewarm: false, load: true, download: false)
            } else {
                guard request.settings.languageMode == "auto" else {
                    throw LabError.invalid("FluidAudio batch adapter currently supports automatic language only")
                }
                let units: MLComputeUnits
                switch request.model.nativeOptions?.computeUnits ?? "cpuAndNeuralEngine" {
                case "cpuOnly": units = .cpuOnly
                case "cpuAndGPU": units = .cpuAndGPU
                case "all": units = .all
                case "cpuAndNeuralEngine": units = .cpuAndNeuralEngine
                default: throw LabError.invalid("Unknown Core ML compute-unit configuration")
                }
                let precisionName = request.model.nativeOptions?.encoderPrecision ?? "int8-v2"
                guard let precision = ParakeetEncoderPrecision(rawValue: precisionName) else {
                    throw LabError.invalid("Unsupported Parakeet encoder precision")
                }
                let modelVersion: AsrModelVersion = request.model.family == "Parakeet Ultra" ? .ultra : .v3
                // loadLocal is deliberately used: load/downloadAndLoad may repair by downloading.
                let models = try AsrModels.loadLocal(from: root, version: modelVersion,
                    encoderPrecision: precision, encoderComputeUnits: units)
                let manager = AsrManager()
                try await manager.loadModels(models)
                parakeet = manager
            }
            loadedIdentity = identity
        }
        let load = Measurements.seconds(loadStart.duration(to: clock.now))
        try checkDeadline()
        let warmupStart = clock.now
        for _ in 0..<request.settings.warmups {
            try Task.checkCancellation()
            _ = try await transcribe(request)
            try checkDeadline()
        }
        let warmup = Measurements.seconds(warmupStart.duration(to: clock.now))
        try Task.checkCancellation()
        let inferenceStart = clock.now
        let text = try await transcribe(request)
        try checkDeadline()
        let inference = Measurements.seconds(inferenceStart.duration(to: clock.now))
        let after = await Measurements.conditions()
        try checkDeadline()
        return NativeResult(id: UUID().uuidString, modelId: request.model.id, modelRevision: request.model.revision,
            audioSha256: request.audioSha256, text: text, loadSeconds: load,
            inferenceSeconds: inference, warmupSeconds: warmup, verificationSeconds: verification,
            runtimeVersion: version, loadingCondition: reused ? "reused-loaded-engine" : "new-engine-os-cache-uncontrolled",
            streamingMode: "batch", deviceConditionsBefore: before, deviceConditionsAfter: after,
            memoryObservationBytes: Measurements.residentMemory(), energyJoules: nil, firstPartialSeconds: nil)
    }

    private func transcribe(_ request: NativeRequest) async throws -> String {
        if let whisper {
            let forced = request.settings.languageMode == "forced"
            if forced && (request.language.contains("+") || request.language == "mixed") {
                throw LabError.invalid("Cannot force a single language for a mixed-language recording")
            }
            var options = DecodingOptions()
            options.task = .transcribe
            options.language = forced ? request.language : nil
            options.detectLanguage = !forced
            options.skipSpecialTokens = true
            options.concurrentWorkerCount = 1
            options.topK = 1
            options.temperature = 0
            options.temperatureFallbackCount = 0
            options.sampleLength = min(request.settings.maxNewTokens, 448)
            let results = try await whisper.transcribe(audioPath: request.audio, decodeOptions: options)
            return results.map(\.text).joined(separator: " ")
        }
        if let parakeet {
            var decoder = try TdtDecoderState()
            let result = try await parakeet.transcribe(URL(fileURLWithPath: request.audio), decoderState: &decoder)
            return result.text
        }
        throw LabError.invalid("No model is loaded")
    }
}
