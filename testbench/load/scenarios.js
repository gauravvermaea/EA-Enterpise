// EA Explorer load test (D582), run by `eax testbench load` with k6 (https://k6.io). Read-mostly, as people use it:
// the start page, who am I, the models, the run's fixture model and its grid, search. Reads only: nothing is changed.
// Every request carries a test account's token (TOKENS, one per virtual user in turn). Settings come from the
// environment the test bench sets: TARGET, TOKENS (comma separated), MODEL, USERS, MINUTES, THRESHOLDS (JSON from
// testbench/thresholds.json), DATA (testbench/load/data.json), INSECURE.
import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { SharedArray } from 'k6/data';

const T = JSON.parse(__ENV.THRESHOLDS || '{}');
const TARGET = (__ENV.TARGET || '').replace(/\/$/, '');
const TOKENS = (__ENV.TOKENS || '').split(',').filter((t) => t);
const MODEL = __ENV.MODEL || '';
const USERS = parseInt(__ENV.USERS || '20', 10);
const MINUTES = parseFloat(__ENV.MINUTES || '2');
const DATA = new SharedArray('searches', () => JSON.parse(open(__ENV.DATA || './data.json')).searches);

export const options = {
  insecureSkipTLSVerify: __ENV.INSECURE === '1',
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(95)', 'p(99)'],
  scenarios: {
    people: {
      executor: 'ramping-vus',
      startVUs: 1,
      stages: [
        { duration: `${Math.max(1, Math.round(MINUTES * 60 * 0.2))}s`, target: USERS },
        { duration: `${Math.max(1, Math.round(MINUTES * 60 * 0.7))}s`, target: USERS },
        { duration: `${Math.max(1, Math.round(MINUTES * 60 * 0.1))}s`, target: 0 },
      ],
      gracefulRampDown: '20s',
    },
  },
  thresholds: {
    http_req_duration: [`med<${T.p50_ms || 400}`, `p(95)<${T.p95_ms || 1500}`, `p(99)<${T.p99_ms || 4000}`],
    http_req_failed: [`rate<${T.error_rate || 0.01}`],
  },
};

function headers() {
  const token = TOKENS.length ? TOKENS[(__VU - 1) % TOKENS.length] : '';
  return { headers: { Authorization: `Bearer ${token}`, Accept: 'application/json' }, timeout: '60s' };
}

export default function () {
  const h = headers();
  group('start page', () => {
    check(http.get(`${TARGET}/`, { timeout: '60s' }), { 'start page 200': (r) => r.status === 200 });
  });
  group('who am I', () => {
    check(http.get(`${TARGET}/api/v1/me`, h), { 'me 200': (r) => r.status === 200 });
  });
  group('models', () => {
    check(http.get(`${TARGET}/api/v1/models`, h), { 'models 200': (r) => r.status === 200 });
  });
  if (MODEL) {
    group('a model and its grid', () => {
      check(http.get(`${TARGET}/api/v1/models/${MODEL}`, h), { 'model 200': (r) => r.status === 200 });
      check(http.get(`${TARGET}/api/v1/models/${MODEL}/grids/relationships`, h), { 'grid 200': (r) => r.status === 200 });
    });
  }
  group('search', () => {
    const q = DATA[Math.floor(Math.random() * DATA.length)];
    check(http.get(`${TARGET}/api/v1/search?q=${encodeURIComponent(q)}`, h), { 'search 200': (r) => r.status === 200 });
  });
  sleep(1 + Math.random() * 2);
}
