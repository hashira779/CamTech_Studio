// The header's one Export button opens this dialog: video quality, YouTube upload and the
// subtitle files, which used to sit in the header and at the bottom of the Lyrics tab.
// The controls inside keep their ids, so their own handlers in main.js work unchanged.
// Also closes the Lyrics tab's "⋯" menu once one of its actions is chosen.

const byId = (id) => document.getElementById(id);

export function openExportDialog() {
  const modal = byId('export-dialog');
  if (!modal) return;
  modal.style.display = 'flex';
  setTimeout(() => byId('btn-export')?.focus(), 50);
}

export function closeExportDialog() {
  const modal = byId('export-dialog');
  if (modal) modal.style.display = 'none';
  byId('btn-open-export')?.focus();
}

export function initExportDialog() {
  const modal = byId('export-dialog');
  if (modal) {
    byId('btn-open-export')?.addEventListener('click', openExportDialog);
    byId('btn-close-export-dialog')?.addEventListener('click', closeExportDialog);
    // The export shows its own progress window, so this one steps aside when it starts.
    byId('btn-export')?.addEventListener('click', closeExportDialog);
    modal.addEventListener('click', (e) => { if (e.target === modal) closeExportDialog(); });
    modal.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeExportDialog(); });
  }

  // "⋯" menus close after a choice, on Escape, and on a click anywhere else.
  document.querySelectorAll('details.ui-more').forEach((menu) => {
    menu.addEventListener('click', (e) => {
      if (e.target.closest('.ui-more-menu button:not([data-keep-open])')) menu.open = false;
    });
    menu.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') { menu.open = false; menu.querySelector('summary')?.focus(); }
    });
  });
  document.addEventListener('click', (e) => {
    document.querySelectorAll('details.ui-more[open]').forEach((menu) => {
      if (!menu.contains(e.target)) menu.open = false;
    });
  });
}
