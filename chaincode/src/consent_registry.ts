import { Context, Contract, Info, Returns, Transaction } from 'fabric-contract-api';
// @ts-ignore
import stringify from 'json-stringify-deterministic';

const HASH_REGEX = /^[0-9a-fA-F]{64}$/;
const AUTHORIZED_MSPS = new Set(['Org1MSP', 'Org2MSP']);

export interface ConsentEntry {
    subjectRef: string;
    consentHash: string;
    is_revoked: boolean;
    recordedAt: string;
    revokedAt?: string;
    recordedByMsp: string;
}

@Info({ title: 'ConsentRegistryContract', description: 'Pseudonymous Biometric Consent Tracking Contract' })
export class ConsentRegistryContract extends Contract {
    constructor() {
        super('ConsentRegistry');
    }

    private checkAccess(ctx: Context): string {
        const mspId = ctx.clientIdentity.getMSPID();
        if (!AUTHORIZED_MSPS.has(mspId)) {
            throw new Error(`Unauthorized MSP: '${mspId}'`);
        }
        return mspId;
    }

    private formatTxTimestamp(ctx: Context): string {
        const ts = ctx.stub.getTxTimestamp();
        const millis = (ts.seconds.toNumber() * 1000) + Math.round(ts.nanos / 1000000);
        return new Date(millis).toISOString();
    }

    @Transaction(true)
    public async RecordConsent(
        ctx: Context,
        subjectRef: string,
        consentHash: string
    ): Promise<string> {
        const mspId = this.checkAccess(ctx);

        if (!HASH_REGEX.test(subjectRef)) {
            throw new Error(`Invalid subjectRef '${subjectRef}'. Must be a 64-character pseudonymous HMAC-SHA256 string.`);
        }
        if (!HASH_REGEX.test(consentHash)) {
            throw new Error(`Invalid consentHash '${consentHash}'. Must be a 64-character HMAC-SHA256 string.`);
        }

        const compositeKey = ctx.stub.createCompositeKey('Consent', [subjectRef]);
        const existingBytes = await ctx.stub.getState(compositeKey);
        if (existingBytes && existingBytes.length > 0) {
            const existing: ConsentEntry = JSON.parse(existingBytes.toString());
            if (!existing.is_revoked && existing.consentHash === consentHash) {
                return stringify({ status: 'ALREADY_EXISTS', entry: existing });
            }
        }

        const entry: ConsentEntry = {
            subjectRef,
            consentHash,
            is_revoked: false,
            recordedAt: this.formatTxTimestamp(ctx),
            recordedByMsp: mspId,
        };

        await ctx.stub.putState(compositeKey, Buffer.from(stringify(entry)));
        return stringify(entry);
    }

    @Transaction(true)
    public async RevokeConsent(ctx: Context, subjectRef: string): Promise<string> {
        this.checkAccess(ctx);

        if (!HASH_REGEX.test(subjectRef)) {
            throw new Error(`Invalid subjectRef '${subjectRef}'. Must be a 64-character string.`);
        }

        const compositeKey = ctx.stub.createCompositeKey('Consent', [subjectRef]);
        const stateBytes = await ctx.stub.getState(compositeKey);
        if (!stateBytes || stateBytes.length === 0) {
            throw new Error(`Consent record not found for subjectRef '${subjectRef}'`);
        }

        const entry: ConsentEntry = JSON.parse(stateBytes.toString());
        if (entry.is_revoked) {
            return stringify({ status: 'ALREADY_REVOKED', entry });
        }

        entry.is_revoked = true;
        entry.revokedAt = this.formatTxTimestamp(ctx);

        await ctx.stub.putState(compositeKey, Buffer.from(stringify(entry)));
        return stringify(entry);
    }

    @Transaction(false)
    @Returns('string')
    public async GetConsent(ctx: Context, subjectRef: string): Promise<string> {
        this.checkAccess(ctx);
        const compositeKey = ctx.stub.createCompositeKey('Consent', [subjectRef]);
        const stateBytes = await ctx.stub.getState(compositeKey);
        if (!stateBytes || stateBytes.length === 0) {
            throw new Error(`Consent record not found for subjectRef '${subjectRef}'`);
        }
        return stateBytes.toString();
    }
}
