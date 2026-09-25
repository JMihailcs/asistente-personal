# Referencia visual del orbe

Origen: diseño "OPTIMIND" de Anton Skvortsov (@anton_skv), visto en
collectui.com/designs/landing-page-ui-design-inspiration/ffec0157-16c4-434c-b06b-96d668cf21a6

| Archivo | Qué es |
|---|---|
| `optimind-completa-1.png` | Referencia buena, cuadro con la luz abajo a la derecha |
| `optimind-completa-2.png` | Referencia buena, cuadro con la luz abajo al centro |
| `optimind-fuente-collectui.png` | Captura de la página de origen (atribución y URL) |
| `recortada-vieja-1.png`, `recortada-vieja-2.png` | Las que se usaron en la Fase 4. **Estaban recortadas** y por eso el orbe salió como salió |

## Por qué importa esta corrección

El orbe de la Fase 4 (ya reemplazado, ver "Estado de la implementación") se construyó mirando las dos imágenes recortadas.
Lo que quedó afuera del recorte es justamente lo que le da el carácter a
la referencia: la niebla interior, la luz localizada y el desenfoque de
las partículas cercanas. El resultado actual es coherente consigo mismo,
pero es otra cosa.

## Qué tiene la referencia que el orbe de la Fase 4 no tenía

Ordenado por cuánto cambia la lectura de la imagen. Los "Hoy" describen
el orbe de la Fase 4, no el actual:

1. **La luz es localizada, no uniforme.** En la referencia hay dos o tres
   focos calientes (ámbar hacia blanco) concentrados en una región, como
   brasas dentro de una estructura apagada. El resto de la malla es casi
   negra. Hoy todo el orbe emite parejo, que es lo que lo vuelve plano.

2. **La estructura es una malla de superficie, no un árbol radial.**
   Triángulos irregulares sobre una cáscara hueca, tipo geodésica
   arrugada. Se ve el lado de atrás a través del de adelante. Hoy las
   aristas nacen en el centro y salen hacia afuera, que da una lectura de
   erizo o diente de león, no de cáscara.

3. **Hay niebla volumétrica adentro.** Humo oscuro ocupando el interior,
   más denso en el centro. Es lo que hace que se lea el hueco y la
   profundidad. Hoy el interior está vacío.

4. **Las partículas varían mucho de tamaño y de foco.** Hay círculos
   grandes y desenfocados (bokeh, cerca de la cámara), puntos medios
   nítidos y motas diminutas. Se agrupan donde está la luz. Hoy todas son
   del mismo tamaño y foco.

5. **Anillos concéntricos finísimos** rodeando la esfera, apenas
   visibles. Encuadran la figura sin competir con ella.

6. **La paleta tiene negro de verdad.** La malla es casi negra sobre
   fondo claro; el ámbar aparece solo donde hay luz. Hoy todo es ámbar
   sobre negro.

## La tensión que había que resolver antes de implementar (resuelta: se mantuvo oscuro)

La referencia es **fondo claro**. En la Fase 4 se decidió explícitamente
adaptarla a oscuro, y el resto del dashboard se construyó sobre esa
decisión (tokens, paneles, tipografía).

Portar la estructura (malla, niebla, luz localizada, bokeh) a fondo
oscuro es posible, pero el contraste se invierte: en la referencia la
malla es oscura sobre claro, y en oscuro habría que decidir si la malla
pasa a ser clara o si se mantiene oscura y se apoya todo en la luz.
**Eso es una decisión de diseño, no un detalle de implementación**, y
conviene tomarla antes de escribir código.

## Nota de movimiento

El usuario describió las partículas como que "se mueven al centro". En
la referencia estática no se puede confirmar la dirección; puede ser
flujo hacia adentro, o partículas cayendo hacia el foco de luz. Si se
implementa, vale hacer las dos y mirarlas.

## Costo de rendimiento a tener en cuenta

El orbe de la Fase 4 corría a 60 fps con 1100 nodos y 1099 aristas, medido en
el navegador. Niebla volumétrica y bokeh son las dos cosas de esta lista
que sí cuestan: la niebla pide un shader o sprites grandes con
transparencia, y el bokeh pide partículas grandes con blending. Conviene
medir de nuevo después de agregarlas, no asumir.

## Estado de la implementación (rediseño OPTIMIND a oscuro)

`frontend/src/orb/orb.js` ya implementa los seis puntos: malla de
superficie triangulada sobre cáscara arrugada, tres focos ámbar
móviles, niebla interior, polvo con tamaño/foco variado y bokeh, y tres
anillos finos. Se mantuvo fondo oscuro: la malla es gris cálido casi
apagado y solo se enciende (aditivo) cerca de los focos.

Rendimiento (Chromium headless con SwiftShader, sin GPU, 5 s de rAF):
antes 60 fps (1100 nodos, ~1100 aristas); después 60 fps a pixel ratio 1
y ~38 fps a pixel ratio 2 con el canvas de 320 px. Si el frame promedio
pasa de 24 ms el orbe degrada solo: primero sin niebla y pixel ratio 1,
luego la mitad del polvo.

### Segunda vuelta

Malla triangulada de verdad (envolvente convexa de puntos irregulares,
`buildSurfaceMesh`), orbe más grande (contenedor de `min(440px, 50vh)`, cámara más
cerca), más bokeh y más grande, niebla central más densa y brasas más
intensas con un resplandor casi blanco en el foco principal. Medición en
el mismo entorno de software: ~47 fps a pixel ratio 1 (60 antes de la
segunda vuelta), con la degradación automática si baja de ~41 fps.
