import { DecisionLedgerContract } from './decision_ledger';
import { ModelRegistryContract } from './model_registry';
import { ConsentRegistryContract } from './consent_registry';

export { DecisionLedgerContract } from './decision_ledger';
export { ModelRegistryContract } from './model_registry';
export { ConsentRegistryContract } from './consent_registry';

export const contracts: any[] = [
    DecisionLedgerContract,
    ModelRegistryContract,
    ConsentRegistryContract,
];
