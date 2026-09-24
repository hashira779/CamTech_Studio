/**
 * VIDA Studio Pro — Advanced Fluid Resizable Layout Engine
 * 
 * Features:
 * - Fluid pointer-drag resizing for Left (Media/AI), Right (Inspector/DSP), and Bottom (Timeline/Waveform) panels
 * - Zero-lag 60/120fps dragging via CSS Variables and pointer capture
 * - Smart collapse/snap thresholds with micro-collapse toggle chevrons
 * - Double-click to instantly reset panel to standard studio dimensions
 * - Keyboard accessible (Arrow keys, Shift+Arrow, Home/End) with ARIA separator semantics
 * - Real-time floating dimension HUD tooltip
 * - Persisted custom workspace state across reloads via localStorage
 * - Seamless integration with header Theater mode and panel toggle buttons
 * - Quick Studio Layout Presets (Standard, Cinema Monitor, Audio DAW Pro, Inspector Pro)
 */

export const LAYOUT_CONFIG = {
  left: {
    min: 200,
    max: 560,
    defaultWidth: 295,
    collapseThreshold: 110,
    cssVar: '--sidebar-left-width'
  },
  right: {
    min: 240,
    max: 640,
    defaultWidth: 320,
    collapseThreshold: 120,
    cssVar: '--sidebar-right-width'
  },
  bottom: {
    min: 60,
    max: 380,
    defaultHeight: 96,
    collapseThreshold: 45,
    cssVar: '--timeline-height'
  },
  storageKey: 'vida_studio_layout_v2'
};

export const LAYOUT_PRESETS = {
  default: {
    name: 'Standard Studio',
    left: 295,
    right: 320,
    bottom: 96,
    leftCollapsed: false,
    rightCollapsed: false
  },
  cinema: {
    name: 'Cinema Monitor',
    left: 295,
    right: 320,
    bottom: 64,
    leftCollapsed: true,
    rightCollapsed: true
  },
  audio: {
    name: 'Audio DAW Pro',
    left: 260,
    right: 300,
    bottom: 210,
    leftCollapsed: false,
    rightCollapsed: false
  },
  director: {
    name: 'Inspector Pro',
    left: 220,
    right: 480,
    bottom: 96,
    leftCollapsed: false,
    rightCollapsed: false
  }
};

let layoutState = {
  leftWidth: LAYOUT_CONFIG.left.defaultWidth,
  rightWidth: LAYOUT_CONFIG.right.defaultWidth,
  bottomHeight: LAYOUT_CONFIG.bottom.defaultHeight,
  leftCollapsed: false,
  rightCollapsed: false,
  bottomCollapsed: false
};

let hudElement = null;
let onResizeCallbacks = [];

/**
 * Register a callback when layout dimensions change (e.g. to redraw waveform)
 */
export function onLayoutResize(callback) {
  if (typeof callback === 'function') {
    onResizeCallbacks.push(callback);
  }
}

function notifyResize(panel, value) {
  window.dispatchEvent(new Event('resize'));
  for (const cb of onResizeCallbacks) {
    try {
      cb(panel, value);
    } catch (e) {
      console.warn('Layout resize callback error:', e);
    }
  }
}

/**
 * Load saved layout from localStorage
 */
function loadSavedLayout() {
  try {
    const raw = localStorage.getItem(LAYOUT_CONFIG.storageKey);
    if (!raw) return;
    const parsed = JSON.parse(raw);
    if (typeof parsed.leftWidth === 'number') {
      layoutState.leftWidth = Math.max(LAYOUT_CONFIG.left.min, Math.min(LAYOUT_CONFIG.left.max, parsed.leftWidth));
    }
    if (typeof parsed.rightWidth === 'number') {
      layoutState.rightWidth = Math.max(LAYOUT_CONFIG.right.min, Math.min(LAYOUT_CONFIG.right.max, parsed.rightWidth));
    }
    if (typeof parsed.bottomHeight === 'number') {
      layoutState.bottomHeight = Math.max(LAYOUT_CONFIG.bottom.min, Math.min(LAYOUT_CONFIG.bottom.max, parsed.bottomHeight));
    }
    layoutState.leftCollapsed = Boolean(parsed.leftCollapsed);
    layoutState.rightCollapsed = Boolean(parsed.rightCollapsed);
    layoutState.bottomCollapsed = Boolean(parsed.bottomCollapsed);
  } catch (e) {
    console.warn('Failed to load saved layout state:', e);
  }
}

