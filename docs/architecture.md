# Architecture

## System Overview
The voice-fraud detection system processes incoming calls via a central gateway, splits analysis across three specialized branches, fuses the results, evaluates risk via rule-based logic, and dispatches actions.

### Data Flow
1. **Input**: Call audio and metadata hit the API Gateway.
2. **Analysis**:
    - **Anti-spoofing**: Checks for synthetic or replayed voice.
    - **Speaker Verification**: Compares embeddings against claimed identity.
    - **ASR & Intent**: Transcribes and analyzes intent for scams.
3. **Fusion**: Aggregates all branch scores into `FusedEvidence`.
4. **Risk Engine**: Evaluates evidence against predefined rules.
5. **Dispatch & Audit**: Takes action and logs an immutable `AuditRecord`.

## Branches
- `antispoof`: Deepfake detection.
- `speaker`: Biometric verification.
- `asr_intent`: Contextual fraud detection.

## Risk Engine
Evaluates fused evidence to categorize risk as LOW, MEDIUM, HIGH, or CRITICAL.

## Audit Trail
Cryptographically logs decision lineage for compliance and tracing.

## MCP Server
Exposes verification tools to intelligent agents using the Model Context Protocol.

## Agents
- **Voice Identity Agent**: Validates claimed identity.
- **Voice Deepfake Agent**: Detects generative audio.
- **Context Fraud Agent**: Identifies scammy language.
- **Adversarial Agent**: Tests system robustness.
