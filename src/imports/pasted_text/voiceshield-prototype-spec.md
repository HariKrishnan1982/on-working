Create a complete high-fidelity enterprise cybersecurity web application prototype called "VoiceShield".

PRODUCT:
VoiceShield is an AI-powered real-time voice security gateway for organizations. It sits as a security layer in an existing communication environment and analyzes protected voice interactions before allowing, warning, requiring additional verification, or blocking suspicious interactions.

The system verifies caller identity, detects AI-generated or manipulated voice, analyzes conversational fraud/context, detects behavioral anomalies, performs adversarial cross-checking, fuses evidence into a 0–100 risk score, applies deterministic security policies, takes preventive action, and records security audit evidence on a permissioned Hyperledger Fabric blockchain.

TARGET USERS:
Banking & Finance, Enterprises, Government, Telecom/Communication providers.
Primary interface users are security administrators, fraud/security analysts, enterprise operators, and call-center security teams.

IMPORTANT:
This is an enterprise security gateway demonstration UI, NOT a consumer voice-calling application.
Do not design it as a social app, messaging app, or generic AI chatbot.
The UI must clearly communicate real-time security monitoring.

CURRENT MVP SCOPE:
Focus on voice security, voice identity verification, voice deepfake detection, context/fraud analysis, behavioral anomaly analysis, adversarial verification, risk scoring, policy enforcement, alerts, and blockchain audit.
Face/video deepfake functionality is a future extension and should NOT be presented as an active MVP feature.

TECHNOLOGY REPRESENTED IN THE UI:
Python/FastAPI backend
PyTorch
Wav2Vec2 / RawNet2
Librosa
Multi-agent Python architecture
Unified Security MCP Server
PostgreSQL
JWT/RBAC/TLS
React
Recharts
Hyperledger Fabric
Docker

DESIGN:
Create a dark, modern, professional enterprise cybersecurity interface.
Use dark navy/charcoal backgrounds with subtle borders and restrained blue accents.
Use green only for safe/online states.
Use amber/orange for warnings.
Use red for critical/block states.
Use blue for informational states.
Use Inter typography.
Use consistent 8–16px corner radii.
Avoid excessive gradients, glowing effects, unnecessary 3D graphics, and decorative elements.
Prioritize information hierarchy and readability.
Make the UI look suitable for a banking/government enterprise security operations environment.

GLOBAL LAYOUT:
Fixed left sidebar.
Top navigation bar.
Responsive main content area.
Sidebar navigation:
Dashboard
Live Calls
Alerts
Audit Trail
Trusted Users
Security Policies
System Status

Bottom of sidebar:
SECURE GATEWAY
Gateway Online
MCP Connected
Fabric Connected

SCREEN 1: LOGIN
Create a centered enterprise login card.
Title: VoiceShield
Subtitle: AI-Powered Security Gateway
Email field
Password field
Sign In button
Footer: Secure Enterprise Access / Authorized Access Only

SCREEN 2: DASHBOARD
Page title: Security Overview
Subtitle: Real-time monitoring of protected voice interactions.

Create KPI cards:
Active Calls: 12
Calls Analyzed: 1,248
Threats Detected: 27
Calls Blocked: 9
Gateway Status: ONLINE

Create a large "Real-Time Risk Monitoring" chart using mock data.

Create "Recent Security Events" table with:
Time
Caller
Risk
Detection
Action

Example rows:
10:42 | User 104 | 92 | Voice Clone | BLOCKED
10:39 | User 087 | 68 | Suspicious Context | MFA
10:31 | User 221 | 24 | Verified | ALLOWED
10:25 | User 112 | 81 | Deepfake Signal | CALLBACK

SCREEN 3: LIVE CALLS
Title: Live Call Monitoring
Show active sessions.
Each call card should contain:
Session ID
Caller/User ID
Duration
Risk score
Identity score
Deepfake probability
Context risk
Behavior score
Current action
View Session button

SCREEN 4: LIVE SESSION DETAIL
This is the primary demonstration screen.

Header:
CALL SESSION #CALL-1042
Analysis Active

Caller information:
User ID: EMP-1042
Role: Finance Manager
Organization: Demo Organization
Duration: 02:43
Communication: PSTN/VoIP

Create a large risk score visualization:
92 / 100
CRITICAL

Create five agent cards:

VOICE IDENTITY AGENT
Match Score: 92%
Status: High Confidence

VOICE DEEPFAKE AGENT
Synthetic Probability: 87%
Status: Suspicious

CONTEXT / FRAUD AGENT
Risk Level: HIGH
Status: Suspicious Request

BEHAVIOR / ANOMALY AGENT
Anomaly Score: 74%
Status: Unusual

