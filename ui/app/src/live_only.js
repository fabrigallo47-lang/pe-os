/*
 * live_only — remove everything from the frontend that no extraction produced.
 *
 * The V17 package ships a complete synthetic case so the interface can be shown
 * before a backend exists. That is the right way to hand over a design, and the
 * wrong thing to look at when the question is "what did the extractor actually
 * find?" — a screen that renders identically either way cannot answer it.
 *
 * So this empties the fixture in place, before engine.js and render.js capture
 * their references to it. Object shapes survive; content does not. What appears
 * afterwards is what the projection put there, and nothing else.
 *
 * Views the extraction does not feed are not left blank: the projection names
 * them in `absent`, with the reason, and the guard in render.js shows that
 * reason instead of an empty frame. A missing screen and a broken screen look
 * nothing alike, which is the point.
 *
 * Off with ?fixture=keep — the demo is still worth being able to see.
 */
(function () {
  'use strict';

  var params = new URLSearchParams(location.search);
  var keep = params.get('fixture') === 'keep';
  var connected = params.get('mode') === 'connected';

  // Only strip when connected to a backend. Opening the package on its own
  // should still show the package.
  if (keep || !connected) {
    window.PantaLive = { stripped: false, absent: {} };
    return;
  }

  /*
   * Empty a value while preserving its shape.
   *
   * Arrays become empty, strings become empty, numbers become null — the keys
   * stay, so code that reaches three levels down finds an object rather than a
   * crash. Only the values are gone.
   */
  function emptyInPlace(node, seen) {
    seen = seen || new Set();
    if (!node || typeof node !== 'object' || seen.has(node)) return node;
    seen.add(node);
    if (Array.isArray(node)) { node.length = 0; return node; }
    Object.keys(node).forEach(function (key) {
      var v = node[key];
      if (Array.isArray(v)) { v.length = 0; }
      else if (v && typeof v === 'object') { emptyInPlace(v, seen); }
      else if (typeof v === 'string') { node[key] = ''; }
      else if (typeof v === 'number') { node[key] = null; }
      else if (typeof v === 'boolean') { node[key] = false; }
    });
    return node;
  }

  var F = window.PANTA_V17_FIXTURE;
  if (F) {
    // case_id is identity, not content: the API is addressed by it, so losing
    // it would mean the frontend could not ask for the case it is showing.
    var caseId = F.deal && F.deal.case_id;
    emptyInPlace(F);
    F.package_version = '17.0.0';
    F.mode = 'LIVE_EXTRACTION_ONLY';
    F.disclosure = 'Fixture rimossa. Ogni valore a schermo viene da un ingest.';
    if (F.deal) F.deal.case_id = caseId || 'PROJECT-KEYSTONE';
  }
  if (window.PANTA_CASE) emptyInPlace(window.PANTA_CASE);

  window.PantaLive = {
    stripped: true,
    absent: {},
    available: [],
    // Filled by engine.js once the projection arrives; read by render.js.
    setAbsent: function (map, available) {
      this.absent = map || {};
      this.available = available || [];
    },
    reasonFor: function (view) { return this.absent[view] || null; },
    panel: function (view) {
      var reason = this.reasonFor(view);
      if (!reason) return null;
      var clean = function (s) { return String(s).replace(/[&<>]/g, ''); };
      var links = this.available.length
        ? '<p style="margin-top:24px"><span class="eyebrow">CON DATI</span><br>' +
          this.available.map(function (v) {
            return '<button class="ghost" data-nav="' + clean(v) + '" ' +
                   'style="margin:6px 6px 0 0">' + clean(v) + '</button>';
          }).join('') + '</p>'
        : '';
      return (
        '<section class="page-head" style="padding:48px;max-width:720px">' +
        '<span class="eyebrow">NON PRODOTTO DALL\'ESTRAZIONE</span>' +
        '<h2 style="margin:12px 0">Questa schermata non ha dati</h2>' +
        '<p>' + clean(reason) + '</p>' +
        '<p style="opacity:.6;margin-top:20px">Non è un errore di caricamento: ' +
        'niente di ciò che è stato estratto alimenta questa vista, e riempirla ' +
        'con dati di esempio la renderebbe indistinguibile da una che funziona.</p>' +
        links +
        '</section>'
      );
    }
  };
})();
