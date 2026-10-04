import Foundation
import Vision
import ImageIO

guard CommandLine.arguments.count == 2 else {
    fatalError("Expected screenshot path")
}

let url = URL(fileURLWithPath: CommandLine.arguments[1])
let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.recognitionLanguages = ["en-US"]
request.usesLanguageCorrection = false

let handler = VNImageRequestHandler(url: url, options: [:])
try handler.perform([request])

let rows: [[String: Any]] = (request.results ?? []).compactMap { observation in
    guard let candidate = observation.topCandidates(1).first else {
        return nil
    }
    let box = observation.boundingBox
    return [
        "text": candidate.string,
        "confidence": Double(candidate.confidence),
        "x": Double(box.midX),
        // Vision uses bottom-left origin; Android uses top-left.
        "y": Double(1.0 - box.midY),
        "x1": Double(box.minX),
        "y1": Double(1.0 - box.maxY),
        "x2": Double(box.maxX),
        "y2": Double(1.0 - box.minY)
    ]
}

let data = try JSONSerialization.data(withJSONObject: rows)
FileHandle.standardOutput.write(data)
