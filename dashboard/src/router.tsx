import { createBrowserRouter } from 'react-router-dom';
import { ErrorBoundary } from './components/common/ErrorBoundary';
import { RootLayout } from './layouts/RootLayout';
import { DashboardPage } from './pages/Dashboard';
import { DetectionDetailPage } from './pages/DetectionDetail';
import { DetectionListPage } from './pages/DetectionList';
import { StatsPage } from './pages/Stats';

export const router = createBrowserRouter([
  {
    path: '/',
    element: <RootLayout />,
    errorElement: <ErrorBoundary />,
    children: [
      { index: true, element: <DashboardPage /> },
      { path: 'detections', element: <DetectionListPage /> },
      { path: 'detections/:id', element: <DetectionDetailPage /> },
      { path: 'stats', element: <StatsPage /> },
    ],
  },
]);
