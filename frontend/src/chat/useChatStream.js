import { useCallback, useEffect, useRef, useState } from 'react';

const LEVEL_BUMP = 0.35;
const LEVEL_DECAY = 0.92;

function parseSSE(buffer) {
  // Devuelve [eventos completos, resto sin terminar].
  const blocks = buffer.split('\n\n');
  const rest = blocks.pop() ?? '';
  const events = [];
  for (const block of blocks) {
    let name = null;
    let data = null;
    for (const line of block.split('\n')) {
      if (line.startsWith('event: ')) name = line.slice(7);
      else if (line.startsWith('data: ')) {
        try {
          data = JSON.parse(line.slice(6));
        } catch {
          data = null;
        }
      }
    }
    if (name) events.push({ name, data });
  }
  return [events, rest];
}

export function useChatStream() {
  const [messages, setMessages] = useState([]);
  const [state, setState] = useState('idle');
  const [level, setLevel] = useState(0);
  const [error, setError] = useState(null);
  const levelRef = useRef(0);
  const rafRef = useRef(null);

  // Seguidor de envolvente: cada token empuja el nivel y este loop lo decae.
  // Manana esta misma senal la alimenta la amplitud del audio, sin cambiar
  // nada del orbe.
  useEffect(() => {
    function tick() {
      levelRef.current *= LEVEL_DECAY;
      setLevel(levelRef.current);
      rafRef.current = requestAnimationFrame(tick);
    }
    rafRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafRef.current);
  }, []);

  const send = useCallback(async (text) => {
    setError(null);
    setMessages((prev) => [...prev, { role: 'user', text }]);
    setState('thinking');

    let response;
    try {
      response = await fetch('/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: 'web', message: text }),
      });
    } catch (err) {
      setError(err.message || 'sin conexión con el backend');
      setState('idle');
      return;
    }

    if (!response.ok || !response.body) {
      setError(`el backend respondió ${response.status}`);
      setState('idle');
      return;
    }

    setMessages((prev) => [...prev, { role: 'assistant', text: '', incomplete: true }]);

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let sawDone = false;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const [events, rest] = parseSSE(buffer);
      buffer = rest;

      for (const event of events) {
        if (event.name === 'token') {
          setState('speaking');
          levelRef.current = Math.min(1, levelRef.current + LEVEL_BUMP);
          setMessages((prev) => {
            const next = [...prev];
            const last = { ...next[next.length - 1] };
            last.text += event.data?.text ?? '';
            next[next.length - 1] = last;
            return next;
          });
        } else if (event.name === 'done') {
          sawDone = true;
          const pending = event.data?.pending_action_ids ?? [];
          setMessages((prev) => {
            const next = [...prev];
            next[next.length - 1] = {
              role: 'assistant',
              text: event.data.reply,
              durationSeconds: event.data.duration_seconds,
              queriedAt: event.data.queried_at,
              pendingActionIds: pending,
            };
            return next;
          });
          setState(pending.length > 0 ? 'awaiting' : 'idle');
        }
      }
    }

    if (!sawDone) {
      // El stream corto a mitad: queda marcado incompleto. Nunca se muestra
      // una respuesta truncada como si estuviera terminada.
      setError('la respuesta se cortó antes de terminar');
      setState('idle');
    }
  }, []);

  return { messages, send, state, level, error };
}
