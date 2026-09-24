/**
 * Config-driven voice-enrollment phases.
 *
 * Each phase binds one fixed phrase to one backend sample slot:
 *   Phase 1 -> samples[0], Phase 2 -> samples[1], Phase 3 -> samples[2]
 * submitted (in phase order) to POST /api/v1/users via the existing
 * `enrollUser({ ..., samples })` client. Phrase text is frontend-only and
 * is never sent to the backend.
 *
 * Phase 1 keeps the previously approved enrollment phrase verbatim.
 * Phrases 2-3 use different phonetic content while staying natural and
 * easy to read. No claim is made about biometric accuracy impact.
 */

export interface EnrollmentPhase {
  /** Zero-based slot index; also the order of `samples` in the request. */
  id: number;
  /** Short label, e.g. "Phase 1". */
  title: string;
  /** Exact phrase the user must read aloud for this phase. */
  phrase: string;
}

export const ENROLLMENT_PHASES: EnrollmentPhase[] = [
  {
    id: 0,
    title: 'Phase 1',
    phrase: 'The security gateway verifies all authorized voice interactions in real time.',
  },
  {
    id: 1,
    title: 'Phase 2',
    phrase: 'Please confirm the secure verification before continuing the conversation.',
  },
  {
    id: 2,
    title: 'Phase 3',
    phrase: 'Authorized users must complete voice verification before sensitive actions.',
  },
];

/** Per-phase recording lifecycle (derived in the screen, never a global flag). */
export type PhaseStatus = 'pending' | 'recording' | 'processing' | 'recorded' | 'error';

export const PHASE_STATUS_LABEL: Record<PhaseStatus, string> = {
  pending: 'Pending',
  recording: 'Recording',
  processing: 'Processing',
  recorded: 'Recorded',
  error: 'Needs attention',
};
