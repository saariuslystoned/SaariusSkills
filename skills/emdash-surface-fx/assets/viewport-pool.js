/*
 * emdash-surface-fx / assets/viewport-pool.js
 * Teknium-style IntersectionObserver + (pointer: coarse) active WebGL/Canvas GPU pooler.
 *
 * Enforces MAX_LIVE = 6 on desktop and MAX_LIVE = 1 on mobile/coarse pointers (with tap-to-run)
 * so heavy shaders, dither canvases, and particle stages never exhaust browser WebGL contexts
 * or drop scroll frames on EmDash / DinkusKit storefronts.
 */

const DEFAULT_MAX_DESKTOP = 6;
const DEFAULT_MAX_MOBILE = 1;

function createViewportPool(opts) {
  const options = opts || {};
  const maxDesktop = options.maxDesktop || DEFAULT_MAX_DESKTOP;
  const maxMobile = options.maxMobile || DEFAULT_MAX_MOBILE;
  const rootMargin = options.rootMargin || '80px 0px';

  const entries = new Map();
  let observer = null;
  let tapTarget = null;

  const isCoarsePointer = () => {
    try {
      return typeof matchMedia !== 'undefined' && matchMedia('(pointer: coarse)').matches;
    } catch (_) {
      return false;
    }
  };

  const isReducedMotion = () => {
    try {
      return typeof matchMedia !== 'undefined' && matchMedia('(prefers-reduced-motion: reduce)').matches;
    } catch (_) {
      return false;
    }
  };

  const maxAllowed = () => (isCoarsePointer() ? maxMobile : maxDesktop);

  const rebalance = () => {
    const reduced = isReducedMotion();
    const limit = maxAllowed();
    const coarse = isCoarsePointer();

    if (reduced) {
      for (const item of entries.values()) {
        if (item.active) {
          item.active = false;
          if (typeof item.stop === 'function') item.stop();
        }
        if (typeof item.renderStatic === 'function' && !item.staticRendered) {
          item.renderStatic();
          item.staticRendered = true;
        }
      }
      return;
    }

    const visible = [];
    for (const item of entries.values()) {
      if (item.intersecting) {
        visible.push(item);
      } else if (item.active) {
        item.active = false;
        if (typeof item.stop === 'function') item.stop();
      }
    }

    /* Sort visible surfaces: tapped surface first on mobile, then highest intersection ratio */
    visible.sort((a, b) => {
      if (coarse && tapTarget) {
        if (a.el === tapTarget) return -1;
        if (b.el === tapTarget) return 1;
      }
      return (b.ratio || 0) - (a.ratio || 0) || a.order - b.order;
    });

    visible.forEach((item, idx) => {
      const shouldRun = idx < limit;
      if (shouldRun && !item.active) {
        item.active = true;
        if (typeof item.start === 'function') item.start();
      } else if (!shouldRun && item.active) {
        item.active = false;
        if (typeof item.stop === 'function') item.stop();
        if (typeof item.renderStatic === 'function') item.renderStatic();
      }
    });
  };

  const ensureObserver = () => {
    if (observer || typeof IntersectionObserver === 'undefined') return;
    observer = new IntersectionObserver(
      ioEntries => {
        for (const io of ioEntries) {
          const item = entries.get(io.target);
          if (!item) continue;
          item.intersecting = io.isIntersecting && io.intersectionRatio > 0.02;
          item.ratio = io.intersectionRatio || 0;
        }
        rebalance();
      },
      { rootMargin, threshold: [0, 0.05, 0.25, 0.6, 0.95] }
    );
  };

  let seq = 0;

  return {
    register(el, hooks) {
      const targetEl = typeof el === 'string' ? document.querySelector(el) : el;
      if (!targetEl) return () => {};
      ensureObserver();

      const item = {
        el: targetEl,
        order: ++seq,
        intersecting: true,
        ratio: 1,
        active: false,
        staticRendered: false,
        start: hooks && hooks.start,
        stop: hooks && hooks.stop,
        renderStatic: hooks && hooks.renderStatic,
      };
      entries.set(targetEl, item);

      const onPointerDown = () => {
        if (isCoarsePointer()) {
          tapTarget = targetEl;
          rebalance();
        }
      };
      targetEl.addEventListener('pointerdown', onPointerDown, { passive: true });

      if (observer) {
        observer.observe(targetEl);
      }
      if (typeof item.renderStatic === 'function') {
        item.renderStatic();
        item.staticRendered = true;
      }
      rebalance();

      return () => {
        if (observer) observer.unobserve(targetEl);
        targetEl.removeEventListener('pointerdown', onPointerDown);
        if (item.active && typeof item.stop === 'function') item.stop();
        entries.delete(targetEl);
        if (tapTarget === targetEl) tapTarget = null;
        rebalance();
      };
    },
    rebalance,
    getStats() {
      let liveCount = 0;
      for (const item of entries.values()) {
        if (item.active) liveCount++;
      }
      return {
        liveCount,
        maxLive: maxAllowed(),
        maxDesktop,
        maxMobile,
        isCoarse: isCoarsePointer(),
        reducedMotion: isReducedMotion(),
        registeredCount: entries.size,
      };
    },
  };
}

const defaultViewportPool = createViewportPool();

if (typeof window !== 'undefined') {
  window.createViewportPool = createViewportPool;
  window.defaultViewportPool = defaultViewportPool;
}
