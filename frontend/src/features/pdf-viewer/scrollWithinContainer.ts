/**
 * Scroll acotado al panel del PDF.
 *
 * FIX (2026-08-14): el visor usaba `Element.scrollIntoView()`, que por
 * definición scrollea TODOS los ancestros scrolleables del elemento — incluido
 * el documento. Por eso cada click en un ojito arrastraba la página entera
 * hacia abajo: el panel del PDF se acomodaba, y de paso se llevaba puesta la
 * ventana. Con una lista de diez ítems, diez clicks = diez saltos.
 *
 * Estas funciones mueven ÚNICAMENTE el `scrollTop` del contenedor que se les
 * pasa. La ventana no se entera.
 */

/** Distancia del tope de `element` al tope del contenido de `container`. */
export function offsetWithinContainer(container: HTMLElement, element: HTMLElement): number {
  const containerRect = container.getBoundingClientRect();
  const elementRect = element.getBoundingClientRect();
  return elementRect.top - containerRect.top + container.scrollTop;
}

/** Lleva el contenido del contenedor a `top`. Nada más. */
export function scrollContainerTo(
  container: HTMLElement,
  top: number,
  { behavior = "smooth" as ScrollBehavior } = {},
): void {
  const safeTop = Math.max(0, top);
  if (typeof container.scrollTo === "function") {
    container.scrollTo({ top: safeTop, behavior });
    return;
  }
  // jsdom y navegadores viejos no implementan scrollTo con opciones.
  container.scrollTop = safeTop;
}


/** Dónde tiene que quedar el tope de la vista para enfocar una cita.
 *
 * `pageOffset` es la posición de la página dentro del contenido del panel;
 * `regionTop` es la coordenada Y de la primera línea del resaltado, en puntos
 * de la página sin escalar (el contrato que emite el backend), o null si no hay
 * coordenadas y sólo se puede enfocar la página.
 */
export function focusTargetOffset({
  pageOffset,
  regionTop,
  scale,
}: {
  pageOffset: number;
  regionTop: number | null;
  scale: number;
}): number {
  if (regionTop === null || !Number.isFinite(regionTop) || scale <= 0) {
    return pageOffset;
  }
  return pageOffset + regionTop * scale;
}

/** ¿Hay que volver a enfocar cuando termine de renderizar otra página?
 *
 * El visor renderiza una ventana de páginas alrededor de la actual, y las que
 * están ARRIBA de la página objetivo crecen a medida que cargan: cada una que
 * termina empuja la página objetivo hacia abajo. Enfocar una sola vez -- ni
 * bien cambia la página -- deja el visor en un lugar que deja de ser el
 * correcto medio segundo después. Es la causa de "enfoca mal en cualquier
 * página".
 *
 * Mientras quede alguna página anterior sin renderizar, la posición todavía se
 * va a mover y hay que volver a aplicarla.
 */
export function focusIsStillPending(
  pagesToRender: number[],
  targetPage: number,
  renderedPages: ReadonlySet<number>,
): boolean {
  return pagesToRender.some((page) => page <= targetPage && !renderedPages.has(page));
}


/** Cuánto texto del documento se deja por encima de la cita, como contexto. */
const MAX_LEAD_IN_PX = 96;

/**
 * El `scrollTop` final para dejar una cita a la vista.
 *
 * FIX (2026-08-14): el margen superior era el 30% del alto visible del panel.
 * En un panel de 800px son 240px de contexto — más que suficiente para que, con
 * una cita cerca del tope de su página, la vista termine mostrando la página
 * ANTERIOR. Es exactamente el caso reportado: una cita de la página 2 abría en
 * la portada.
 *
 * Ahora el margen es chico y, sobre todo, está ACOTADO al tope de la página
 * objetivo: el contexto que se muestra arriba de una cita nunca puede ser otra
 * página.
 */
export function focusScrollTop({
  pageOffset,
  regionTop,
  scale,
  viewportHeight,
}: {
  pageOffset: number;
  regionTop: number | null;
  scale: number;
  viewportHeight: number;
}): number {
  const target = focusTargetOffset({ pageOffset, regionTop, scale });
  const leadIn = Math.min(viewportHeight * 0.15, MAX_LEAD_IN_PX);
  return Math.max(0, Math.max(pageOffset, target - leadIn));
}
