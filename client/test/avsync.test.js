'use strict';
/**
 * Tonwächter bei Framegen: alle paar echten Bilder avsync prüfen, bei
 * dauerhaftem Versatz einmal neu synchronisieren (Sprung an die Raum-Position).
 */
const test = require('node:test');
const assert = require('node:assert');
const { EventEmitter } = require('events');
const { Session } = require('../src/main/session');

function setup(avsync) {
  const relay = Object.assign(new EventEmitter(), { serverNow: () => Date.now(), send() {}, leave() {} });
  const framegen = new EventEmitter();
  const s = new Session({ relay, settings: { prefs: {} }, installer: {}, framegen, configDir: '/tmp', logDir: '/tmp' });
  clearInterval(s.syncTimer); clearInterval(s.statusTimer); clearInterval(s.uiTimer); clearInterval(s.avTimer);
  const calls = [];
  const mpv = {
    running: true,
    props: { pause: false, seeking: false, 'paused-for-cache': false, 'time-pos': 100, duration: 7000 },
    value: avsync,
    get: async (name) => { assert.strictEqual(name, 'avsync'); return mpv.value; },
    command: async (...args) => { calls.push(args); },
    osd: (text) => { calls.push(['osd', text]); },
  };
  s.mpv = mpv;
  s.fileReady = true;
  s.playback = { item: { id: 'film' }, playing: true, position: 100, updatedAt: Date.now() };
  s.planInfo = { framegen: { state: 'on', from: 24 } };
  return { s, mpv, calls };
}

async function ticks(s, n) {
  for (let i = 0; i < n; i++) {
    s.avLastCheck = 0; // Zeit überspringen: jeder Aufruf ist eine neue Prüfung
    s.avTick();
    await new Promise((r) => setImmediate(r));
  }
}

test('kleiner Versatz: nichts passiert', async () => {
  const { s, calls } = setup(0.03);
  await ticks(s, 20);
  assert.deepStrictEqual(calls, []);
});

test('dauerhafter Versatz: einmal neu synchronisieren', async () => {
  const { s, calls } = setup(-0.4);
  await ticks(s, 5);
  assert.strictEqual(calls.length, 0, 'erst nach mehreren Prüfungen');
  await ticks(s, 1);
  const seek = calls.find((c) => c[0] === 'seek');
  assert.ok(seek, 'springt an die Raum-Position');
  assert.ok(Math.abs(seek[1] - 100) < 0.5);
  assert.ok(calls.some((c) => c[0] === 'osd' && /neu synchronisiert \(400 ms\)/.test(c[1])));
  // gleich danach nicht nochmal (Filter lädt neu, höchstens alle 15 s)
  calls.length = 0;
  s.avQuietUntil = 0; s.pendingSeeks = 0;
  await ticks(s, 12);
  assert.ok(!calls.some((c) => c[0] === 'seek'));
});

test('kurzer Ausreißer zählt nicht', async () => {
  const { s, mpv, calls } = setup(0.5);
  await ticks(s, 3);
  mpv.value = 0.01;
  await ticks(s, 1);
  mpv.value = 0.5;
  await ticks(s, 5);
  assert.deepStrictEqual(calls, []);
});

test('ohne Framegen, pausiert oder kurz nach einem Sprung: keine Prüfung', async () => {
  for (const change of [
    (s) => { s.planInfo = { framegen: null }; },
    (s) => { s.mpv.props.pause = true; },
    (s) => { s.avQuietUntil = Date.now() + 60000; },
  ]) {
    const { s, calls } = setup(1);
    change(s);
    await ticks(s, 10);
    assert.deepStrictEqual(calls, []);
  }
});

test('wiederholt: Hinweis auf zu langsame Grafikkarte', async () => {
  const { s, calls } = setup(0.3);
  for (let i = 0; i < 3; i++) {
    s.avLastResync = 0; s.pendingSeeks = 0; s.avQuietUntil = 0;
    await ticks(s, 6);
  }
  assert.ok(calls.some((c) => c[0] === 'osd' && /kommt mit Framegen nicht hinterher/.test(c[1])));
});

test('Framegen an/aus: kein Weglassen von Bildern beim Springen, Bild und Ton starten gemeinsam neu', async () => {
  const { s, mpv, calls } = setup(0);
  const sets = [];
  mpv.set = async (name, value) => { sets.push([name, value]); mpv.props[name] = value; };
  mpv.props['video-params'] = { w: 1920, h: 1080 };
  mpv.props['container-fps'] = 23.976;
  s.lastPlanKey = '[]';
  s.settings.prefs = { framegen: { enabled: true } };
  s.installer.status = () => ({ framegen: true, models: ['v4_26'] });
  s.framegen = { plan: () => ({ vf: ['@wprife:vapoursynth=file=x'], info: { framegen: { state: 'on', from: 23.976, to: 143.86 }, notes: [] } }), building: null };
  s.updateButtons = () => {};
  await s.applyFilters();
  assert.ok(sets.some(([n, v]) => n === 'hr-seek-framedrop' && v === 'no'));
  const iVf = calls.findIndex((c) => c[0] === 'vf' && c[1] === 'set');
  const iSeek = calls.findIndex((c) => c[0] === 'seek');
  assert.ok(iVf >= 0 && iSeek > iVf, 'nach dem Filterwechsel an dieselbe Stelle springen');

  // wieder aus: Bilder dürfen wieder weggelassen werden, auch hier neu starten
  calls.length = 0;
  s.framegen.plan = () => ({ vf: [], info: { framegen: null, notes: [] } });
  await s.applyFilters();
  assert.ok(sets.some(([n, v]) => n === 'hr-seek-framedrop' && v === 'yes'));
  assert.ok(calls.some((c) => c[0] === 'seek'));

  // ohne Framegen ändert sich nur VSR: kein Sprung
  calls.length = 0;
  s.framegen.plan = () => ({ vf: ['@wpvsr:d3d11vpp=scaling-mode=nvidia'], info: { framegen: null, notes: [] } });
  await s.applyFilters();
  assert.ok(!calls.some((c) => c[0] === 'seek'));
});
