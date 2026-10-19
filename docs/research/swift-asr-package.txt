// swift-tools-version: 6.2

import PackageDescription

let package = Package(
    name: "mlx-swift-asr",
    platforms: [
        .macOS(.v15),
    ],
    products: [
        .library(name: "MLXASR", targets: ["MLXASR"]),
    ],
    dependencies: [
        .package(url: "https://github.com/ml-explore/mlx-swift", branch: "main"),
        .package(url: "https://github.com/ml-explore/mlx-swift-lm", branch: "main"),
        .package(url: "https://github.com/huggingface/swift-transformers", from: "1.1.6"),
    ],
    targets: [
        .target(
            name: "MLXASR",
            dependencies: [
                .product(name: "MLX", package: "mlx-swift"),
                .product(name: "MLXNN", package: "mlx-swift"),
                .product(name: "MLXRandom", package: "mlx-swift"),
                .product(name: "MLXFast", package: "mlx-swift"),
                .product(name: "MLXLMCommon", package: "mlx-swift-lm"),
                .product(name: "Tokenizers", package: "swift-transformers"),
            ]
        ),
        .testTarget(
            name: "MLXASRTests",
            dependencies: ["MLXASR"],
            resources: [
                .copy("Resources"),
            ]
        ),
    ]
)
