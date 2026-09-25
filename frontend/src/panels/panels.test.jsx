import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import SystemPanel from './SystemPanel.jsx';
import TasksPanel from './TasksPanel.jsx';
import NotesPanel from './NotesPanel.jsx';
import PendingActionsPanel from './PendingActionsPanel.jsx';

function mockFetchOnce(payload) {
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => payload })));
}

describe('SystemPanel', () => {
  it('muestra las lecturas cuando el backend responde', async () => {
    mockFetchOnce({
      ram: { total_gb: 31.2, used_gb: 17.4, available_gb: 13.8, percent_used: 55.7 },
      disk: { path: '/', total_gb: 882, used_gb: 431, free_gb: 451, percent_used: 48.9 },
      gpu: { available: true, vram_used_percent: 20.4 },
    });

    render(<SystemPanel />);

    await waitFor(() => expect(screen.getByText(/31.2/)).toBeInTheDocument());
  });

  it('muestra desconectado, no ceros, si el backend falla', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new Error('caido');
      }),
    );

    render(<SystemPanel />);

    await waitFor(() => expect(screen.getByText(/sin conexión/i)).toBeInTheDocument());
    expect(screen.queryByText(/0 GB/)).not.toBeInTheDocument();
  });

  it('informa cuando la GPU no esta disponible', async () => {
    mockFetchOnce({
      ram: { total_gb: 31.2, used_gb: 1, available_gb: 30, percent_used: 3 },
      disk: { path: '/', total_gb: 882, used_gb: 1, free_gb: 881, percent_used: 1 },
      gpu: { available: false, reason: 'rocm-smi no está instalado o no está en PATH' },
    });

    render(<SystemPanel />);

    await waitFor(() => expect(screen.getByText(/rocm-smi/)).toBeInTheDocument());
  });
});

describe('TasksPanel', () => {
  it('lista las tareas por lista', async () => {
    mockFetchOnce({ lists: [{ name: 'Casa', tasks: [{ text: 'lavar los platos', done: false }] }] });

    render(<TasksPanel refreshKey={0} />);

    await waitFor(() => expect(screen.getByText(/lavar los platos/)).toBeInTheDocument());
    expect(screen.getByText('Casa')).toBeInTheDocument();
  });
});

describe('NotesPanel', () => {
  it('lista las notas recientes', async () => {
    mockFetchOnce({
      notes: [{ title: 'Idea de negocio', created: '2026-09-11T10:00:00', excerpt: 'vender cafe' }],
    });

    render(<NotesPanel refreshKey={0} />);

    await waitFor(() => expect(screen.getByText('Idea de negocio')).toBeInTheDocument());
  });
});

describe('PendingActionsPanel', () => {
  it('no renderiza nada cuando no hay acciones pendientes', async () => {
    mockFetchOnce({ actions: [] });

    const { container } = render(<PendingActionsPanel refreshKey={0} />);

    await waitFor(() => expect(container).toBeEmptyDOMElement());
  });

  it('muestra la accion pendiente con sus botones', async () => {
    mockFetchOnce({
      actions: [
        { action_id: 'abc123', tool_name: 'restart_service', kwargs: { service_name: 'wireplumber' } },
      ],
    });

    render(<PendingActionsPanel refreshKey={0} />);

    await waitFor(() => expect(screen.getByText(/restart_service/)).toBeInTheDocument());
    expect(screen.getByRole('button', { name: /aprobar/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /rechazar/i })).toBeInTheDocument();
  });
});

describe('editar y eliminar', () => {
  it('eliminar una tarea solo propone el cambio', async () => {
    const fetchMock = vi.fn(async (url) => ({
      ok: true,
      json: async () =>
        url === '/tasks'
          ? { lists: [{ name: 'Casa', tasks: [{ text: 'lavar', done: false }] }] }
          : {},
    }));
    vi.stubGlobal('fetch', fetchMock);
    const onProposed = vi.fn();

    render(<TasksPanel refreshKey={0} onProposed={onProposed} />);
    fireEvent.click(await screen.findByRole('button', { name: /eliminar/i }));

    await waitFor(() => expect(onProposed).toHaveBeenCalled());
    const call = fetchMock.mock.calls.find(([url]) => url === '/changes');
    expect(JSON.parse(call[1].body)).toEqual({
      action: 'delete_task',
      list_name: 'Casa',
      text: 'lavar',
    });
  });

  it('si el backend rechaza el cambio, avisa y no refresca', async () => {
    const fetchMock = vi.fn(async (url) => ({
      ok: url !== '/changes',
      json: async () =>
        url === '/tasks'
          ? { lists: [{ name: 'Casa', tasks: [{ text: 'lavar', done: false }] }] }
          : {},
    }));
    vi.stubGlobal('fetch', fetchMock);
    const onProposed = vi.fn();

    render(<TasksPanel refreshKey={0} onProposed={onProposed} />);
    fireEvent.click(await screen.findByRole('button', { name: /editar/i }));
    fireEvent.click(screen.getByRole('button', { name: /guardar/i }));

    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(screen.getByLabelText('nuevo texto')).toBeInTheDocument();
    expect(onProposed).not.toHaveBeenCalled();
  });

  it('editar una nota propone el nuevo titulo', async () => {
    const fetchMock = vi.fn(async (url) => ({
      ok: true,
      json: async () =>
        url === '/notes/recent'
          ? { notes: [{ id: 'idea', title: 'Idea', created: '2026', excerpt: 'x' }] }
          : {},
    }));
    vi.stubGlobal('fetch', fetchMock);

    render(<NotesPanel refreshKey={0} />);
    fireEvent.click(await screen.findByRole('button', { name: /editar/i }));
    fireEvent.change(screen.getByLabelText(/nuevo texto/i), { target: { value: 'Idea 2' } });
    fireEvent.click(screen.getByRole('button', { name: /guardar/i }));

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(([url]) => url === '/changes');
      expect(JSON.parse(call[1].body)).toEqual({
        action: 'edit_note',
        note: 'idea',
        new_title: 'Idea 2',
      });
    });
  });
});