/**
 * Save layout to localStorage
 */
function saveLayoutState() {
  try {
    localStorage.setItem(LAYOUT_CONFIG.storageKey, JSON.stringify(layoutState));
  } catch (e) {
    console.warn('Failed to persist layout state:', e);
  }
}

/**
 * Apply layout dimensions to CSS variables and workspace classes
 */
export function applyLayout(options = { animated: false }) {
  const root = document.documentElement;
  const workspace = document.getElementById('daw-workspace');
  const btnToggleLeft = document.getElementById('btn-toggle-left-panel');
  const btnToggleRight = document.getElementById('btn-toggle-right-panel');

  if (options.animated && workspace) {
    workspace.classList.add('layout-animated');
    setTimeout(() => workspace.classList.remove('layout-animated'), 350);
  }

  // Set CSS variables
  root.style.setProperty(LAYOUT_CONFIG.left.cssVar, `${layoutState.leftWidth}px`);
  root.style.setProperty(LAYOUT_CONFIG.right.cssVar, `${layoutState.rightWidth}px`);
  root.style.setProperty(LAYOUT_CONFIG.bottom.cssVar, `${layoutState.bottomHeight}px`);

  // Collapsed classes on workspace
  if (workspace) {
    workspace.classList.toggle('left-collapsed', layoutState.leftCollapsed);
    workspace.classList.toggle('right-collapsed', layoutState.rightCollapsed);
  }

  // Sync header button states
  if (btnToggleLeft) {
    btnToggleLeft.classList.toggle('active', !layoutState.leftCollapsed);
  }
  if (btnToggleRight) {
    btnToggleRight.classList.toggle('active', !layoutState.rightCollapsed);
  }

  // Update resizer ARIA attributes
  updateAriaAttributes();

  // Notify listeners
  notifyResize('all', layoutState);
}

function updateAriaAttributes() {
  const resizerLeft = document.getElementById('resizer-left');
  const resizerRight = document.getElementById('resizer-right');
  const resizerBottom = document.getElementById('resizer-bottom');

  if (resizerLeft) {
    resizerLeft.setAttribute('aria-valuenow', layoutState.leftCollapsed ? 0 : layoutState.leftWidth);
    resizerLeft.setAttribute('aria-valuemin', LAYOUT_CONFIG.left.min);
    resizerLeft.setAttribute('aria-valuemax', LAYOUT_CONFIG.left.max);
    resizerLeft.setAttribute('title', `Media Panel: ${layoutState.leftCollapsed ? 'Collapsed' : layoutState.leftWidth + 'px'} • Double-click to reset (${LAYOUT_CONFIG.left.defaultWidth}px)`);
    const chevron = resizerLeft.querySelector('.resizer-collapse-btn');
    if (chevron) {
      chevron.innerHTML = layoutState.leftCollapsed ? '›' : '‹';
      chevron.title = layoutState.leftCollapsed ? 'Expand Media Panel' : 'Collapse Media Panel';
    }
  }

  if (resizerRight) {
    resizerRight.setAttribute('aria-valuenow', layoutState.rightCollapsed ? 0 : layoutState.rightWidth);
    resizerRight.setAttribute('aria-valuemin', LAYOUT_CONFIG.right.min);
    resizerRight.setAttribute('aria-valuemax', LAYOUT_CONFIG.right.max);
    resizerRight.setAttribute('title', `Inspector Panel: ${layoutState.rightCollapsed ? 'Collapsed' : layoutState.rightWidth + 'px'} • Double-click to reset (${LAYOUT_CONFIG.right.defaultWidth}px)`);
    const chevron = resizerRight.querySelector('.resizer-collapse-btn');
    if (chevron) {
      chevron.innerHTML = layoutState.rightCollapsed ? '‹' : '›';
      chevron.title = layoutState.rightCollapsed ? 'Expand Inspector Panel' : 'Collapse Inspector Panel';
    }
  }

  if (resizerBottom) {
    resizerBottom.setAttribute('aria-valuenow', layoutState.bottomHeight);
    resizerBottom.setAttribute('aria-valuemin', LAYOUT_CONFIG.bottom.min);
    resizerBottom.setAttribute('aria-valuemax', LAYOUT_CONFIG.bottom.max);
    resizerBottom.setAttribute('title', `Timeline Console: ${layoutState.bottomHeight}px • Double-click to reset (${LAYOUT_CONFIG.bottom.defaultHeight}px)`);
    const chevron = resizerBottom.querySelector('.resizer-collapse-btn');
    if (chevron) {
      chevron.innerHTML = layoutState.bottomHeight <= LAYOUT_CONFIG.bottom.min + 10 ? '▲' : '▼';
      chevron.title = layoutState.bottomHeight <= LAYOUT_CONFIG.bottom.min + 10 ? 'Expand Timeline' : 'Compact Timeline';
    }
  }
}

