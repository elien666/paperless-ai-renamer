import Layout from './components/Layout';
import { ProgressProvider } from './contexts/ProgressContext';

function App() {
  return (
    <ProgressProvider>
      <Layout />
    </ProgressProvider>
  );
}

export default App;
