import Foundation
import STTNative

@main struct NativeRunner {
    static func main() async throws {
        guard CommandLine.arguments.count == 2 else {
            throw LabError.invalid("Usage: stt-native /path/to/request.json")
        }
        let request = try LabJSON.decoder.decode(NativeRequest.self,
            from: Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1])))
        let engine = NativeEngine()
        let result = try await engine.run(request)
        let data = try LabJSON.encoder.encode(result)
        print("STT_RESULT=" + String(decoding: data, as: UTF8.self))
    }
}
