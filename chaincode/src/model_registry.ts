import { Context, Contract, Info, Returns, Transaction } from 'fabric-contract-api';
// @ts-ignore
import stringify from 'json-stringify-deterministic';

const HASH_REGEX = /^[0-9a-fA-F]{64}$/;

export type GovernanceStatus = 'PROPOSED' | 'ACTIVE';

export interface ModelEntry {
    name: string;
    version: string;
    artefactSha256: string;
    status: GovernanceStatus;
    proposedByMsp: string;
    proposedAt: string;
    approvedByMsp?: string;
    approvedAt?: string;
}

export interface RulesEntry {
    rulesVersion: string;
    sha256: string;
    status: GovernanceStatus;
    proposedByMsp: string;
    proposedAt: string;
    approvedByMsp?: string;
    approvedAt?: string;
}

@Info({ title: 'ModelRegistryContract', description: 'Multi-Org Two-Step Model & Rules Governance Registry' })
export class ModelRegistryContract extends Contract {
    constructor() {
        super('ModelRegistry');
    }

    private formatTxTimestamp(ctx: Context): string {
        const ts = ctx.stub.getTxTimestamp();
        const millis = (ts.seconds.toNumber() * 1000) + Math.round(ts.nanos / 1000000);
        return new Date(millis).toISOString();
    }

    // ── Model Governance ────────────────────────────────────────────────────────

    @Transaction(true)
    public async ProposeModel(
        ctx: Context,
        name: string,
        version: string,
        artefactSha256: string
    ): Promise<string> {
        const mspId = ctx.clientIdentity.getMSPID();
        if (mspId !== 'Org1MSP') {
            throw new Error(`Only Org1MSP (Operator) may propose models. Caller MSP: '${mspId}'`);
        }
        if (!HASH_REGEX.test(artefactSha256)) {
            throw new Error(`Invalid artefactSha256 '${artefactSha256}'. Must be 64 hex characters.`);
        }

        const compositeKey = ctx.stub.createCompositeKey('Model', [name, version]);
        const existingBytes = await ctx.stub.getState(compositeKey);
        if (existingBytes && existingBytes.length > 0) {
            const existing: ModelEntry = JSON.parse(existingBytes.toString());
            if (existing.status === 'ACTIVE') {
                throw new Error(`Model '${name}:${version}' is already ACTIVE and cannot be re-proposed.`);
            }
        }

        const entry: ModelEntry = {
            name,
            version,
            artefactSha256: artefactSha256.toLowerCase(),
            status: 'PROPOSED',
            proposedByMsp: mspId,
            proposedAt: this.formatTxTimestamp(ctx),
        };

        await ctx.stub.putState(compositeKey, Buffer.from(stringify(entry)));
        return stringify(entry);
    }

    @Transaction(true)
    public async ApproveModel(
        ctx: Context,
        name: string,
        version: string,
        artefactSha256: string
    ): Promise<string> {
        const mspId = ctx.clientIdentity.getMSPID();
        if (mspId !== 'Org2MSP') {
            throw new Error(`Only Org2MSP (Auditor) may approve models. Caller MSP: '${mspId}'`);
        }

        const compositeKey = ctx.stub.createCompositeKey('Model', [name, version]);
        const stateBytes = await ctx.stub.getState(compositeKey);
        if (!stateBytes || stateBytes.length === 0) {
            throw new Error(`Cannot approve: Model '${name}:${version}' has not been proposed by Org1.`);
        }

        const entry: ModelEntry = JSON.parse(stateBytes.toString());
        if (entry.status === 'ACTIVE') {
            return stringify({ status: 'ALREADY_ACTIVE', entry });
        }
        if (entry.artefactSha256.toLowerCase() !== artefactSha256.toLowerCase()) {
            throw new Error(`Approval rejected: auditor hash '${artefactSha256}' does not match proposed hash '${entry.artefactSha256}'`);
        }

        entry.status = 'ACTIVE';
        entry.approvedByMsp = mspId;
        entry.approvedAt = this.formatTxTimestamp(ctx);

        await ctx.stub.putState(compositeKey, Buffer.from(stringify(entry)));
        return stringify(entry);
    }

