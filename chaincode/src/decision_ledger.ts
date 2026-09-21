import { Context, Contract, Info, Returns, Transaction } from 'fabric-contract-api';
// @ts-ignore
import stringify from 'json-stringify-deterministic';

const HASH_REGEX = /^[0-9a-fA-F]{64}$/;
const VALID_ACTIONS = new Set(['ALLOW', 'FLAG', 'ESCALATE', 'BLOCK']);
const VALID_RISK_LEVELS = new Set(['LOW', 'MEDIUM', 'HIGH', 'CRITICAL']);
const AUTHORIZED_MSPS = new Set(['Org1MSP', 'Org2MSP']);

export interface DecisionRecord {
    sessionId: string;
    decisionHash: string;
    action: string;
    riskLevel: string;
    rulesVersion: string;
    modelVersionsHash: string;
    clientTimestamp: string;
    txTimestamp: string;
    recordedByMsp: string;
}

export interface VerificationResult {
    verified: boolean;
    sessionId: string;
    onChainHash?: string;
    recomputedHash: string;
    mismatchReason?: string;
}

@Info({ title: 'DecisionLedgerContract', description: 'Immutable Smart Contract for Voice Fraud Decisions' })
export class DecisionLedgerContract extends Contract {
    constructor() {
        super('DecisionLedger');
    }

    private checkAccess(ctx: Context): string {
        const mspId = ctx.clientIdentity.getMSPID();
        if (!AUTHORIZED_MSPS.has(mspId)) {
            throw new Error(`Unauthorized MSP: '${mspId}' is not permitted to execute this transaction.`);
        }
        return mspId;
    }

    private formatTxTimestamp(ctx: Context): string {
        const ts = ctx.stub.getTxTimestamp();
        const millis = (ts.seconds.toNumber() * 1000) + Math.round(ts.nanos / 1000000);
        return new Date(millis).toISOString();
    }

    @Transaction(true)
    public async RecordDecision(
        ctx: Context,
        sessionId: string,
        decisionHash: string,
        action: string,
        riskLevel: string,
        rulesVersion: string,
        modelVersionsHash: string,
        clientTimestamp: string
    ): Promise<string> {
        const mspId = this.checkAccess(ctx);

        if (!sessionId || sessionId.trim().length === 0) {
            throw new Error('sessionId must be a non-empty string.');
        }
        if (!HASH_REGEX.test(decisionHash)) {
            throw new Error(`Invalid decisionHash: '${decisionHash}' must be a 64-character hexadecimal SHA-256 string.`);
        }
        if (!HASH_REGEX.test(modelVersionsHash)) {
            throw new Error(`Invalid modelVersionsHash: '${modelVersionsHash}' must be a 64-character hexadecimal string.`);
        }
        if (!VALID_ACTIONS.has(action)) {
            throw new Error(`Invalid action '${action}'. Must be one of: ${Array.from(VALID_ACTIONS).join(', ')}`);
        }
        if (!VALID_RISK_LEVELS.has(riskLevel)) {
            throw new Error(`Invalid riskLevel '${riskLevel}'. Must be one of: ${Array.from(VALID_RISK_LEVELS).join(', ')}`);
        }

        const compositeKey = ctx.stub.createCompositeKey('Decision', [sessionId]);
        const existing = await ctx.stub.getState(compositeKey);

        if (existing && existing.length > 0) {
            const existingRecord: DecisionRecord = JSON.parse(existing.toString());
            if (existingRecord.decisionHash === decisionHash) {
                // Idempotent write: same sessionId and matching hash
                return stringify({ status: 'ALREADY_EXISTS', message: 'Decision already recorded with matching hash', record: existingRecord });
            }
            throw new Error(`Decision overwrite rejected for sessionId '${sessionId}'. Existing hash '${existingRecord.decisionHash}' differs from incoming hash '${decisionHash}'.`);
        }

        const txTimestamp = this.formatTxTimestamp(ctx);

        const record: DecisionRecord = {
            sessionId,
            decisionHash,
            action,
            riskLevel,
            rulesVersion,
            modelVersionsHash,
            clientTimestamp,
            txTimestamp,
            recordedByMsp: mspId,
        };

        await ctx.stub.putState(compositeKey, Buffer.from(stringify(record)));
        return stringify(record);
    }

    @Transaction(false)
    @Returns('string')
    public async GetDecision(ctx: Context, sessionId: string): Promise<string> {
        this.checkAccess(ctx);
        const compositeKey = ctx.stub.createCompositeKey('Decision', [sessionId]);
        const stateBytes = await ctx.stub.getState(compositeKey);
        if (!stateBytes || stateBytes.length === 0) {
            throw new Error(`Decision not found for sessionId '${sessionId}'`);
        }
        return stateBytes.toString();
    }

    @Transaction(false)
    @Returns('string')
    public async VerifyDecision(ctx: Context, sessionId: string, recomputedHash: string): Promise<string> {
        this.checkAccess(ctx);
        const compositeKey = ctx.stub.createCompositeKey('Decision', [sessionId]);
        const stateBytes = await ctx.stub.getState(compositeKey);

        if (!stateBytes || stateBytes.length === 0) {
            const res: VerificationResult = {
                verified: false,
                sessionId,
                recomputedHash,
                mismatchReason: 'Decision record not found on ledger',
            };
            return stringify(res);
        }

        const record: DecisionRecord = JSON.parse(stateBytes.toString());
        const isMatch = (record.decisionHash.toLowerCase() === recomputedHash.toLowerCase());

        const res: VerificationResult = {
            verified: isMatch,
            sessionId,
            onChainHash: record.decisionHash,
            recomputedHash,
            mismatchReason: isMatch ? undefined : `Hash mismatch: on-chain='${record.decisionHash}', recomputed='${recomputedHash}'`,
        };
        return stringify(res);
    }

    @Transaction(false)
    @Returns('string')
    public async GetHistory(ctx: Context, sessionId: string): Promise<string> {
        this.checkAccess(ctx);
        const compositeKey = ctx.stub.createCompositeKey('Decision', [sessionId]);
        const iterator = await ctx.stub.getHistoryForKey(compositeKey);
        const history: any[] = [];

        let result = await iterator.next();
        while (!result.done) {
            const item: any = {
                txId: result.value.txId,
                isDelete: result.value.isDelete,
                timestamp: new Date(
                    (result.value.timestamp.seconds.toNumber() * 1000) +
                    Math.round(result.value.timestamp.nanos / 1000000)
                ).toISOString(),
            };
            if (!result.value.isDelete && result.value.value.length > 0) {
                item.value = JSON.parse(result.value.value.toString('utf8'));
            }
            history.push(item);
            result = await iterator.next();
        }
        await iterator.close();
        return stringify(history);
    }

    @Transaction(false)
    @Returns('string')
    public async ListDecisions(ctx: Context, pageSize: string, bookmark: string): Promise<string> {
        this.checkAccess(ctx);
        const size = parseInt(pageSize, 10) || 50;
        const response = await ctx.stub.getStateByRangeWithPagination('Decision\u0000', 'Decision\u007f', size, bookmark);

        const records: DecisionRecord[] = [];
        let result = await response.iterator.next();
        while (!result.done) {
            records.push(JSON.parse(result.value.value.toString('utf8')));
            result = await response.iterator.next();
        }
        await response.iterator.close();

        return stringify({
            records,
            recordsCount: response.metadata.fetchedRecordsCount,
            bookmark: response.metadata.bookmark,
        });
    }
}