/**
 * Create or get the HUD Dimension Tooltip
 */
function getHudTooltip() {
  if (!hudElement) {
    hudElement = document.createElement('div');
    hudElement.className = 'layout-hud-tooltip';
    document.body.appendChild(hudElement);
  }
  return hudElement;
}

function showHud(text, x, y) {
  const hud = getHudTooltip();
  hud.textContent = text;
  hud.classList.add('visible');
  hud.style.left = `${Math.min(window.innerWidth - 140, Math.max(12, x))}px`;
  hud.style.top = `${Math.min(window.innerHeight - 50, Math.max(12, y))}px`;
}

function hideHud() {
  if (hudElement) {
    hudElement.classList.remove('visible');
  }
}

/**
 * Setup dragging interaction for a resizer
 */
function setupResizer(resizerId, type) {
  const resizer = document.getElementById(resizerId);
  if (!resizer) return;

  let isDragging = false;
  let startX = 0;
  let startY = 0;
  let startDimension = 0;
  let rafId = null;

  // Click on mini collapse chevron inside handle
  const collapseBtn = resizer.querySelector('.resizer-collapse-btn');
  if (collapseBtn) {
    collapseBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      e.preventDefault();
      if (type === 'left') {
        toggleLeftPanel();
      } else if (type === 'right') {
        toggleRightPanel();
      } else if (type === 'bottom') {
        toggleBottomTimeline();
      }
    });
  }

  // Pointer Down -> Start Drag
  resizer.addEventListener('pointerdown', (e) => {
    // If clicked on collapse button, do not drag
    if (e.target.closest('.resizer-collapse-btn')) return;

    // Only primary button
    if (e.button !== 0) return;

    e.preventDefault();
    e.stopPropagation();

    isDragging = true;
    resizer.setPointerCapture(e.pointerId);

    startX = e.clientX;
    startY = e.clientY;

    if (type === 'left') {
      startDimension = layoutState.leftCollapsed ? 0 : layoutState.leftWidth;
    } else if (type === 'right') {
      startDimension = layoutState.rightCollapsed ? 0 : layoutState.rightWidth;
    } else if (type === 'bottom') {
      startDimension = layoutState.bottomHeight;
    }

    document.body.classList.add('is-resizing');
    document.body.classList.add(type === 'bottom' ? 'is-resizing-row' : 'is-resizing-col');
    resizer.classList.add('active');

    const label = type === 'left' ? 'Media Pool' : type === 'right' ? 'Inspector' : 'Timeline';
    showHud(`${label}: ${Math.round(startDimension)}px`, e.clientX + 16, e.clientY - 16);
  });

  // Pointer Move -> Update Dimensions (Zero-latency RAF)
  resizer.addEventListener('pointermove', (e) => {
    if (!isDragging) return;

    e.preventDefault();

    if (rafId) cancelAnimationFrame(rafId);

    rafId = requestAnimationFrame(() => {
      const dx = e.clientX - startX;
      const dy = e.clientY - startY;

      if (type === 'left') {
        const rawW = startDimension + dx;
        if (rawW < LAYOUT_CONFIG.left.collapseThreshold) {
          // Snap to collapse
          layoutState.leftCollapsed = true;
          document.documentElement.style.setProperty(LAYOUT_CONFIG.left.cssVar, `${LAYOUT_CONFIG.left.min}px`);
          const ws = document.getElementById('daw-workspace');
          if (ws) ws.classList.add('left-collapsed');
          showHud('Media Pool: ✕ Collapsed', e.clientX + 16, e.clientY - 16);
        } else {
          layoutState.leftCollapsed = false;
          const maxAllowed = Math.min(LAYOUT_CONFIG.left.max, Math.round(window.innerWidth * 0.45));
          const clamped = Math.max(LAYOUT_CONFIG.left.min, Math.min(maxAllowed, rawW));
          layoutState.leftWidth = clamped;
          document.documentElement.style.setProperty(LAYOUT_CONFIG.left.cssVar, `${clamped}px`);
          const ws = document.getElementById('daw-workspace');
          if (ws) ws.classList.remove('left-collapsed');
          showHud(`Media Pool: ${clamped}px`, e.clientX + 16, e.clientY - 16);
        }
        notifyResize('left', layoutState.leftWidth);
      } else if (type === 'right') {
        const rawW = startDimension - dx;
        if (rawW < LAYOUT_CONFIG.right.collapseThreshold) {
          // Snap to collapse
          layoutState.rightCollapsed = true;
          document.documentElement.style.setProperty(LAYOUT_CONFIG.right.cssVar, `${LAYOUT_CONFIG.right.min}px`);
          const ws = document.getElementById('daw-workspace');
          if (ws) ws.classList.add('right-collapsed');
          showHud('Inspector: ✕ Collapsed', e.clientX - 140, e.clientY - 16);
        } else {
          layoutState.rightCollapsed = false;
          const maxAllowed = Math.min(LAYOUT_CONFIG.right.max, Math.round(window.innerWidth * 0.48));
          const clamped = Math.max(LAYOUT_CONFIG.right.min, Math.min(maxAllowed, rawW));
          layoutState.rightWidth = clamped;
          document.documentElement.style.setProperty(LAYOUT_CONFIG.right.cssVar, `${clamped}px`);
          const ws = document.getElementById('daw-workspace');
          if (ws) ws.classList.remove('right-collapsed');
          showHud(`Inspector: ${clamped}px`, e.clientX - 140, e.clientY - 16);
        }
        notifyResize('right', layoutState.rightWidth);
      } else if (type === 'bottom') {
        const rawH = startDimension - dy;
        const maxAllowed = Math.min(LAYOUT_CONFIG.bottom.max, Math.round(window.innerHeight * 0.55));
        const clamped = Math.max(LAYOUT_CONFIG.bottom.min, Math.min(maxAllowed, rawH));
        layoutState.bottomHeight = clamped;
        document.documentElement.style.setProperty(LAYOUT_CONFIG.bottom.cssVar, `${clamped}px`);
        showHud(`Timeline: ${clamped}px`, e.clientX + 16, e.clientY - 36);
        notifyResize('bottom', layoutState.bottomHeight);
      }

      updateAriaAttributes();
    });
  });

  // Pointer Up / Cancel -> End Drag
  const endDrag = (e) => {
    if (!isDragging) return;
    isDragging = false;

    if (rafId) {
      cancelAnimationFrame(rafId);
      rafId = null;
    }

    try {
      resizer.releasePointerCapture(e.pointerId);
    } catch (err) {}

    document.body.classList.remove('is-resizing', 'is-resizing-col', 'is-resizing-row');
    resizer.classList.remove('active');
    hideHud();

    // Persist final state
    saveLayoutState();
    applyLayout({ animated: false });
  };

  resizer.addEventListener('pointerup', endDrag);
  resizer.addEventListener('pointercancel', endDrag);

  // Double-Click -> Reset to standard default width/height
  resizer.addEventListener('dblclick', (e) => {
    if (e.target.closest('.resizer-collapse-btn')) return;
    e.preventDefault();

    if (type === 'left') {
      if (layoutState.leftCollapsed || Math.abs(layoutState.leftWidth - LAYOUT_CONFIG.left.defaultWidth) < 5) {
        layoutState.leftCollapsed = !layoutState.leftCollapsed;
        layoutState.leftWidth = LAYOUT_CONFIG.left.defaultWidth;
      } else {
        layoutState.leftWidth = LAYOUT_CONFIG.left.defaultWidth;
        layoutState.leftCollapsed = false;
      }
    } else if (type === 'right') {
      if (layoutState.rightCollapsed || Math.abs(layoutState.rightWidth - LAYOUT_CONFIG.right.defaultWidth) < 5) {
        layoutState.rightCollapsed = !layoutState.rightCollapsed;
        layoutState.rightWidth = LAYOUT_CONFIG.right.defaultWidth;
      } else {
        layoutState.rightWidth = LAYOUT_CONFIG.right.defaultWidth;
        layoutState.rightCollapsed = false;
      }
    } else if (type === 'bottom') {
      layoutState.bottomHeight = LAYOUT_CONFIG.bottom.defaultHeight;
    }

    applyLayout({ animated: true });
    saveLayoutState();
  });

  // Keyboard Accessibility
  resizer.addEventListener('keydown', (e) => {
    const step = e.shiftKey ? 40 : 10;
    let handled = false;

    if (type === 'left') {
      if (e.key === 'ArrowLeft') {
        layoutState.leftWidth = Math.max(LAYOUT_CONFIG.left.min, layoutState.leftWidth - step);
        layoutState.leftCollapsed = false;
        handled = true;
      } else if (e.key === 'ArrowRight') {
        layoutState.leftWidth = Math.min(LAYOUT_CONFIG.left.max, layoutState.leftWidth + step);
        layoutState.leftCollapsed = false;
        handled = true;
      } else if (e.key === 'Home') {
        layoutState.leftCollapsed = true;
        handled = true;
      } else if (e.key === 'End') {
        layoutState.leftWidth = LAYOUT_CONFIG.left.max;
        layoutState.leftCollapsed = false;
        handled = true;
      }
    } else if (type === 'right') {
      if (e.key === 'ArrowLeft') {
        layoutState.rightWidth = Math.min(LAYOUT_CONFIG.right.max, layoutState.rightWidth + step);
        layoutState.rightCollapsed = false;
        handled = true;
      } else if (e.key === 'ArrowRight') {
        layoutState.rightWidth = Math.max(LAYOUT_CONFIG.right.min, layoutState.rightWidth - step);
        layoutState.rightCollapsed = false;
        handled = true;
      } else if (e.key === 'Home') {
        layoutState.rightWidth = LAYOUT_CONFIG.right.max;
        layoutState.rightCollapsed = false;
        handled = true;
      } else if (e.key === 'End') {
        layoutState.rightCollapsed = true;
        handled = true;
      }
    } else if (type === 'bottom') {
      if (e.key === 'ArrowUp') {
        layoutState.bottomHeight = Math.min(LAYOUT_CONFIG.bottom.max, layoutState.bottomHeight + step);
        handled = true;
      } else if (e.key === 'ArrowDown') {
        layoutState.bottomHeight = Math.max(LAYOUT_CONFIG.bottom.min, layoutState.bottomHeight - step);
        handled = true;
      } else if (e.key === 'Home') {
        layoutState.bottomHeight = LAYOUT_CONFIG.bottom.min;
        handled = true;
      } else if (e.key === 'End') {
        layoutState.bottomHeight = LAYOUT_CONFIG.bottom.max;
        handled = true;
      }
    }

    if (handled) {
      e.preventDefault();
      applyLayout({ animated: true });
      saveLayoutState();
    }
  });
}

