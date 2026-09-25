import { useEffect, useState } from 'react';
import Orb from './orb/Orb.jsx';
import Chat from './chat/Chat.jsx';
import { useChatStream } from './chat/useChatStream.js';
import SystemPanel from './panels/SystemPanel.jsx';
import TasksPanel from './panels/TasksPanel.jsx';
import NotesPanel from './panels/NotesPanel.jsx';
import PendingActionsPanel from './panels/PendingActionsPanel.jsx';

export default function App() {
  const { messages, send, state, level, error } = useChatStream();
  const [refreshKey, setRefreshKey] = useState(0);
  const bump = () => setRefreshKey((key) => key + 1);
  const [clock, setClock] = useState('');

  // Los paneles se recargan cuando termina un turno, que es cuando pueden
  // haber cambiado; no hace falta polling para eso.
  useEffect(() => {
    if (state === 'idle' || state === 'awaiting') setRefreshKey((key) => key + 1);
  }, [state]);

  useEffect(() => {
    const id = setInterval(() => setClock(new Date().toLocaleTimeString()), 1000);
    return () => clearInterval(id);
  }, []);

  return (
    <div style={{ height: '100dvh', display: 'flex', flexDirection: 'column' }}>
      <header
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: '12px 20px',
          borderBottom: '1px solid var(--hairline)',
        }}
      >
        <span className="display" style={{ fontSize: 15 }}>Mikha</span>
        <span className="label">{clock}</span>
      </header>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '1fr 320px',
          gap: 'var(--gap)',
          padding: 'var(--gap)',
          flex: 1,
          minHeight: 0,
        }}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--gap)', minHeight: 0 }}>
          <div style={{ height: 'min(440px, 50vh)', flexShrink: 0 }}>
            <Orb state={state} level={level} />
          </div>
          <Chat messages={messages} onSend={send} error={error} />
        </div>

        <aside
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: 'var(--gap)',
            overflowY: 'auto',
          }}
        >
          <SystemPanel />
          <PendingActionsPanel
            refreshKey={refreshKey}
            onResolved={bump}
          />
          <TasksPanel refreshKey={refreshKey} onProposed={bump} />
          <NotesPanel refreshKey={refreshKey} onProposed={bump} />
        </aside>
      </div>
    </div>
  );
}
