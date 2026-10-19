import Foundation

public enum LabJSON {
    public static var decoder: JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }
    public static var encoder: JSONEncoder {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        encoder.outputFormatting = [.sortedKeys]
        return encoder
    }
}

public struct ModelAsset: Codable, Sendable {
    public let path: String
    public let sha256: String
}

public struct NativeOptions: Codable, Sendable {
    public var computeUnits: String = "cpuAndNeuralEngine"
    public var encoderPrecision: String = "int8-v2"
    public init() {}
}

public struct ModelManifest: Codable, Identifiable, Sendable {
    public let id: String
    public let family: String
    public let variant: String
    public let repository: String
    public let revision: String
    public let license: String
    public let runtime: String
    public let runtimeVersion: String
    public let files: [ModelAsset]
    public let languages: [String]
    public var nativeOptions: NativeOptions?
}

public struct RunSettings: Codable, Sendable {
    public var languageMode: String
    public var warmups: Int
    public var temperature: Double
    public var maxNewTokens: Int
    public var timeoutSeconds: Int
    public init(languageMode: String = "auto", warmups: Int = 0, temperature: Double = 0, maxNewTokens: Int = 1024, timeoutSeconds: Int = 1800) {
        self.languageMode = languageMode; self.warmups = warmups
        self.temperature = temperature; self.maxNewTokens = maxNewTokens
        self.timeoutSeconds = timeoutSeconds
    }
}

public struct NativeRequest: Codable, Sendable {
    public let audio: String
    public let audioSha256: String
    public let modelRoot: String
    public let model: ModelManifest
    public let settings: RunSettings
    public let language: String
    public init(audio: String, audioSha256: String, modelRoot: String, model: ModelManifest, settings: RunSettings, language: String) {
        self.audio = audio; self.audioSha256 = audioSha256; self.modelRoot = modelRoot
        self.model = model; self.settings = settings; self.language = language
    }
}

public struct DeviceConditions: Codable, Sendable {
    public let hardwareIdentifier: String
    public let osVersion: String
    public let thermalState: String
    public let lowPowerMode: Bool
    public let physicalMemoryBytes: UInt64
    public let residentMemoryBytes: UInt64?
    public let batteryLevel: Float?
    public let chargingState: String?
    public let capturedAt: String
    public let appBuild: String
    public let displayBrightness: Double?
    public let orientation: String?
}

public struct NativeResult: Codable, Sendable, Identifiable {
    public var id: String
    public let modelId: String
    public let modelRevision: String
    public let audioSha256: String
    public let text: String
    public let loadSeconds: Double
    public let inferenceSeconds: Double
    public let warmupSeconds: Double
    public let verificationSeconds: Double
    public let runtimeVersion: String
    public let loadingCondition: String
    public let streamingMode: String
    public let deviceConditionsBefore: DeviceConditions
    public let deviceConditionsAfter: DeviceConditions
    public let memoryObservationBytes: UInt64?
    public let energyJoules: Double?
    public let firstPartialSeconds: Double?
}

public enum LabError: LocalizedError {
    case invalid(String)
    public var errorDescription: String? { if case .invalid(let message) = self { return message }; return nil }
}