/**
 * Toggle Left Panel collapse state
 */
export function toggleLeftPanel() {
  layoutState.leftCollapsed = !layoutState.leftCollapsed;
  applyLayout({ animated: true });
  saveLayoutState();
  return !layoutState.leftCollapsed;
}

/**
 * Toggle Right Panel collapse state
 */
export function toggleRightPanel() {
  layoutState.rightCollapsed = !layoutState.rightCollapsed;
  applyLayout({ animated: true });
  saveLayoutState();
  return !layoutState.rightCollapsed;
}

/**
 * Toggle Bottom Timeline height (compact vs expanded)
 */
export function toggleBottomTimeline() {
  if (layoutState.bottomHeight <= LAYOUT_CONFIG.bottom.min + 15) {
    layoutState.bottomHeight = LAYOUT_CONFIG.bottom.defaultHeight;
  } else if (layoutState.bottomHeight <= LAYOUT_CONFIG.bottom.defaultHeight + 10) {
    layoutState.bottomHeight = 180; // Expanded multi-track waveform
  } else {
    layoutState.bottomHeight = LAYOUT_CONFIG.bottom.min;
  }
  applyLayout({ animated: true });
  saveLayoutState();
}

/**
 * Toggle Theater Mode (collapses both left & right sidebars)
 */
