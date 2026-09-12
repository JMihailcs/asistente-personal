import { useEffect, useRef, useState } from 'react';

function formatTime(iso) {
  if (!iso) return '';
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleTimeString();
}

export default function Chat({ messages, onSend, error }) {
  const [draft, setDraft] = useState('');
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  function submit(event) {
    event.preventDefault();
    const text = draft.trim();
    if (!text) return;
    setDraft('');
    onSend(text);
  }

  return (
    <section style={{ display: 'flex', flexDirection: 'column', gap: 'var(--gap)', minHeight: 0, flex: 1 }}>
      <div style={{ overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 14, flex: 1 }}>
        {messages.map((message, index) => (
          <div key={index}>
            <div className="label">{message.role === 'user' ? 'vos' : 'mikha'}</div>
            <div style={{ whiteSpace: 'pre-wrap', lineHeight: 1.5 }}>{message.text}</div>
            {message.durationSeconds !== undefined && (
              <div className="label" style={{ marginTop: 6 }}>
                {formatTime(message.queriedAt)} · {message.durationSeconds.toFixed(1)}s
              </div>
            )}
            {message.pending && !message.text && (
              <div className="label live" style={{ marginTop: 6 }}>
                pensando…
              </div>
            )}
            {message.incomplete && (
              <div className="label live" style={{ marginTop: 6 }}>
                respuesta incompleta
              </div>
            )}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {error && <div className="label live">{error}</div>}

      <form onSubmit={submit}>
        <input
          className="panel"
          style={{
            width: '100%',
            color: 'var(--text)',
            fontFamily: 'var(--font-body)',
            fontSize: 14,
          }}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="escribí algo…"
          aria-label="mensaje"
        />
      </form>
    </section>
  );
}
