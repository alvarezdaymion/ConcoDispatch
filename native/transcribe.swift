// macOS 26+ SpeechAnalyzer file helper. Build with swiftc -parse-as-library.
import AVFoundation
import Foundation
import Speech

@main
struct NativeTranscribe {
    struct Failure: Error, CustomStringConvertible {
        let description: String
        init(_ message: String) { description = message }
    }

    struct Arguments {
        var locale = "en-US"
        var mode: String?
        var path: String?

        init(_ values: [String]) throws {
            let usage = Failure("Usage: transcribe [--locale ID] <audio-file> | --check | --prepare")
            var index = 0
            while index < values.count {
                let value = values[index]
                switch value {
                case "--locale":
                    index += 1
                    guard index < values.count, !values[index].hasPrefix("-"),
                          !values[index].isEmpty else { throw usage }
                    locale = values[index]
                case "--check", "--prepare":
                    guard mode == nil else { throw usage }
                    mode = value
                default:
                    guard !value.hasPrefix("-"), path == nil else { throw usage }
                    path = value
                }
                index += 1
            }
            guard (mode == nil && path != nil) || (mode != nil && path == nil)
            else { throw usage }
        }
    }

    static func main() async {
        do {
            let arguments = try Arguments(Array(CommandLine.arguments.dropFirst()))
            try await run(arguments)
        } catch {
            FileHandle.standardError.write(Data("\(error)\n".utf8))
            exit(1)
        }
    }

    static func run(_ arguments: Arguments) async throws {
        let locale = Locale(identifier: arguments.locale)
        let available = SpeechTranscriber.isAvailable
        let supported = await SpeechTranscriber.supportedLocale(equivalentTo: locale)
        var transcriber: SpeechTranscriber?
        var installed = false
        if available, let supported {
            let module = SpeechTranscriber(locale: supported, preset: .transcription)
            transcriber = module
            installed = await AssetInventory.status(forModules: [module]) == .installed
        }
        if arguments.mode == "--check" {
            try emit([
                "available": available, "assets_installed": installed,
                "locale_supported": supported != nil, "locale": arguments.locale
            ])
            return
        }
        guard available else { throw Failure("SpeechTranscriber is unavailable on this Mac") }
        guard let transcriber else {
            throw Failure("Unsupported locale: \(arguments.locale)")
        }
        if arguments.mode == "--prepare" {
            // This is the only path allowed to request an Apple asset download.
            if !installed,
               let request = try await AssetInventory.assetInstallationRequest(supporting: [transcriber]) {
                try await request.downloadAndInstall()
            }
            guard await AssetInventory.status(forModules: [transcriber]) == .installed else {
                throw Failure("Apple speech assets were not installed for \(arguments.locale)")
            }
            try emit(["available": true, "locale_supported": true,
                      "assets_installed": true, "locale": arguments.locale])
            return
        }
        let file = try AVAudioFile(forReading: URL(fileURLWithPath: arguments.path!))
        guard installed else {
            throw Failure("Speech assets are not installed for \(arguments.locale); run --prepare --locale \(arguments.locale) explicitly")
        }
        let analyzer = SpeechAnalyzer(modules: [transcriber])
        // Consume concurrently: waiting until analysis ends can stall the producer.
        async let transcript = finalText(from: transcriber)
        do {
            if let end = try await analyzer.analyzeSequence(from: file) {
                try await analyzer.finalizeAndFinish(through: end)
            } else {
                await analyzer.cancelAndFinishNow()
            }
            // Nothing reaches stdout until finalization and result consumption succeed.
            let text = try await transcript
            guard !text.isEmpty else { throw Failure("Local audio transcript is empty") }
            try emit(["text": text])
        } catch {
            await analyzer.cancelAndFinishNow()
            throw error
        }
    }

    static func finalText(from transcriber: SpeechTranscriber) async throws -> String {
        var text = ""
        for try await result in transcriber.results {
            if result.isFinal { text += String(result.text.characters) }
        }
        return text.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    static func emit(_ object: [String: Any]) throws {
        let data = try JSONSerialization.data(withJSONObject: object, options: [.sortedKeys])
        FileHandle.standardOutput.write(data + Data([10]))
    }
}