export function toggleTheaterMode() {
  const isTheater = layoutState.leftCollapsed && layoutState.rightCollapsed;
  if (isTheater) {
    layoutState.leftCollapsed = false;
    layoutState.rightCollapsed = false;
  } else {
    layoutState.leftCollapsed = true;
    layoutState.rightCollapsed = true;
  }
  applyLayout({ animated: true });
  saveLayoutState();
  return !isTheater;
}

/**
 * Apply a named Layout Preset
 */
export function applyLayoutPreset(presetKey) {
  const preset = LAYOUT_PRESETS[presetKey] || LAYOUT_PRESETS.default;
  layoutState.leftWidth = preset.left;
  layoutState.rightWidth = preset.right;
  layoutState.bottomHeight = preset.bottom;
  layoutState.leftCollapsed = Boolean(preset.leftCollapsed);
  layoutState.rightCollapsed = Boolean(preset.rightCollapsed);

  applyLayout({ animated: true });
  saveLayoutState();
}

/**
 * Reset layout to standard studio defaults
 */
export function resetLayout() {
  applyLayoutPreset('default');
}

/**
 * Get current layout configuration state
 */
export function getLayoutState() {
  return { ...layoutState };
}

/**
 * Initialize Resizable Layout System
 */
export function initResizableLayout() {
  // Load saved configuration from localStorage
  loadSavedLayout();

  // Apply initial layout dimensions
  applyLayout({ animated: false });

  // Setup drag event listeners on dividers
  setupResizer('resizer-left', 'left');
  setupResizer('resizer-right', 'right');
  setupResizer('resizer-bottom', 'bottom');

  // Handle Window Resize limits
  window.addEventListener('resize', () => {
    const maxLeft = Math.round(window.innerWidth * 0.45);
    const maxRight = Math.round(window.innerWidth * 0.48);
    const maxBottom = Math.round(window.innerHeight * 0.55);

    let changed = false;
    if (layoutState.leftWidth > maxLeft) {
      layoutState.leftWidth = maxLeft;
      changed = true;
    }
    if (layoutState.rightWidth > maxRight) {
      layoutState.rightWidth = maxRight;
      changed = true;
    }
    if (layoutState.bottomHeight > maxBottom) {
      layoutState.bottomHeight = maxBottom;
      changed = true;
    }
    if (changed) {
      applyLayout({ animated: false });
    }
  });

  // Setup Layout Menu Dropdown in Header if present
  setupLayoutDropdown();
}

