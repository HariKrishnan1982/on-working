import express, { Request, Response, NextFunction } from 'express';
import rateLimit from 'express-rate-limit';
import * as dotenv from 'dotenv';
// @ts-ignore
import stringify from 'json-stringify-deterministic';

dotenv.config();

const app = express();
const PORT = parseInt(process.env.VFD_FABRIC_BRIDGE_PORT || process.env.PORT || '8081', 10);
const HOST = '127.0.0.1';

// Enforce required API Key from environment (fails startup if missing)
const BRIDGE_API_KEY = process.env.VFD_FABRIC_BRIDGE_API_KEY;
if (!BRIDGE_API_KEY || BRIDGE_API_KEY.trim().length === 0) {
    console.error('FATAL: VFD_FABRIC_BRIDGE_API_KEY is not set in environment. Failing startup.');
    process.exit(1);
}

// ── Security Middleware ──────────────────────────────────────────────────────

// Limit request payload to 1MB
app.use(express.json({ limit: '1mb' }));

// Rate limiting: 200 requests per minute per IP
const limiter = rateLimit({
    windowMs: 60 * 1000,
    max: 200,
    standardHeaders: true,
    legacyHeaders: false,
    message: { error: 'Too many requests, please try again later.' },
});
app.use(limiter);

// No payload logging: log only method, sanitized path, status, and IP
app.use((req: Request, res: Response, next: NextFunction) => {
    const start = Date.now();
    res.on('finish', () => {
        const duration = Date.now() - start;
        console.log(`[ACCESS] ${req.method} ${req.path} -> ${res.statusCode} (${duration}ms) [${req.ip}]`);
    });
    next();
});

// Authentication Middleware
const authenticateApiKey = (req: Request, res: Response, next: NextFunction) => {
    const key = req.header('X-Bridge-API-Key');
    if (!key || key !== BRIDGE_API_KEY) {
        return res.status(401).json({ error: 'Unauthorized: Invalid or missing X-Bridge-API-Key' });
    }
    next();
};

// ── In-Memory State Store for Local Dev / Mock Mode ──────────────────────────

const memoryLedger = {
    decisions: new Map<string, any>(),
    decisionHistory: new Map<string, any[]>(),
    models: new Map<string, any>(),
    rules: new Map<string, any>(),
    consents: new Map<string, any>(),
};

// ── Health Endpoint (Public) ─────────────────────────────────────────────────

app.get('/health', (_req: Request, res: Response) => {
    res.json({
        status: 'healthy',
        service: 'fabric-bridge',
        mode: process.env.FABRIC_LIVE_PEER ? 'live-fabric' : 'mock-fallback',
        timestamp: new Date().toISOString(),
    });
});

// Apply authentication to all /api routes
app.use('/api', authenticateApiKey);

// ── Decision Ledger Endpoints ────────────────────────────────────────────────

app.post('/api/v1/decisions', (req: Request, res: Response) => {
    const { sessionId, decisionHash, action, riskLevel, rulesVersion, modelVersionsHash, clientTimestamp } = req.body;

    if (!sessionId || !decisionHash || !action || !riskLevel || !rulesVersion) {
        return res.status(400).json({ error: 'Missing required decision fields' });
    }

    if (memoryLedger.decisions.has(sessionId)) {
        const existing = memoryLedger.decisions.get(sessionId);
        if (existing.decisionHash === decisionHash) {
            return res.status(200).json({ status: 'ALREADY_EXISTS', record: existing });
        }
        return res.status(409).json({ error: `Decision overwrite rejected for sessionId '${sessionId}'` });
    }

    const record = {
        sessionId,
        decisionHash,
        action,
        riskLevel,
        rulesVersion,
        modelVersionsHash: modelVersionsHash || '0'.repeat(64),
        clientTimestamp: clientTimestamp || new Date().toISOString(),
        txTimestamp: new Date().toISOString(),
        recordedByMsp: 'Org1MSP',
    };

    memoryLedger.decisions.set(sessionId, record);
    const history = memoryLedger.decisionHistory.get(sessionId) || [];
    history.push({ txId: `tx-${Date.now()}`, value: record, timestamp: record.txTimestamp });
    memoryLedger.decisionHistory.set(sessionId, history);

    return res.status(201).json(record);
});

app.get('/api/v1/decisions/:sessionId', (req: Request, res: Response) => {
    const { sessionId } = req.params;
    if (!memoryLedger.decisions.has(sessionId)) {
        return res.status(404).json({ error: `Decision not found for sessionId '${sessionId}'` });
    }
    return res.json(memoryLedger.decisions.get(sessionId));
});

app.get('/api/v1/decisions/:sessionId/history', (req: Request, res: Response) => {
    const { sessionId } = req.params;
    const history = memoryLedger.decisionHistory.get(sessionId) || [];
    return res.json(history);
});