ADVERSARIAL AGENT
Status: Suspicious
Cross-check: Flagged

Create an Evidence Fusion section:
Voice Identity: 92%
Voice Deepfake: 87%
Context/Fraud: HIGH
Behavior: 74%
Adversarial: FLAGGED

Then show:
UNIFIED RISK ENGINE
Risk Score: 92 / 100

Then show:
SECURITY DECISION
BLOCK

Reason:
Possible AI-generated voice combined with suspicious high-risk interaction context.

Policy:
CRITICAL_RISK_BLOCK

Create a Unified Security MCP panel:
MCP Server: CONNECTED
Authorized tools:
Voice Model
User Profile Service
Risk Engine
Security Policy
Audit Service

Show:
Unauthorized Tools: 0
Last Authorization: 10:42:17

SCREEN 5: ALERTS
Title: Security Alerts
Filters:
All
Critical
High
Medium
Resolved

Create alert cards/table.

Critical alert:
Possible Voice Cloning Attack
CALL-1042
Risk 92/100
Action BLOCKED

High alert:
Suspicious Financial Request
CALL-1038
Risk 76/100
Action MFA REQUIRED

SCREEN 6: ALERT DETAIL
Show:
Security Alert
Possible Voice Cloning Attack
Risk Score: 92/100

Detection Evidence:
Identity analyzed
Synthetic speech detected
Suspicious context
Behavioral anomaly

Action:
BLOCKED

Policy:
CRITICAL_RISK_BLOCK

Audit Status:
Recorded
Blockchain: Hyperledger Fabric
Evidence Hash: 7f91...a83c
Timestamp: 2026-09-21 10:42:18
Integrity: VERIFIED

SCREEN 7: AUDIT TRAIL
Title: Tamper-Evident Audit Trail
Subtitle: Security decisions recorded for verification and compliance.

Table:
Timestamp
Event
Risk
Action
Audit Status

Example:
10:42:18 | Voice Clone | 92 | BLOCK | Verified
10:39:11 | Fraud Risk | 68 | MFA | Verified
10:31:42 | Verified Call | 24 | ALLOW | Verified

Create an audit detail panel showing:
Event ID
Session ID
Decision
Risk
Evidence Hash
Blockchain Network: Hyperledger Fabric
Integrity: Verified

SCREEN 8: TRUSTED USERS
Title: Trusted User Profiles
Create a table with:
User
Role
Voice Profile
Status

Button:
+ Register User

SCREEN 9: REGISTER USER
Create a 4-step enrollment flow:
1. User Information
2. Voice Enrollment
3. Feature Extraction
4. Profile Created

Voice Enrollment UI:
Record voice samples
Sample 1
Sample 2
Sample 3
Voice Quality
Create Secure Profile

After completion show:
Voice Profile Created
Profile ID
Status: Active

SCREEN 10: SECURITY POLICIES
Title: Security Policies

Create readable rule cards.

Policy 1:
CRITICAL RISK POLICY
IF Risk Score >= 80
AND Deepfake Probability > 70%
THEN:
Block Call
Create Alert
Record Audit

Policy 2:
HIGH RISK POLICY
Risk Score 60–79
THEN:
Require MFA
Request Callback
Create Security Alert

Policy 3:
LOW RISK POLICY
Risk Score < 30
THEN:
Allow
Continue Monitoring

SCREEN 11: SYSTEM STATUS
Title: System Status

Show service health:
Voice Engine — ONLINE
Deepfake Detector — ONLINE
Context Agent — ONLINE
Behavior Agent — ONLINE
Adversarial Agent — ONLINE
MCP Server — ONLINE
Risk Engine — ONLINE
PostgreSQL — ONLINE
Hyperledger Fabric — CONNECTED

Show API health:
API Gateway — Healthy
Average Response Time — 142 ms
Active Connections — 37

PROTOTYPE NAVIGATION:
Login → Dashboard
Dashboard → Live Calls
Live Calls → Session Detail
Session Detail → Alerts
Alerts → Alert Detail
Alert Detail → Audit Trail
Dashboard → Trusted Users
Trusted Users → Register User
Dashboard → Security Policies
Dashboard → System Status

CREATE REUSABLE COMPONENTS:
Metric Card
Risk Score Card
Agent Card
Call Card
Alert Card
Status Badge
Risk Badge
Table Row
Chart Container
Sidebar Item
Top Navigation
Modal
Progress Bar
Risk Gauge
Audit Record
System Status Indicator
Buttons

Use realistic but clearly fictional demo data.
Do not imply that the demo data represents real people or organizations.

The final result should look like a polished enterprise security gateway used to demonstrate the VoiceShield SIH project to technical judges.