function setupLayoutDropdown() {
  const btnDropdown = document.getElementById('btn-layout-dropdown');
  const dropdownList = document.getElementById('layout-dropdown-list');

  if (!btnDropdown || !dropdownList) return;

  btnDropdown.addEventListener('click', (e) => {
    e.stopPropagation();
    const isShown = dropdownList.classList.contains('show');
    closeAllLayoutMenus();
    if (!isShown) {
      dropdownList.classList.add('show');
      btnDropdown.classList.add('active');
    }
  });

  dropdownList.querySelectorAll('.layout-dropdown-item').forEach(item => {
    item.addEventListener('click', (e) => {
      e.stopPropagation();
      const preset = item.dataset.preset;
      const action = item.dataset.action;

      if (preset) {
        applyLayoutPreset(preset);
      } else if (action === 'reset') {
        resetLayout();
      }
      closeAllLayoutMenus();
    });
  });

  document.addEventListener('click', () => {
    closeAllLayoutMenus();
  });
}

function closeAllLayoutMenus() {
  const dropdownList = document.getElementById('layout-dropdown-list');
  const btnDropdown = document.getElementById('btn-layout-dropdown');
  if (dropdownList) dropdownList.classList.remove('show');
  if (btnDropdown) btnDropdown.classList.remove('active');
}
