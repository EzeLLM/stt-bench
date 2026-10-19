import SwiftUI
import STTNative

@main struct STTLabApp: App {
    @StateObject private var lab = LabStore()
    var body: some Scene { WindowGroup { LabView().environmentObject(lab).tint(.teal) } }
}

struct LabView: View {
    @EnvironmentObject var lab: LabStore
    @State private var pairing = false
    @State private var token = ""
    var body: some View {
        TabView {
            NavigationStack {
                List {
                    Section {
                        Label("STT Benchmark Lab", systemImage: "waveform").font(.headline)
                        Text("Private recordings. Local models. Measured evidence.").font(.subheadline).foregroundStyle(.secondary)
                    }
                    Section("Coordinator") {
                        Text(lab.coordinator.isEmpty ? "Not paired" : lab.coordinator).font(.caption).textSelection(.enabled)
                        Button("Pair with Mac") { pairing = true }.disabled(lab.isBusy)
                        Text("Connection is checked on requests. A saved pairing does not imply the Mac is reachable.").font(.caption).foregroundStyle(.secondary)
                    }
                    Section("Device observations") {
                        if let c = lab.conditions {
                            LabeledContent("Device", value: c.hardwareIdentifier)
                            LabeledContent("OS", value: c.osVersion)
                            LabeledContent("Thermal state", value: c.thermalState)
                            LabeledContent("Low Power Mode", value: c.lowPowerMode ? "On" : "Off")
                            LabeledContent("Physical memory", value: ByteCountFormatter.string(fromByteCount: Int64(c.physicalMemoryBytes), countStyle: .memory))
                            if let memory = c.residentMemoryBytes { LabeledContent("App resident memory", value: ByteCountFormatter.string(fromByteCount: Int64(memory), countStyle: .memory)) }
                        }
                        Button("Refresh observations") { Task { await lab.observe() } }
                    }
                    Section("Status") { StatusView() }
                    Section { Text("Experimental native integration. Physical-device compatibility and reference parity must be established for each checkpoint. No remote inference endpoint exists.").font(.caption).foregroundStyle(.secondary) }
                }.navigationTitle("Device home")
            }.tabItem { Label("Home", systemImage: "iphone") }
            ModelsView().tabItem { Label("Models", systemImage: "square.stack.3d.up") }
            BatchView().tabItem { Label("Batch", systemImage: "play.rectangle") }
            DictationView().tabItem { Label("Microphone", systemImage: "mic") }
            ResultsView().tabItem { Label("Results", systemImage: "chart.xyaxis.line") }
        }
        .sheet(isPresented: $pairing) {
            NavigationStack { Form {
                TextField("http://Mac-LAN-IP:8000", text: $lab.coordinator).textInputAutocapitalization(.never).autocorrectionDisabled().keyboardType(.URL)
                SecureField("Pairing token from desktop", text: $token).textInputAutocapitalization(.never)
                Button("Pair securely on trusted LAN") { lab.operate { try await lab.pair(token: token); token = ""; pairing = false } }.disabled(token.isEmpty || lab.isBusy)
                Text("HTTP is only appropriate on a trusted private LAN. Use HTTPS on untrusted networks. Device credentials are stored in this iPhone's Keychain.").font(.caption)
                StatusView()
            }.navigationTitle("Pair with Mac").toolbar { Button("Close") { pairing = false; token = "" } } }
        }
    }
}

struct StatusView: View {
    @EnvironmentObject var lab: LabStore
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(lab.phase).font(.subheadline)
            if lab.isBusy { ProgressView(); Button("Cancel", role: .destructive) { lab.cancel() } }
            if !lab.error.isEmpty { Text(lab.error).font(.caption).foregroundStyle(.red).textSelection(.enabled) }
        }
    }
}

struct ModelsView: View {
    @EnvironmentObject var lab: LabStore
    var body: some View {
        NavigationStack { List {
            Section { Button("Refresh available manifests from Mac") { lab.operate { try await lab.refreshModels() } }.disabled(lab.isBusy) }
            if lab.models.isEmpty { Section { Text("No registered native manifests on the coordinator. Stage and register exact WhisperKit or FluidAudio assets on your Mac first.").foregroundStyle(.secondary) } }
            ForEach(lab.models) { model in Section {
                Text(model.family).font(.headline)
                Text(model.variant).font(.subheadline)
                LabeledContent("Backend", value: model.runtime)
                LabeledContent("Revision", value: String(model.revision.prefix(12)))
                LabeledContent("License", value: model.license)
                LabeledContent("Cache", value: lab.installed.contains(model.id) ? "Installed — hashes checked before execution" : "Not installed")
                if lab.installed.contains(model.id) {
                    Button(lab.selectedModelId == model.id ? "Selected" : "Select model") { lab.selectedModelId = model.id }.disabled(lab.isBusy)
                    Button("Unload model") { lab.operate { await lab.unload() } }.disabled(lab.isBusy)
                    Button("Remove cached model", role: .destructive) { lab.operate { try await lab.remove(model) } }.disabled(lab.isBusy)
                } else { Button("Download & verify all files") { lab.operate { try await lab.install(model) } }.disabled(lab.isBusy) }
            } }
            Section { StatusView(); if lab.isBusy { ProgressView(value: lab.progress) } }
        }.navigationTitle("Model cache") }
    }
}

