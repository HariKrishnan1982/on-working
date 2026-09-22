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

export default function App() {
  const [screen, setScreen] = useState<Screen>('login');
  const navigate: NavigateFn = setScreen;

  if (screen === 'login') return <LoginScreen navigate={navigate} />;

  const content: Partial<Record<Screen, React.ReactNode>> = {
    dashboard: <DashboardScreen navigate={navigate} />,
    'live-calls': <LiveCallsScreen navigate={navigate} />,
    'session-detail': <SessionDetailScreen navigate={navigate} />,
    alerts: <AlertsScreen navigate={navigate} />,
    'alert-detail': <AlertDetailScreen navigate={navigate} />,
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