    @Transaction(false)
    @Returns('string')
    public async GetModel(ctx: Context, name: string, version: string): Promise<string> {
        const compositeKey = ctx.stub.createCompositeKey('Model', [name, version]);
        const bytes = await ctx.stub.getState(compositeKey);
        if (!bytes || bytes.length === 0) {
            throw new Error(`Model not found: '${name}:${version}'`);
        }
        return bytes.toString();
    }

    // ── Rules Governance ────────────────────────────────────────────────────────

    @Transaction(true)
    public async ProposeRules(
        ctx: Context,
        rulesVersion: string,
        sha256: string
    ): Promise<string> {
        const mspId = ctx.clientIdentity.getMSPID();
        if (mspId !== 'Org1MSP') {
            throw new Error(`Only Org1MSP (Operator) may propose rules. Caller MSP: '${mspId}'`);
        }
        if (!HASH_REGEX.test(sha256)) {
            throw new Error(`Invalid rules sha256 '${sha256}'. Must be 64 hex characters.`);
        }

        const compositeKey = ctx.stub.createCompositeKey('Rules', [rulesVersion]);
        const existingBytes = await ctx.stub.getState(compositeKey);
        if (existingBytes && existingBytes.length > 0) {
            const existing: RulesEntry = JSON.parse(existingBytes.toString());
            if (existing.status === 'ACTIVE') {
                throw new Error(`Rules '${rulesVersion}' is already ACTIVE and cannot be re-proposed.`);
            }
        }

        const entry: RulesEntry = {
            rulesVersion,
            sha256: sha256.toLowerCase(),
            status: 'PROPOSED',
            proposedByMsp: mspId,
            proposedAt: this.formatTxTimestamp(ctx),
        };

        await ctx.stub.putState(compositeKey, Buffer.from(stringify(entry)));
        return stringify(entry);
    }

    @Transaction(true)
    public async ApproveRules(
        ctx: Context,
        rulesVersion: string,
        sha256: string
    ): Promise<string> {
        const mspId = ctx.clientIdentity.getMSPID();
        if (mspId !== 'Org2MSP') {
            throw new Error(`Only Org2MSP (Auditor) may approve rules. Caller MSP: '${mspId}'`);
        }

        const compositeKey = ctx.stub.createCompositeKey('Rules', [rulesVersion]);
        const stateBytes = await ctx.stub.getState(compositeKey);
        if (!stateBytes || stateBytes.length === 0) {
            throw new Error(`Cannot approve: Rules '${rulesVersion}' has not been proposed by Org1.`);
        }

        const entry: RulesEntry = JSON.parse(stateBytes.toString());
        if (entry.status === 'ACTIVE') {
            return stringify({ status: 'ALREADY_ACTIVE', entry });
        }
        if (entry.sha256.toLowerCase() !== sha256.toLowerCase()) {
            throw new Error(`Approval rejected: auditor hash '${sha256}' does not match proposed hash '${entry.sha256}'`);
        }

        entry.status = 'ACTIVE';
        entry.approvedByMsp = mspId;
        entry.approvedAt = this.formatTxTimestamp(ctx);

        await ctx.stub.putState(compositeKey, Buffer.from(stringify(entry)));
        return stringify(entry);
    }

    @Transaction(false)
    @Returns('string')
    public async GetRules(ctx: Context, rulesVersion: string): Promise<string> {
        const compositeKey = ctx.stub.createCompositeKey('Rules', [rulesVersion]);
        const bytes = await ctx.stub.getState(compositeKey);
        if (!bytes || bytes.length === 0) {
            throw new Error(`Rules not found: '${rulesVersion}'`);
        }
        return bytes.toString();
    }

    @Transaction(false)
    @Returns('string')
    public async ListActiveModels(ctx: Context): Promise<string> {
        const iterator = await ctx.stub.getStateByPartialCompositeKey('Model', []);
        const active: ModelEntry[] = [];
        let res = await iterator.next();
        while (!res.done) {
            const entry: ModelEntry = JSON.parse(res.value.value.toString('utf8'));
            if (entry.status === 'ACTIVE') {
                active.push(entry);
            }
            res = await iterator.next();
        }
        await iterator.close();
        return stringify(active);
    }
}