struct BatchView: View {
    @EnvironmentObject var lab: LabStore
    @State private var repetitions = 30
    @State private var warmups = 1
    var body: some View {
        NavigationStack { List {
            Section("Offline batch") {
                Text("Configure randomized model order, repetitions and warmups in a desktop iPhone experiment, then start it. Cache all inputs before measuring.").font(.caption).foregroundStyle(.secondary)
                Button("1. Cache queued inputs over Wi-Fi") { lab.operate { try await lab.cacheJobs() } }.disabled(lab.isBusy || lab.installed.isEmpty)
                Button("2. Run cached tests locally") { lab.operate { try await lab.runCached() } }.disabled(lab.isBusy || !lab.entries.contains { ["cached","interrupted"].contains($0.state) })
                Button("3. Synchronize results") { lab.operate { try await lab.sync() } }.disabled(lab.isBusy)
                Text("You can disconnect Wi-Fi after caching. Running cached tests makes no network requests. Expired/reassigned server leases can cause a sync conflict; the local result is retained.").font(.caption).foregroundStyle(.secondary)
            }
            Section("Sustained performance") {
                Picker("Model", selection: $lab.selectedModelId) { ForEach(lab.models.filter { lab.installed.contains($0.id) }) { Text($0.family + " · " + $0.variant).tag($0.id) } }
                Stepper("Measured repetitions: \(repetitions)", value: $repetitions, in: 2...1000)
                Stepper("Warmups before first measurement: \(warmups)", value: $warmups, in: 0...20)
                Button("Run sustained local workload") { lab.operate { try await lab.sustained(repetitions: repetitions, warmups: warmups) } }.disabled(lab.isBusy || lab.selected == nil || lab.entries.isEmpty)
                Text("Uses cached owner audio and the selected loaded model. Conditions are sampled before/after every run. Repeated loading is distinguished from reusing a loaded engine. No power numbers are inferred from battery level.").font(.caption).foregroundStyle(.secondary)
            }
            Section("Execution") { StatusView() }
            Section("Local jobs") { ForEach(lab.entries) { entry in VStack(alignment: .leading) { Text(entry.state).font(.headline); Text(entry.id).font(.caption.monospaced()); if !entry.error.isEmpty { Text(entry.error).font(.caption).foregroundStyle(.red) } } } }
        }.navigationTitle("Batch & sustained") }
    }
}

struct DictationView: View {
    @EnvironmentObject var lab: LabStore
    @StateObject private var mic = Microphone()
    @State private var audio: URL?
    var body: some View {
        NavigationStack { List {
            Section {
                Label("Post-recording batch", systemImage: "waveform").font(.headline)
                Text("These adapters return a final transcript after recording stops. They do not expose native streaming partials in this app. Finalization is measured from Stop through validation, loading and inference; model inference is reported separately.").font(.caption).foregroundStyle(.secondary)
                Picker("Model", selection: $lab.selectedModelId) { ForEach(lab.models.filter { lab.installed.contains($0.id) }) { Text($0.family).tag($0.id) } }
                Button(mic.isRecording ? "Stop & transcribe locally" : "Record microphone") {
                    if mic.isRecording { mic.stop(); if let audio { lab.operate { try await lab.dictate(audio: audio, captureSeconds: mic.captureSeconds) } } }
                    else {
                        let url = lab.root.appendingPathComponent("microphone-\(UUID().uuidString).wav"); audio = url
                        Task { do { try await mic.start(to: url) } catch { lab.error = error.localizedDescription } }
                    }
                }.disabled((lab.isBusy && !mic.isRecording) || lab.selected == nil)
            }
            Section("Current output") { if let result = lab.microphoneLatest { Text(result.text.isEmpty ? "Empty transcription" : result.text).textSelection(.enabled); ResultMetrics(result: result) } else { Text("No microphone result yet.").foregroundStyle(.secondary) } }
            Section { StatusView() }
        }.navigationTitle("Microphone test") }
    }
}

struct ResultMetrics: View {
    let result: NativeResult
    var body: some View {
        LabeledContent("Checkpoint", value: result.modelId)
        LabeledContent("Revision", value: String(result.modelRevision.prefix(12)))
        LabeledContent("Load", value: String(format: "%.3f s", result.loadSeconds))
        LabeledContent("Inference", value: String(format: "%.3f s", result.inferenceSeconds))
        LabeledContent("Warmup", value: String(format: "%.3f s", result.warmupSeconds))
        LabeledContent("Loading condition", value: result.loadingCondition)
        LabeledContent("Thermal", value: result.deviceConditionsAfter.thermalState)
        LabeledContent("Energy", value: "Unavailable — external profiling required")
    }
}

struct ResultsView: View {
    @EnvironmentObject var lab: LabStore
    var body: some View {
        NavigationStack { List {
            Section("Most recent local measurement") { if let result = lab.latest { ResultMetrics(result: result) } else { Text("No inference has completed in this session.").foregroundStyle(.secondary) } }
            Section("Synchronization") {
                LabeledContent("Pending results", value: String(lab.entries.filter { $0.state == "pending-sync" }.count))
                Button("Synchronize with Mac") { lab.operate { try await lab.sync() } }.disabled(lab.isBusy)
                StatusView()
                Button("Prepare local evidence export") { lab.exportEvidence() }.disabled(lab.isBusy)
                if let url = lab.exportURL { ShareLink("Share journal including retained conflict evidence", item: url) }
            }
            Section("Persisted local history") { ForEach(lab.localHistory, id: \.0) { row in VStack(alignment: .leading) { Text(row.1); Text(row.2).font(.caption).foregroundStyle(.secondary) } } }
            Section("Condition observations this session") { ForEach(Array(lab.thermalObservations.enumerated()), id: \.offset) { _, observation in Text(observation).font(.caption.monospaced()) } }
            Section { Text("Main analysis is on the desktop. Preserve Instruments traces separately and associate them with the experiment. Short battery percentage changes are not energy measurements.").font(.caption).foregroundStyle(.secondary) }
        }.navigationTitle("Results") }
    }
}
