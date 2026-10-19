import Foundation
import Darwin
#if os(iOS)
import UIKit
#endif

public enum Measurements {
    public static func seconds(_ duration: Duration) -> Double {
        let components = duration.components
        return Double(components.seconds) + Double(components.attoseconds) / 1e18
    }
    public static func residentMemory() -> UInt64? {
        var info = mach_task_basic_info()
        var count = mach_msg_type_number_t(MemoryLayout<mach_task_basic_info>.size / MemoryLayout<integer_t>.size)
        let status = withUnsafeMutablePointer(to: &info) { pointer in
            pointer.withMemoryRebound(to: integer_t.self, capacity: Int(count)) {
                task_info(mach_task_self_, task_flavor_t(MACH_TASK_BASIC_INFO), $0, &count)
            }
        }
        return status == KERN_SUCCESS ? UInt64(info.resident_size) : nil
    }
    @MainActor public static func conditions() -> DeviceConditions {
        var system = utsname(); uname(&system)
        let machineCapacity = MemoryLayout.size(ofValue: system.machine)
        let hardware = withUnsafePointer(to: &system.machine) { pointer in
            pointer.withMemoryRebound(to: CChar.self, capacity: machineCapacity) { String(cString: $0) }
        }
        let process = ProcessInfo.processInfo
        let thermal: String
        switch process.thermalState {
        case .nominal: thermal = "nominal"
        case .fair: thermal = "fair"
        case .serious: thermal = "serious"
        case .critical: thermal = "critical"
        @unknown default: thermal = "unknown"
        }
        var battery: Float? = nil; var charging: String? = nil; var brightness: Double? = nil; var orientation: String? = nil
        #if os(iOS)
        UIDevice.current.isBatteryMonitoringEnabled = true
        if UIDevice.current.batteryLevel >= 0 { battery = UIDevice.current.batteryLevel }
        switch UIDevice.current.batteryState {
        case .charging: charging = "charging"
        case .full: charging = "full"
        case .unplugged: charging = "unplugged"
        default: charging = "unknown"
        }
        brightness = Double(UIScreen.main.brightness)
        orientation = String(describing: UIDevice.current.orientation)
        #endif
        return DeviceConditions(hardwareIdentifier: hardware, osVersion: process.operatingSystemVersionString,
            thermalState: thermal, lowPowerMode: process.isLowPowerModeEnabled,
            physicalMemoryBytes: process.physicalMemory, residentMemoryBytes: residentMemory(),
            batteryLevel: battery, chargingState: charging, capturedAt: ISO8601DateFormatter().string(from: Date()),
            appBuild: Bundle.main.infoDictionary?["CFBundleVersion"] as? String ?? "development",
            displayBrightness: brightness, orientation: orientation)
    }
}
