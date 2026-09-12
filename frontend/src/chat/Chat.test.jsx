import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';
import Chat from './Chat.jsx';

const noop = () => {};

describe('Chat', () => {
  it('dice que esta pensando mientras el turno no devolvio texto', () => {
    render(
      <Chat
        messages={[
          { role: 'user', text: 'que notas tenia?' },
          { role: 'assistant', text: '', pending: true },
        ]}
        onSend={noop}
      />,
    );

    expect(screen.getByText('pensando…')).toBeInTheDocument();
    expect(screen.queryByText('respuesta incompleta')).not.toBeInTheDocument();
  });

  it('deja de decir que piensa en cuanto empieza a llegar texto', () => {
    render(
      <Chat
        messages={[{ role: 'assistant', text: 'Tenias tres notas', pending: true }]}
        onSend={noop}
      />,
    );

    expect(screen.queryByText('pensando…')).not.toBeInTheDocument();
    expect(screen.getByText('Tenias tres notas')).toBeInTheDocument();
  });

  it('avisa solo cuando la respuesta de verdad se corto', () => {
    render(
      <Chat
        messages={[{ role: 'assistant', text: 'a medio ', incomplete: true }]}
        onSend={noop}
      />,
    );

    expect(screen.getByText('respuesta incompleta')).toBeInTheDocument();
    expect(screen.queryByText('pensando…')).not.toBeInTheDocument();
  });

  it('no muestra ningun aviso en una respuesta terminada', () => {
    render(
      <Chat
        messages={[
          { role: 'assistant', text: 'listo', durationSeconds: 1.2, queriedAt: '2026-09-11T10:00:00' },
        ]}
        onSend={noop}
      />,
    );

    expect(screen.queryByText('pensando…')).not.toBeInTheDocument();
    expect(screen.queryByText('respuesta incompleta')).not.toBeInTheDocument();
  });
});
