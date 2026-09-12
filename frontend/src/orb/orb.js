import * as THREE from 'three';

// Una sola nube: cada punto es un nodo del arbol, sin particulas sueltas
// flotando al margen. Encima corren los pulsos que saltan de nodo en nodo.
const NODE_COUNT = 700;
const PULSE_COUNT = 90;

// Cuanto mas adentro tiene que estar un nodo para poder ser padre de otro.
const RADIAL_STEP = 0.09;

// Pensar gira rapido y vibra; contestar gira lento y deja que la vibracion
// la marque la voz (via `level`). Las aristas nunca se apagan del todo.
const STATE_PARAMS = {
  idle: { amp: 0.02, speed: 0.3, opacity: 0.45, spin: 0.0015, edges: 0.22, pulse: 0.6 },
  thinking: { amp: 0.06, speed: 3.4, opacity: 0.8, spin: 0.009, edges: 0.6, pulse: 2.6 },
  speaking: { amp: 0.18, speed: 0.8, opacity: 1.0, spin: 0.003, edges: 0.4, pulse: 1.2 },
  awaiting: { amp: 0.04, speed: 0.5, opacity: 1.0, spin: 0.002, edges: 0.3, pulse: 0.8 },
};

// Cuanto de la diferencia se cubre por frame al cambiar de estado: sin esto
// el giro y las aristas cambiarian de golpe.
const FADE = 0.06;

/** Pseudoaleatorio determinista: la misma nube en cada carga. */
function noiseAt(i) {
  return Math.abs((Math.sin(i * 12.9898) * 43758.5453) % 1);
}

/** Reparte `count` direcciones parejo sobre la esfera (espiral de Fibonacci). */
function fibonacciDirection(i, count) {
  const y = 1 - (i / (count - 1)) * 2;
  const ring = Math.sqrt(Math.max(0, 1 - y * y));
  const theta = Math.PI * (1 + Math.sqrt(5)) * i;
  return [Math.cos(theta) * ring, y, Math.sin(theta) * ring];
}

/**
 * Une cada nodo con el nodo mas cercano que este mas cerca del centro.
 *
 * Recorriendo de adentro hacia afuera, cada nodo elige padre entre los que
 * ya quedaron detras: el resultado es un arbol que nace en el medio y se
 * abre en ramas hacia el borde, en vez de una malla tendida sobre la
 * cascara. Se calcula una sola vez sobre las posiciones de reposo — la nube
 * respira y rota entera, asi que la topologia sigue valiendo y cada frame
 * solo hay que mover los extremos.
 */
export function buildRadialTree(positions, count, minRadialStep = RADIAL_STEP) {
  const distanceToCenter = (i) =>
    Math.hypot(positions[i * 3], positions[i * 3 + 1], positions[i * 3 + 2]);

  const inwardFirst = Array.from({ length: count }, (_, i) => i).sort(
    (a, b) => distanceToCenter(a) - distanceToCenter(b),
  );

  const edges = [];
  for (let k = 1; k < inwardFirst.length; k += 1) {
    const child = inwardFirst[k];
    // El padre tiene que estar un escalon mas adentro, no solo un poco mas
    // adentro: si vale cualquiera, cada nodo se engancha con su vecino del
    // mismo radio y el arbol se acuesta sobre la cascara en vez de crecer
    // hacia afuera.
    const ceiling = distanceToCenter(child) - minRadialStep;
    let parent = inwardFirst[0];
    let bestDistance = Infinity;

    for (let m = 0; m < k; m += 1) {
      const candidate = inwardFirst[m];
      if (distanceToCenter(candidate) > ceiling) break;
      const dx = positions[child * 3] - positions[candidate * 3];
      const dy = positions[child * 3 + 1] - positions[candidate * 3 + 1];
      const dz = positions[child * 3 + 2] - positions[candidate * 3 + 2];
      const distance = dx * dx + dy * dy + dz * dz;
      if (distance < bestDistance) {
        bestDistance = distance;
        parent = candidate;
      }
    }
    edges.push(parent, child);
  }

  return Uint16Array.from(edges);
}

// Sprite de glow radial generado en memoria: da a cada particula el halo
// de luz emitida del diseno de referencia, sin depender de un asset.
function createGlowTexture(core, mid) {
  const size = 64;
  const element = document.createElement('canvas');
  element.width = size;
  element.height = size;
  const context = element.getContext('2d');
  if (!context) return null;

  const gradient = context.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
  gradient.addColorStop(0.0, core);
  gradient.addColorStop(0.25, mid);
  gradient.addColorStop(1.0, 'rgba(242, 160, 61, 0)');
  context.fillStyle = gradient;
  context.fillRect(0, 0, size, size);

  return new THREE.CanvasTexture(element);
}

