import CryptoKit
import Foundation

public enum AssetIntegrity {
    public static func hash(_ url: URL) throws -> String {
        let handle = try FileHandle(forReadingFrom: url)
        defer { try? handle.close() }
        var hasher = SHA256()
        while let data = try handle.read(upToCount: 1024 * 1024), !data.isEmpty { hasher.update(data: data) }
        return hasher.finalize().map { String(format: "%02x", $0) }.joined()
    }

    public static func path(_ relative: String, inside root: URL) throws -> URL {
        guard !relative.hasPrefix("/"), !relative.split(separator: "/").contains(".."), !relative.isEmpty else {
            throw LabError.invalid("Unsafe asset path")
        }
        let url = root.appendingPathComponent(relative).resolvingSymlinksInPath().standardizedFileURL
        let prefix = root.resolvingSymlinksInPath().standardizedFileURL.path + "/"
        guard url.path.hasPrefix(prefix) else { throw LabError.invalid("Asset escapes its cache directory") }
        return url
    }

    public static func verify(_ manifest: ModelManifest, root: URL) throws {
        guard !manifest.files.isEmpty else { throw LabError.invalid("Checkpoint has no hash manifest") }
        for asset in manifest.files {
            let url = try path(asset.path, inside: root)
            guard try hash(url) == asset.sha256 else { throw LabError.invalid("Checksum mismatch: \(asset.path)") }
        }
    }
}
