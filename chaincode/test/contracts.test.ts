import { expect } from 'chai';
import { DecisionLedgerContract } from '../src/decision_ledger';
import { ModelRegistryContract } from '../src/model_registry';
import { ConsentRegistryContract } from '../src/consent_registry';

describe('Smart Contracts Unit Tests', () => {
    let mockContext: any;
    let mockState: Map<string, Buffer>;

    beforeEach(() => {
        mockState = new Map();
        mockContext = {
            clientIdentity: {
                getMSPID: () => 'Org1MSP',
            },
            stub: {
                createCompositeKey: (type: string, attributes: string[]) => `${type}:${attributes.join(':')}`,
                getState: async (key: string) => mockState.get(key) || Buffer.alloc(0),
                putState: async (key: string, value: Buffer) => { mockState.set(key, value); },
                getTxTimestamp: () => ({
                    seconds: { toNumber: () => 1774000000 },
                    nanos: 0,
                }),
            },
        };
    });

    describe('DecisionLedgerContract', () => {
        it('should record a valid decision and reject duplicates with mismatched hash', async () => {
            const contract = new DecisionLedgerContract();
            const sessionId = 'sess-cc-001';
            const hash = 'a'.repeat(64);
            const modelHash = 'b'.repeat(64);

            const resStr = await contract.RecordDecision(
                mockContext,
                sessionId,
                hash,
                'BLOCK',
                'CRITICAL',
                '0.2.0:123456',
                modelHash,
                '2026-09-18T18:00:00Z'
            );
            const res = JSON.parse(resStr);
            expect(res.sessionId).to.equal(sessionId);
            expect(res.decisionHash).to.equal(hash);

            // Re-submitting with different hash must be rejected
            try {
                await contract.RecordDecision(
                    mockContext,
                    sessionId,
                    'c'.repeat(64),
                    'BLOCK',
                    'CRITICAL',
                    '0.2.0:123456',
                    modelHash,
                    '2026-09-18T18:00:00Z'
                );
                expect.fail('Should have rejected overwrite');
            } catch (err: any) {
                expect(err.message).to.include('Decision overwrite rejected');
            }
        });

        it('should verify decision hash correctly', async () => {
            const contract = new DecisionLedgerContract();
            const sessionId = 'sess-cc-002';
            const hash = 'f'.repeat(64);

            await contract.RecordDecision(
                mockContext,
                sessionId,
                hash,
                'ALLOW',
                'LOW',
                '0.2.0:123456',
                '0'.repeat(64),
                '2026-09-18T18:00:00Z'
            );

            // Matching hash
            const matchRes = JSON.parse(await contract.VerifyDecision(mockContext, sessionId, hash));
            expect(matchRes.verified).to.be.true;

            // Mismatched hash
            const mismatchRes = JSON.parse(await contract.VerifyDecision(mockContext, sessionId, '0'.repeat(64)));
            expect(mismatchRes.verified).to.be.false;
            expect(mismatchRes.mismatchReason).to.include('Hash mismatch');
        });
    });

    describe('ModelRegistryContract (Two-Step Governance)', () => {
        it('should allow Org1 to propose and Org2 to approve a model', async () => {
            const contract = new ModelRegistryContract();
            const modelHash = '1'.repeat(64);

            // 1. Org1 Proposes
            mockContext.clientIdentity.getMSPID = () => 'Org1MSP';
            const propStr = await contract.ProposeModel(mockContext, 'aasist', 'v1.0', modelHash);
            expect(JSON.parse(propStr).status).to.equal('PROPOSED');

            // 2. Org2 Approves
            mockContext.clientIdentity.getMSPID = () => 'Org2MSP';
            const appStr = await contract.ApproveModel(mockContext, 'aasist', 'v1.0', modelHash);
            const app = JSON.parse(appStr);
            expect(app.status).to.equal('ACTIVE');
            expect(app.approvedByMsp).to.equal('Org2MSP');
        });

        it('should reject approval if auditor hash does not match proposed hash', async () => {
            const contract = new ModelRegistryContract();
            mockContext.clientIdentity.getMSPID = () => 'Org1MSP';
            await contract.ProposeRules(mockContext, '0.2.0:abc', 'a'.repeat(64));

            mockContext.clientIdentity.getMSPID = () => 'Org2MSP';
            try {
                await contract.ApproveRules(mockContext, '0.2.0:abc', 'b'.repeat(64));
                expect.fail('Should have failed on hash mismatch');
            } catch (err: any) {
                expect(err.message).to.include('auditor hash');
            }
        });
    });

    describe('ConsentRegistryContract', () => {
        it('should record consent and revoke it with a tombstone timestamp', async () => {
            const contract = new ConsentRegistryContract();
            const subjectRef = 'e'.repeat(64);
            const consentHash = 'd'.repeat(64);

            const rec = JSON.parse(await contract.RecordConsent(mockContext, subjectRef, consentHash));
            expect(rec.is_revoked).to.be.false;

            const revoked = JSON.parse(await contract.RevokeConsent(mockContext, subjectRef));
            expect(revoked.is_revoked).to.be.true;
            expect(revoked.revokedAt).to.be.a('string');
        });
    });
});
