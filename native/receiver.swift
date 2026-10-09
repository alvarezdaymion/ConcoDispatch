// Native LaunchServices identity for the local receiver's macOS file-access grant.
import AppKit
import Foundation

struct Paths {
    let runtime: URL
    let config: URL
    let state: URL

    init(_ arguments: [String]) throws {
        let usage = NSError(domain: "Usage: receiver --runtime ABSOLUTE --config ABSOLUTE --state ABSOLUTE",
                            code: 1)
        guard arguments.count == 6 else { throw usage }
        var values: [String: URL] = [:]
        for index in stride(from: 0, to: arguments.count, by: 2) {
            let key = arguments[index], value = arguments[index + 1]
            guard ["--runtime", "--config", "--state"].contains(key),
                  values[key] == nil, value.hasPrefix("/") else { throw usage }
            values[key] = URL(fileURLWithPath: value)
        }
        guard let runtime = values["--runtime"], let config = values["--config"],
              let state = values["--state"] else { throw usage }
        self.runtime = runtime
        self.config = config
        self.state = state
    }
}

final class ReceiverDelegate: NSObject, NSApplicationDelegate {
    let paths: Paths
    init(_ paths: Paths) { self.paths = paths }

    func applicationDidFinishLaunching(_ notification: Notification) {
        let paths = self.paths
        DispatchQueue.global(qos: .utility).async {
            let process = Process()
            process.executableURL = URL(fileURLWithPath: "/bin/sh")
            process.arguments = [paths.runtime.appendingPathComponent("scripts/consume.sh").path]
            process.currentDirectoryURL = paths.runtime
            var environment = ProcessInfo.processInfo.environment
            environment["HOME"] = FileManager.default.homeDirectoryForCurrentUser.path
            environment["VOICE_KANBAN_CONFIG"] = paths.config.path
            environment["VOICE_KANBAN_STATE_DIR"] = paths.state.path
            environment["PATH"] = "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"
            process.environment = environment
            var outputs: [FileHandle] = []
            do {
                for (name, isError) in [("receiver.log", false), ("receiver-error.log", true)] {
                    let file = paths.state.appendingPathComponent(name)
                    if !FileManager.default.fileExists(atPath: file.path) {
                        guard FileManager.default.createFile(atPath: file.path, contents: nil,
                                attributes: [.posixPermissions: 0o600]) else {
                            throw NSError(domain: "Cannot create receiver log", code: 1)
                        }
                    }
                    let handle = try FileHandle(forWritingTo: file)
                    try handle.seekToEnd()
                    outputs.append(handle)
                    if isError { process.standardError = handle }
                    else { process.standardOutput = handle }
                }
                try process.run()
                process.waitUntilExit()
                for handle in outputs { try? handle.close() }
                exit(process.terminationStatus)
            } catch {
                let data = Data("Receiver host failed: \(error)\n".utf8)
                if let handle = outputs.last { try? handle.write(contentsOf: data) }
                else { FileHandle.standardError.write(data) }
                for handle in outputs { try? handle.close() }
                exit(1)
            }
        }
    }
}

@main
struct ReceiverHost {
    static func main() {
        do {
            let delegate = ReceiverDelegate(try Paths(Array(CommandLine.arguments.dropFirst())))
            let application = NSApplication.shared
            application.delegate = delegate
            application.setActivationPolicy(.accessory)
            withExtendedLifetime(delegate) { application.run() }
        } catch {
            FileHandle.standardError.write(Data("\(error)\n".utf8))
            exit(1)
        }
    }
}
