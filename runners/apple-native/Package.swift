// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "STTNative",
    platforms: [.iOS(.v17), .macOS(.v14)],
    products: [
        .library(name: "STTNative", targets: ["STTNative"]),
        .executable(name: "stt-native", targets: ["STTNativeCLI"])
    ],
    dependencies: [
        .package(url: "https://github.com/argmaxinc/WhisperKit.git", revision: "9f99b5cb6a907730543823ad271b82532782a899"),
        .package(url: "https://github.com/FluidInference/FluidAudio.git", revision: "2d6c42ca5f3accc0faf9fee9e0fff5b9b2cf6042")
    ],
    targets: [
        .target(name: "STTNative", dependencies: [
            .product(name: "WhisperKit", package: "WhisperKit"),
            .product(name: "FluidAudio", package: "FluidAudio")
        ]),
        .executableTarget(name: "STTNativeCLI", dependencies: ["STTNative"]),
        .testTarget(name: "STTNativeTests", dependencies: ["STTNative"])
    ],
    swiftLanguageModes: [.v5]
)
