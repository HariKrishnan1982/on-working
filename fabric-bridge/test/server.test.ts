import { expect } from 'chai';
import request from 'supertest';
import * as fs from 'fs';
import * as path from 'path';

process.env.VFD_FABRIC_BRIDGE_API_KEY = 'test-bridge-key-12345';
import app from '../src/server';

describe('Fabric Bridge REST API Tests', () => {
    const validKey = 'test-bridge-key-12345';

    it('should reject requests without X-Bridge-API-Key with 401', async () => {
        const res = await request(app).get('/api/v1/decisions/sess-001');
        expect(res.status).to.equal(401);
    });

    it('should allow public access to /health', async () => {
        const res = await request(app).get('/health');
        expect(res.status).to.equal(200);
        expect(res.body.status).to.equal('healthy');
    });

    it('should match hashes in test_vectors/decision_hash_vectors.json', async () => {
        const vectorsPath = path.resolve(__dirname, '../../test_vectors/decision_hash_vectors.json');
        const data = JSON.parse(fs.readFileSync(vectorsPath, 'utf8'));

        for (const vec of data.vectors) {
            if (vec.payload) {
                // Post decision to bridge
                const postRes = await request(app)
                    .post('/api/v1/decisions')
                    .set('X-Bridge-API-Key', validKey)
                    .send({
                        sessionId: vec.payload.session_id,
                        decisionHash: vec.expected_sha256,
                        action: vec.payload.action,
                        riskLevel: vec.payload.risk_level,
                        rulesVersion: vec.payload.rules_version,
                        modelVersionsHash: vec.payload.model_versions_hash,
                    });
                expect([200, 201]).to.include(postRes.status);

                // Verify decision
                const verifyRes = await request(app)
                    .post('/api/v1/decisions/verify')
                    .set('X-Bridge-API-Key', validKey)
                    .send({
                        sessionId: vec.payload.session_id,
                        recomputedHash: vec.expected_sha256,
                    });
                expect(verifyRes.body.verified).to.be.true;
            }
        }
    });

    it('should support two-step model governance (Propose and Approve)', async () => {
        // 1. Propose
        const propRes = await request(app)
            .post('/api/v1/models/propose')
            .set('X-Bridge-API-Key', validKey)
            .send({
                name: 'aasist',
                version: 'v0.5',
                artefactSha256: '9'.repeat(64),
            });
        expect(propRes.status).to.equal(201);
        expect(propRes.body.status).to.equal('PROPOSED');

        // 2. Approve
        const appRes = await request(app)
            .post('/api/v1/models/approve')
            .set('X-Bridge-API-Key', validKey)
            .send({
                name: 'aasist',
                version: 'v0.5',
                artefactSha256: '9'.repeat(64),
            });
        expect(appRes.status).to.equal(200);
        expect(appRes.body.status).to.equal('ACTIVE');
    });

    it('should support consent recording and revocation with tombstone', async () => {
        const subjectRef = 'a'.repeat(64);
        const consentHash = 'b'.repeat(64);

        // Record
        const recRes = await request(app)
            .post('/api/v1/consent')
            .set('X-Bridge-API-Key', validKey)
            .send({ subjectRef, consentHash });
        expect(recRes.status).to.equal(201);
        expect(recRes.body.is_revoked).to.be.false;

        // Revoke
        const revRes = await request(app)
            .post('/api/v1/consent/revoke')
            .set('X-Bridge-API-Key', validKey)
            .send({ subjectRef });
        expect(revRes.status).to.equal(200);
        expect(revRes.body.is_revoked).to.be.true;
        expect(revRes.body.revokedAt).to.be.a('string');
    });
});
