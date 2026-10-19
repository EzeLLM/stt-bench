import Foundation
import SQLite3
import STTNative

/// Transactional local job/outbox persistence. Results survive Wi-Fi loss and app restart.
final class Journal {
    private var db: OpaquePointer?
    private let transient = unsafeBitCast(-1, to: sqlite3_destructor_type.self)
    init(url: URL) throws {
        guard sqlite3_open(url.path, &db) == SQLITE_OK else { throw LabError.invalid("Cannot open local experiment journal") }
        try execute("PRAGMA journal_mode=WAL")
        try execute("CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, payload TEXT NOT NULL, result TEXT, state TEXT NOT NULL, error TEXT, created_at TEXT NOT NULL)")
        try execute("CREATE TABLE IF NOT EXISTS local_runs(id TEXT PRIMARY KEY,kind TEXT NOT NULL,payload TEXT NOT NULL,created_at TEXT NOT NULL)")
        try execute("PRAGMA user_version=1")
    }
    deinit { sqlite3_close(db) }
    private func execute(_ sql: String) throws {
        guard sqlite3_exec(db, sql, nil, nil, nil) == SQLITE_OK else { throw LabError.invalid(String(cString: sqlite3_errmsg(db))) }
    }
    func store(job: DeviceJob) throws {
        let text = String(decoding: try LabJSON.encoder.encode(job), as: UTF8.self)
        try execute("BEGIN IMMEDIATE")
        do {
            for entry in try entries() where ["cached", "interrupted"].contains(entry.state) {
                let previous = try LabJSON.decoder.decode(DeviceJob.self, from: Data(entry.payload.utf8))
                if previous.id == job.id && previous.attemptId != job.attemptId {
                    try state(entry.id, state: "superseded", error: "New coordinator attempt cached; previous evidence retained")
                }
            }
            try statement("INSERT OR IGNORE INTO jobs VALUES(?,?,NULL,'cached',NULL,?)", [key(job), text, ISO8601DateFormatter().string(from: Date())])
            try execute("COMMIT")
        } catch { try? execute("ROLLBACK"); throw error }
    }
    private func key(_ job: DeviceJob) -> String { job.id + "@" + job.attemptId }
    func result(job: DeviceJob, value: NativeResult) throws {
        let text = String(decoding: try LabJSON.encoder.encode(SyncEnvelope(job: job, result: value)), as: UTF8.self)
        try statement("UPDATE jobs SET result=?,state='pending-sync',error=NULL WHERE id=?", [text, key(job)])
    }
    func state(_ jobId: String, state: String, error: String? = nil) throws {
        try statement("UPDATE jobs SET state=?,error=? WHERE id=?", [state, error ?? "", jobId])
    }
    func local(kind: String, request: NativeRequest, result: NativeResult, captureSeconds: Double?, finalizationSeconds: Double?) throws {
        struct Local: Encodable { let request: NativeRequest; let result: NativeResult; let captureSeconds: Double?; let finalizationSeconds: Double? }
        let data = try LabJSON.encoder.encode(Local(request: request, result: result, captureSeconds: captureSeconds, finalizationSeconds: finalizationSeconds))
        try statement("INSERT INTO local_runs VALUES(?,?,?,?)", [result.id, kind, String(decoding: data, as: UTF8.self), ISO8601DateFormatter().string(from: Date())])
    }
    func localHistory() throws -> [(String, String, String)] {
        var statement: OpaquePointer?
        guard sqlite3_prepare_v2(db, "SELECT id,kind,created_at FROM local_runs ORDER BY rowid DESC", -1, &statement, nil) == SQLITE_OK else { throw LabError.invalid("Cannot read local history") }
        defer { sqlite3_finalize(statement) }
        var rows = [(String,String,String)]()
        while sqlite3_step(statement) == SQLITE_ROW {
            rows.append((String(cString: sqlite3_column_text(statement,0)),String(cString: sqlite3_column_text(statement,1)),String(cString: sqlite3_column_text(statement,2))))
        }
        return rows
    }
    func export(to url: URL) throws {
        try? FileManager.default.removeItem(at: url)
        var target: OpaquePointer?
        guard sqlite3_open(url.path, &target) == SQLITE_OK else { throw LabError.invalid("Cannot create local evidence export") }
        defer { sqlite3_close(target) }
        guard let backup = sqlite3_backup_init(target, "main", db, "main") else { throw LabError.invalid("Cannot snapshot local journal") }
        let status = sqlite3_backup_step(backup, -1)
        sqlite3_backup_finish(backup)
        guard status == SQLITE_DONE else { throw LabError.invalid("Local evidence export failed") }
    }
    func entries() throws -> [Entry] {
        var statement: OpaquePointer?
        guard sqlite3_prepare_v2(db, "SELECT id,payload,result,state,error,created_at FROM jobs ORDER BY rowid DESC", -1, &statement, nil) == SQLITE_OK else { throw LabError.invalid("Cannot read journal") }
        defer { sqlite3_finalize(statement) }
        var rows = [Entry]()
        while sqlite3_step(statement) == SQLITE_ROW {
            func text(_ column: Int32) -> String { sqlite3_column_text(statement, column).map { String(cString: $0) } ?? "" }
            rows.append(Entry(id: text(0), payload: text(1), result: text(2), state: text(3), error: text(4), createdAt: text(5)))
        }
        return rows
    }
    private func statement(_ sql: String, _ values: [String]) throws {
        var statement: OpaquePointer?
        guard sqlite3_prepare_v2(db, sql, -1, &statement, nil) == SQLITE_OK else { throw LabError.invalid("Cannot prepare journal update") }
        defer { sqlite3_finalize(statement) }
        for (index, value) in values.enumerated() { sqlite3_bind_text(statement, Int32(index + 1), value, -1, transient) }
        guard sqlite3_step(statement) == SQLITE_DONE else { throw LabError.invalid("Journal update failed") }
    }
    struct Entry: Identifiable { let id: String; let payload: String; let result: String; let state: String; let error: String; let createdAt: String }
}