app.post('/api/v1/decisions/verify', (req: Request, res: Response) => {
    const { sessionId, recomputedHash } = req.body;
    if (!sessionId || !recomputedHash) {
        return res.status(400).json({ error: 'sessionId and recomputedHash are required' });
    }

    if (!memoryLedger.decisions.has(sessionId)) {
        return res.json({ verified: false, sessionId, recomputedHash, mismatchReason: 'Decision not found on ledger' });
    }

    const record = memoryLedger.decisions.get(sessionId);
    const verified = (record.decisionHash.toLowerCase() === recomputedHash.toLowerCase());
    return res.json({
        verified,
        sessionId,
        onChainHash: record.decisionHash,
        recomputedHash,
        mismatchReason: verified ? undefined : `Hash mismatch: on-chain='${record.decisionHash}', recomputed='${recomputedHash}'`,
    });
});

app.get('/api/v1/decisions', (req: Request, res: Response) => {
    const pageSize = parseInt(req.query.pageSize as string, 10) || 50;
    const all = Array.from(memoryLedger.decisions.values());
    return res.json({
        records: all.slice(0, pageSize),
        recordsCount: all.length,
        bookmark: '',
    });
});

// ── Model & Rules Governance Endpoints ────────────────────────────────────────

app.post('/api/v1/models/propose', (req: Request, res: Response) => {
    const { name, version, artefactSha256 } = req.body;
    const key = `${name}:${version}`;
    const entry = {
        name,
        version,
        artefactSha256: artefactSha256.toLowerCase(),
        status: 'PROPOSED',
        proposedByMsp: 'Org1MSP',
        proposedAt: new Date().toISOString(),
    };
    memoryLedger.models.set(key, entry);
    return res.status(201).json(entry);
});

app.post('/api/v1/models/approve', (req: Request, res: Response) => {
    const { name, version, artefactSha256 } = req.body;
    const key = `${name}:${version}`;
    if (!memoryLedger.models.has(key)) {
        return res.status(404).json({ error: `Model '${key}' not proposed` });
    }
    const entry = memoryLedger.models.get(key);
    if (entry.artefactSha256 !== artefactSha256.toLowerCase()) {
        return res.status(400).json({ error: 'Auditor hash mismatch' });
    }
    entry.status = 'ACTIVE';
    entry.approvedByMsp = 'Org2MSP';
    entry.approvedAt = new Date().toISOString();
    return res.json(entry);
});

app.get('/api/v1/models/:name/:version', (req: Request, res: Response) => {
    const key = `${req.params.name}:${req.params.version}`;
    if (!memoryLedger.models.has(key)) {
        return res.status(404).json({ error: `Model '${key}' not found` });
    }
    return res.json(memoryLedger.models.get(key));
});

app.post('/api/v1/rules/propose', (req: Request, res: Response) => {
    const { rulesVersion, sha256 } = req.body;
    const entry = {
        rulesVersion,
        sha256: sha256.toLowerCase(),
        status: 'PROPOSED',
        proposedByMsp: 'Org1MSP',
        proposedAt: new Date().toISOString(),
    };
    memoryLedger.rules.set(rulesVersion, entry);
    return res.status(201).json(entry);
});

app.post('/api/v1/rules/approve', (req: Request, res: Response) => {
    const { rulesVersion, sha256 } = req.body;
    if (!memoryLedger.rules.has(rulesVersion)) {
        return res.status(404).json({ error: `Rules '${rulesVersion}' not proposed` });
    }
    const entry = memoryLedger.rules.get(rulesVersion);
    if (entry.sha256 !== sha256.toLowerCase()) {
        return res.status(400).json({ error: 'Auditor hash mismatch' });
    }
    entry.status = 'ACTIVE';
    entry.approvedByMsp = 'Org2MSP';
    entry.approvedAt = new Date().toISOString();
    return res.json(entry);
});

app.get('/api/v1/rules/:version', (req: Request, res: Response) => {
    const { version } = req.params;
    if (!memoryLedger.rules.has(version)) {
        return res.status(404).json({ error: `Rules version '${version}' not found` });
    }
    return res.json(memoryLedger.rules.get(version));
});

// ── Consent Registry Endpoints ───────────────────────────────────────────────

app.post('/api/v1/consent', (req: Request, res: Response) => {
    const { subjectRef, consentHash } = req.body;
    const entry = {
        subjectRef,
        consentHash,
        is_revoked: false,
        recordedAt: new Date().toISOString(),
        recordedByMsp: 'Org1MSP',
    };
    memoryLedger.consents.set(subjectRef, entry);
    return res.status(201).json(entry);
});

app.post('/api/v1/consent/revoke', (req: Request, res: Response) => {
    const { subjectRef } = req.body;
    if (!memoryLedger.consents.has(subjectRef)) {
        return res.status(404).json({ error: `Consent record not found for subjectRef '${subjectRef}'` });
    }
    const entry = memoryLedger.consents.get(subjectRef);
    entry.is_revoked = true;
    entry.revokedAt = new Date().toISOString();
    return res.json(entry);
});

app.get('/api/v1/consent/:subjectRef', (req: Request, res: Response) => {
    const { subjectRef } = req.params;
    if (!memoryLedger.consents.has(subjectRef)) {
        return res.status(404).json({ error: `Consent record not found for subjectRef '${subjectRef}'` });
    }
    return res.json(memoryLedger.consents.get(subjectRef));
});

export default app;

if (require.main === module) {
    app.listen(PORT, HOST, () => {
        console.log(`[FABRIC-BRIDGE] REST Service listening securely on http://${HOST}:${PORT}`);
    });
}