export function createOrb(canvas) {
  const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(50, 1, 0.1, 100);
  camera.position.z = 3.2;

  // Los nodos ocupan todo el volumen, del centro al borde, con el exponente
  // cargando la mano hacia afuera para que el contorno siga leyendose
  // redondo. Quien mantiene las ramas radiales no es esta distribucion sino
  // el escalon de buildRadialTree, asi que poblar el borde no las acuesta.
  const nodeBase = new Float32Array(NODE_COUNT * 3);
  const nodePositions = new Float32Array(NODE_COUNT * 3);
  for (let i = 0; i < NODE_COUNT; i += 1) {
    const [dx, dy, dz] = fibonacciDirection(i, NODE_COUNT);
    const radius = 0.05 + Math.pow(noiseAt(i + 7000), 0.55) * 0.95;
    nodeBase.set([dx * radius, dy * radius, dz * radius], i * 3);
  }
  nodePositions.set(nodeBase);

  const glowTexture = createGlowTexture('rgba(255, 217, 160, 1)', 'rgba(242, 160, 61, 0.75)');
  const nodeGeometry = new THREE.BufferGeometry();
  nodeGeometry.setAttribute('position', new THREE.BufferAttribute(nodePositions, 3));
  const nodeMaterial = new THREE.PointsMaterial({
    size: 0.07,
    map: glowTexture,
    color: new THREE.Color('#f2a03d'),
    transparent: true,
    opacity: 0.85,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
    sizeAttenuation: true,
  });
  const nodes = new THREE.Points(nodeGeometry, nodeMaterial);

  const edges = buildRadialTree(nodeBase, NODE_COUNT);
  const edgePositions = new Float32Array(edges.length * 3);
  const edgeGeometry = new THREE.BufferGeometry();
  edgeGeometry.setAttribute('position', new THREE.BufferAttribute(edgePositions, 3));
  const edgeMaterial = new THREE.LineBasicMaterial({
    color: new THREE.Color('#f2a03d'),
    transparent: true,
    opacity: 0.22,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
  });
  const lines = new THREE.LineSegments(edgeGeometry, edgeMaterial);

  // Pulsos: puntitos que recorren una arista de punta a punta y al llegar
  // reaparecen en otra, como senales saltando de nodo en nodo.
  const edgeCount = edges.length / 2;
  const pulsePositions = new Float32Array(PULSE_COUNT * 3);
  const pulseEdge = new Uint16Array(PULSE_COUNT);
  const pulseProgress = new Float32Array(PULSE_COUNT);
  const pulseSpeed = new Float32Array(PULSE_COUNT);
  for (let p = 0; p < PULSE_COUNT; p += 1) {
    pulseEdge[p] = Math.floor(noiseAt(p + 100) * edgeCount) % edgeCount;
    pulseProgress[p] = noiseAt(p + 200);
    pulseSpeed[p] = 0.004 + noiseAt(p + 300) * 0.008;
  }

  const pulseGeometry = new THREE.BufferGeometry();
  pulseGeometry.setAttribute('position', new THREE.BufferAttribute(pulsePositions, 3));
  const pulseTexture = createGlowTexture('rgba(255, 255, 255, 1)', 'rgba(255, 217, 160, 0.9)');
  const pulseMaterial = new THREE.PointsMaterial({
    size: 0.05,
    map: pulseTexture,
    color: new THREE.Color('#ffd9a0'),
    transparent: true,
    opacity: 0.95,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
    sizeAttenuation: true,
  });
  const pulses = new THREE.Points(pulseGeometry, pulseMaterial);

  // Todo en el mismo grupo para que gire junto: si cada capa rotara por su
  // cuenta, las aristas se despegarian de sus nodos.
  const cloud = new THREE.Group();
  cloud.add(lines);
  cloud.add(nodes);
  cloud.add(pulses);
  scene.add(cloud);

  let state = 'idle';
  let level = 0;
  // Fase acumulada en vez de `tiempo * velocidad`: al cambiar de estado la
  // velocidad cambia, y multiplicar por el tiempo absoluto haria saltar la
  // animacion a otra parte de la onda.
  let phase = 0;
  let spin = STATE_PARAMS.idle.spin;
  let edgeOpacity = STATE_PARAMS.idle.edges;
  let rafId = null;
  let respawn = 1;

  const reduceMotion =
    typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;

  function resize() {
    const { clientWidth, clientHeight } = canvas;
    if (!clientWidth || !clientHeight) return;
    renderer.setSize(clientWidth, clientHeight, false);
    camera.aspect = clientWidth / clientHeight;
    camera.updateProjectionMatrix();
  }

  function breathe(source, target, count, amp, drive) {
    for (let i = 0; i < count; i += 1) {
      const i3 = i * 3;
      const bx = source[i3];
      const by = source[i3 + 1];
      const bz = source[i3 + 2];
      const wobble = Math.sin(phase + bx * 4) * Math.cos(phase + by * 4);
      const scale = 1 + wobble * amp * drive;
      target[i3] = bx * scale;
      target[i3 + 1] = by * scale;
      target[i3 + 2] = bz * scale;
    }
  }

  function frame() {
    const params = STATE_PARAMS[state] || STATE_PARAMS.idle;
    const drive = state === 'speaking' ? level : 1;
    phase += 0.016 * params.speed;

    breathe(nodeBase, nodePositions, NODE_COUNT, params.amp, drive);
    nodeGeometry.attributes.position.needsUpdate = true;

    // Las aristas siguen a sus nodos: cada vertice copia la posicion ya
    // calculada del nodo en el que nace.
    for (let e = 0; e < edges.length; e += 1) {
      const from = edges[e] * 3;
      const to = e * 3;
      edgePositions[to] = nodePositions[from];
      edgePositions[to + 1] = nodePositions[from + 1];
      edgePositions[to + 2] = nodePositions[from + 2];
    }
    edgeGeometry.attributes.position.needsUpdate = true;

    for (let p = 0; p < PULSE_COUNT; p += 1) {
      pulseProgress[p] += pulseSpeed[p] * params.pulse;
      if (pulseProgress[p] >= 1) {
        pulseProgress[p] = 0;
        // Salta a otra arista al azar; el contador da la variacion sin
        // guardar estado de un generador aparte.
        respawn += 1;
        pulseEdge[p] = Math.floor(noiseAt(respawn) * edgeCount) % edgeCount;
      }
      const edge = pulseEdge[p] * 2;
      const from = edges[edge] * 3;
      const to = edges[edge + 1] * 3;
      const t = pulseProgress[p];
      const p3 = p * 3;
      pulsePositions[p3] = nodePositions[from] + (nodePositions[to] - nodePositions[from]) * t;
      pulsePositions[p3 + 1] =
        nodePositions[from + 1] + (nodePositions[to + 1] - nodePositions[from + 1]) * t;
      pulsePositions[p3 + 2] =
        nodePositions[from + 2] + (nodePositions[to + 2] - nodePositions[from + 2]) * t;
    }
    pulseGeometry.attributes.position.needsUpdate = true;

    edgeOpacity += (params.edges - edgeOpacity) * FADE;
    edgeMaterial.opacity = edgeOpacity;
    nodeMaterial.opacity = params.opacity * (0.7 + 0.3 * drive);

    spin += (params.spin - spin) * FADE;
    cloud.rotation.y += spin;

    renderer.render(scene, camera);
    rafId = requestAnimationFrame(frame);
  }

  function start() {
    if (rafId === null) rafId = requestAnimationFrame(frame);
  }

  function stop() {
    if (rafId !== null) {
      cancelAnimationFrame(rafId);
      rafId = null;
    }
  }

  // Si la pestana no esta visible no tiene sentido quemar GPU de fondo.
  function onVisibility() {
    if (document.hidden) stop();
    else start();
  }

  resize();
  window.addEventListener('resize', resize);
  document.addEventListener('visibilitychange', onVisibility);

  if (reduceMotion) {
    renderer.render(scene, camera);
  } else {
    start();
  }

  return {
    setState(next) {
      if (next in STATE_PARAMS) state = next;
    },
    setLevel(next) {
      const value = Number(next);
      level = Number.isFinite(value) ? Math.min(1, Math.max(0, value)) : 0;
    },
    dispose() {
      stop();
      window.removeEventListener('resize', resize);
      document.removeEventListener('visibilitychange', onVisibility);
      nodeGeometry.dispose();
      nodeMaterial.dispose();
      edgeGeometry.dispose();
      edgeMaterial.dispose();
      pulseGeometry.dispose();
      pulseMaterial.dispose();
      glowTexture?.dispose();
      pulseTexture?.dispose();
      renderer.dispose();
    },
  };
}
