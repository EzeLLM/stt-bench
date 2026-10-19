import XCTest
@testable import STTNative

final class IntegrityTests: XCTestCase {
    func testKnownSHA256AndTraversal() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let file = directory.appendingPathComponent("test")
        try Data("abc".utf8).write(to: file)
        XCTAssertEqual(try AssetIntegrity.hash(file), "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")
        XCTAssertThrowsError(try AssetIntegrity.path("../secret", inside: directory))
    }

    func testMonotonicDurationConversion() {
        XCTAssertEqual(Measurements.seconds(.milliseconds(1250)), 1.25, accuracy: 0.000001)
    }
}
