import { useState } from 'react';
import Layout from './components/Layout';
import LoginScreen from './screens/LoginScreen';
import DashboardScreen from './screens/DashboardScreen';
import LiveCallsScreen from './screens/LiveCallsScreen';
import SessionDetailScreen from './screens/SessionDetailScreen';
import AlertsScreen from './screens/AlertsScreen';
import AlertDetailScreen from './screens/AlertDetailScreen';
import AuditTrailScreen from './screens/AuditTrailScreen';
import TrustedUsersScreen from './screens/TrustedUsersScreen';
import RegisterUserScreen from './screens/RegisterUserScreen';
import SecurityPoliciesScreen from './screens/SecurityPoliciesScreen';
import SystemStatusScreen from './screens/SystemStatusScreen';

export type Screen =
  | 'login' | 'dashboard' | 'live-calls' | 'session-detail'
  | 'alerts' | 'alert-detail' | 'audit-trail' | 'trusted-users'
  | 'register-user' | 'security-policies' | 'system-status';

export type NavigateFn = (screen: Screen) => void;

/** Selected record ids shared across screens (upload/select → detail flow). */
export interface Selection {
  sessionId: string | null;
  alertId: string | null;
  openSession: (id: string) => void;
  openAlert: (id: string) => void;
}

export default function App() {
  const [screen, setScreen] = useState<Screen>('login');
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [alertId, setAlertId] = useState<string | null>(null);
  const navigate: NavigateFn = setScreen;

  if (screen === 'login') return <LoginScreen navigate={navigate} />;

  const selection: Selection = {
    sessionId,
    alertId,
    openSession: (id: string) => {
      setSessionId(id);
      setScreen('session-detail');
    },
    openAlert: (id: string) => {
      setAlertId(id);
      setScreen('alert-detail');
    },
  };

  const content: Partial<Record<Screen, React.ReactNode>> = {
    dashboard: <DashboardScreen navigate={navigate} selection={selection} />,
    'live-calls': <LiveCallsScreen navigate={navigate} selection={selection} />,
    'session-detail': <SessionDetailScreen navigate={navigate} selection={selection} />,
    alerts: <AlertsScreen navigate={navigate} selection={selection} />,
    'alert-detail': <AlertDetailScreen navigate={navigate} selection={selection} />,
    'audit-trail': <AuditTrailScreen navigate={navigate} />,
    'trusted-users': <TrustedUsersScreen navigate={navigate} />,
    'register-user': <RegisterUserScreen navigate={navigate} />,
    'security-policies': <SecurityPoliciesScreen navigate={navigate} />,
    'system-status': <SystemStatusScreen navigate={navigate} />,
  };

  return (
    <Layout currentScreen={screen} navigate={navigate}>
      {content[screen]}
    </Layout>
  );
}
