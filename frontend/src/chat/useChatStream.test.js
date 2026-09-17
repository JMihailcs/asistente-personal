import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';
import { useChatStream } from './useChatStream.js';

function sseResponse(chunks) {
  const encoder = new TextEncoder();
  return {
    ok: true,
    body: {
      getReader() {
        let i = 0;
        return {
          read: async () =>
            i < chunks.length
              ? { done: false, value: encoder.encode(chunks[i++]) }
              : { done: true, value: undefined },
          releaseLock() {},
        };
      },
    },
  };
}

beforeEach(() => {
  vi.stubGlobal('requestAnimationFrame', vi.fn(() => 1));
  vi.stubGlobal('cancelAnimationFrame', vi.fn());
});

describe('useChatStream', () => {
  it('acumula los tokens y cierra con el evento done', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        sseResponse([
          'event: token\ndata: {"text":"Hola "}\n\n',
          'event: token\ndata: {"text":"mundo"}\n\n',
          'event: done\ndata: {"reply":"Hola mundo","pending_action_ids":[],"duration_seconds":1.2,"queried_at":"2026-09-11T10:00:00"}\n\n',
        ]),
      ),
    );

    const { result } = renderHook(() => useChatStream());
    await act(async () => {
      await result.current.send('hola');
    });

    await waitFor(() => expect(result.current.state).toBe('idle'));
    const last = result.current.messages.at(-1);
    expect(last.role).toBe('assistant');
    expect(last.text).toBe('Hola mundo');
    expect(last.durationSeconds).toBe(1.2);
    expect(last.incomplete).toBeFalsy();
  });

  it('pasa a awaiting cuando el turno deja una accion pendiente', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        sseResponse([
          'event: token\ndata: {"text":"listo"}\n\n',
          'event: done\ndata: {"reply":"listo","pending_action_ids":["abc123"],"duration_seconds":1,"queried_at":"2026-09-11T10:00:00"}\n\n',
        ]),
      ),
    );

    const { result } = renderHook(() => useChatStream());
    await act(async () => {
      await result.current.send('reinicia wireplumber');
    });

    await waitFor(() => expect(result.current.state).toBe('awaiting'));
  });

  it('muestra que esta pensando sin esperar a que el backend conteste', async () => {
    let answerFetch;
    vi.stubGlobal(
      'fetch',
      vi.fn(
        () =>
          new Promise((resolve) => {
            answerFetch = resolve;
          }),
      ),
    );

    const { result } = renderHook(() => useChatStream());
    let sending;
    await act(async () => {
      sending = result.current.send('hola');
    });

    // El fetch sigue sin resolver — con un proxy que buffea los headers eso
    // puede tardar segundos — y aun asi el usuario ya ve que lo escucharon.
    const last = result.current.messages.at(-1);
    expect(last.role).toBe('assistant');
    expect(last.pending).toBe(true);
    expect(result.current.state).toBe('thinking');

    await act(async () => {
      answerFetch(sseResponse([]));
      await sending;
    });
  });

  it('no deja un mensaje vacio del asistente si el backend no responde', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new Error('sin conexion');
      }),
    );

    const { result } = renderHook(() => useChatStream());
    await act(async () => {
      await result.current.send('hola');
    });

    // El turno no llego a empezar: no queda un bloque vacio colgado.
    expect(result.current.messages.at(-1).role).toBe('user');
    expect(result.current.error).toBeTruthy();
  });

  it('no marca como incompleta una respuesta que todavia esta en curso', async () => {
    const encoder = new TextEncoder();
    const chunks = [
      'event: token\ndata: {"text":"Hola"}\n\n',
      'event: done\ndata: {"reply":"Hola","pending_action_ids":[],"duration_seconds":1,"queried_at":"2026-09-11T10:00:00"}\n\n',
    ];
    let releaseStream;
    const gate = new Promise((resolve) => {
      releaseStream = resolve;
    });
    let i = 0;
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: true,
        body: {
          getReader: () => ({
            async read() {
              if (i === 0) await gate;
              return i < chunks.length
                ? { done: false, value: encoder.encode(chunks[i++]) }
                : { done: true, value: undefined };
            },
            releaseLock() {},
          }),
        },
      })),
    );

    const { result } = renderHook(() => useChatStream());
    let sending;
    await act(async () => {
      sending = result.current.send('hola');
    });

    // El turno arranco pero no llego ni un token: esto es "pensando",
    // no una respuesta truncada.
    const inFlight = result.current.messages.at(-1);
    expect(inFlight.role).toBe('assistant');
    expect(inFlight.pending).toBe(true);
    expect(inFlight.incomplete).toBeFalsy();

    await act(async () => {
      releaseStream();
      await sending;
    });
    expect(result.current.messages.at(-1).pending).toBeFalsy();
  });

  it('marca el mensaje como incompleto si el stream corta sin done', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => sseResponse(['event: token\ndata: {"text":"a medio "}\n\n'])),
    );

    const { result } = renderHook(() => useChatStream());
    await act(async () => {
      await result.current.send('hola');
    });

    await waitFor(() => expect(result.current.state).toBe('idle'));
    expect(result.current.messages.at(-1).incomplete).toBe(true);
    expect(result.current.error).toBeTruthy();
  });

  it('reporta error si el backend no responde', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new Error('sin conexion');
      }),
    );

    const { result } = renderHook(() => useChatStream());
    await act(async () => {
      await result.current.send('hola');
    });

    await waitFor(() => expect(result.current.error).toBeTruthy());
    expect(result.current.state).toBe('idle');
  });

  it('muestra el error que manda el backend en vez de quedarse pensando', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        sseResponse([
          'event: error\ndata: {"message":"No hay conexion con Ollama. Levantalo con \'ollama serve\'."}\n\n',
        ]),
      ),
    );

    const { result } = renderHook(() => useChatStream());
    await act(async () => {
      await result.current.send('hola');
    });

    await waitFor(() => expect(result.current.error).toContain('ollama serve'));
    expect(result.current.state).toBe('idle');
    // No queda un bloque vacio del asistente colgado diciendo "pensando".
    expect(result.current.messages.at(-1).role).toBe('user');
  });

  it('no se cuelga si la conexion se corta a mitad de la lectura', async () => {
    // El caso real: el backend manda 200, el generador explota, y la conexion
    // muere sin un solo byte. Sin atrapar esto, send() lanza y la UI se queda
    // en "pensando" para siempre.
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: true,
        body: {
          getReader: () => ({
            read: async () => {
              throw new TypeError('network error');
            },
            releaseLock() {},
          }),
        },
      })),
    );

    const { result } = renderHook(() => useChatStream());
    await act(async () => {
      await result.current.send('hola');
    });

    await waitFor(() => expect(result.current.error).toBeTruthy());
    expect(result.current.state).toBe('idle');
    expect(result.current.messages.at(-1).pending).toBeFalsy();
  });

  it('conserva los tokens ya recibidos cuando llega un error a mitad', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        sseResponse([
          'event: token\ndata: {"text":"Hola "}\n\n',
          'event: error\ndata: {"message":"se corto"}\n\n',
        ]),
      ),
    );

    const { result } = renderHook(() => useChatStream());
    await act(async () => {
      await result.current.send('hola');
    });

    await waitFor(() => expect(result.current.error).toBe('se corto'));
    const last = result.current.messages.at(-1);
    expect(last.text).toBe('Hola ');
    expect(last.incomplete).toBe(true);
    expect(last.pending).toBeFalsy();
  });
});
