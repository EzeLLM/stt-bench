import Foundation

public struct DeviceJob: Codable, Identifiable, Sendable {
    public let id: String
    public let attemptId: String
    public let experimentId: String
    public let audioUrl: String
    public let audioSha256: String
    public let duration: Double
    public let model: ModelManifest
    public let settings: RunSettings
    public let language: String
    public let repetition: Int
}

public struct PairingReceipt: Codable, Sendable {
    public let id: String
    public let token: String
}

public struct SyncEnvelope: Codable, Sendable {
    public let attemptId: String
    public let text: String
    public let loadSeconds: Double
    public let inferenceSeconds: Double
    public let runtimeVersion: String
    public let audioSha256: String
    public let modelRevision: String
    public let deviceConditions: DeviceConditions
    public let executionLocation: String
    public let measurements: NativeResult
    public init(job: DeviceJob, result: NativeResult) {
        attemptId = job.attemptId; text = result.text; loadSeconds = result.loadSeconds
        inferenceSeconds = result.inferenceSeconds; runtimeVersion = result.runtimeVersion
        audioSha256 = job.audioSha256; modelRevision = job.model.revision
        deviceConditions = result.deviceConditionsAfter; executionLocation = "device"; measurements = result
    }
}

public struct CoordinatorClient: Sendable {
    public let base: URL
    public let token: String
    public init(base: URL, token: String) throws {
        guard let host = base.host, ["http", "https"].contains(base.scheme ?? ""), !host.isEmpty,
              base.user == nil, base.password == nil, base.query == nil, base.fragment == nil else {
            throw LabError.invalid("Enter an HTTP(S) coordinator URL without credentials or a path")
        }
        self.base = base; self.token = token
    }
    private func url(_ path: String) throws -> URL {
        guard path.hasPrefix("/api/v1/device/"), let url = URL(string: path, relativeTo: base)?.absoluteURL,
              url.host == base.host, url.port == base.port, url.scheme == base.scheme else {
            throw LabError.invalid("Asset URL must stay on the paired coordinator")
        }
        return url
    }
    public func request<T: Decodable>(_ path: String, method: String = "GET", body: Data? = nil) async throws -> T {
        var request = URLRequest(url: try url(path))
        request.httpMethod = method; request.httpBody = body; request.timeoutInterval = 30
        request.setValue("Bearer " + token, forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
            throw LabError.invalid("Coordinator rejected request: " + String(decoding: data.prefix(1500), as: UTF8.self))
        }
        return try LabJSON.decoder.decode(T.self, from: data)
    }
    public func download(_ path: String, to destination: URL, sha256: String) async throws {
        var request = URLRequest(url: try url(path)); request.timeoutInterval = 600
        request.setValue("Bearer " + token, forHTTPHeaderField: "Authorization")
        let (temporary, response) = try await URLSession.shared.download(for: request)
        guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
            throw LabError.invalid("Asset download failed")
        }
        defer { try? FileManager.default.removeItem(at: temporary) }
        guard try AssetIntegrity.hash(temporary) == sha256 else { throw LabError.invalid("Downloaded asset checksum mismatch") }
        try FileManager.default.createDirectory(at: destination.deletingLastPathComponent(), withIntermediateDirectories: true)
        if FileManager.default.fileExists(atPath: destination.path) { try FileManager.default.removeItem(at: destination) }
        try FileManager.default.moveItem(at: temporary, to: destination)
    }
}
