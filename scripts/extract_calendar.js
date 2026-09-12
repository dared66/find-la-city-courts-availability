// Run this function in the browser tool's read-only DOM evaluation on a loaded
// official WebTrac search page. Save the JSON result and pass it to --snapshot.
// Does not click bookings or export cookies, CSRF tokens, or action URLs.
() => {
  const headings = Array.from(document.querySelectorAll('.result-header__info'));
  const tables = Array.from(document.querySelectorAll('table#frwebsearch_output_table'));
  const source = new URL(location.href);
  for (const key of Array.from(source.searchParams.keys())) {
    if (!['InterfaceParameter', 'arwebsearch_buttonsearch', 'begintime', 'date', 'location', 'module', 'page'].includes(key))
      source.searchParams.delete(key);
  }
  return {
    source_url: source.href,
    captured_at: new Date().toISOString(),
    date: document.querySelector('[id^="date_vm_"][id$="_button"]')?.textContent.trim(),
    summary: document.querySelector('#frwebsearch_nextgenresultsgroup h1')?.textContent.trim(),
    courts: tables.map(t => {
      const field = label => t.querySelector(`[data-title="${label}"]`)?.textContent.trim();
      const name = field('Facility Description');
      const header = headings.find(h => h.querySelector('h2')?.textContent.trim() === name);
      const detail = t.querySelector('a[href*="iteminfo.html"]');
      const url = detail ? new URL(detail.href) : null;
      return {
        name, location: field('Location Description'), category: field('Class Description'),
        date: t.querySelector('.dateblock')?.getAttribute('data-tooltip'),
        detail_url: url ? `${url.origin}${url.pathname}?Module=FR&FMID=${url.searchParams.get('FMID')}` : null,
        rules: header?.textContent.trim() || '',
        blocks: Array.from(t.querySelectorAll('a.cart-button--state-block')).map(a => ({
          time: a.textContent.trim(), classes: a.className, tooltip: a.getAttribute('data-tooltip') || ''
        }))
      };
    })
  };
}
