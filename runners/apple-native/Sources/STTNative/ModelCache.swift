import Foundation

public actor ModelCache {
    public let root: URL
    public init(root: URL) throws {
        self.root = root
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    }
    public func modelRoot(_ model: ModelManifest) throws -> URL {
        try AssetIntegrity.path(model.id + "@" + model.revision, inside: root)
    }
    public func isInstalled(_ model: ModelManifest) -> Bool {
        guard let directory = try? modelRoot(model) else { return false }
        return FileManager.default.fileExists(atPath: directory.appendingPathComponent(".complete").path)
    }
    public func install(_ model: ModelManifest, client: CoordinatorClient,
                        progress: @Sendable (Int, Int) async -> Void) async throws {
        let directory = try modelRoot(model)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        for (index, asset) in model.files.enumerated() {
            try Task.checkCancellation()
            let destination = try AssetIntegrity.path(asset.path, inside: directory)
            if (try? AssetIntegrity.hash(destination)) != asset.sha256 {
                let encoded = asset.path.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? ""
                try await client.download("/api/v1/device/models/\(model.id)/assets/\(encoded)", to: destination, sha256: asset.sha256)
            }
            await progress(index + 1, model.files.count)
        }
        try AssetIntegrity.verify(model, root: directory)
        try Data(model.revision.utf8).write(to: directory.appendingPathComponent(".complete"), options: .atomic)
    }
    public func remove(_ model: ModelManifest) throws {
        let directory = try modelRoot(model)
        if FileManager.default.fileExists(atPath: directory.path) { try FileManager.default.removeItem(at: directory) }
    }
}
