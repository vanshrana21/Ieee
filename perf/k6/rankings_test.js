import http from 'k6/http';
import { sleep, check, group } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';

/**
 * k6 Load Test: Rankings Endpoint
 * 
 * Tests the Phase 16 rankings API under load.
 * Target: 200 VUs, p95 latency < 200ms
 */

// Custom metrics
const errorRate = new Rate('errors');
const latencyTrend = new Trend('latency');
const successCounter = new Counter('successful_requests');

// Test configuration
export const options = {
  stages: [
    { duration: '1m', target: 50 },    // Ramp up to 50 VUs
    { duration: '2m', target: 200 }, // Ramp up to 200 VUs
    { duration: '5m', target: 200 },   // Stay at 200 VUs
    { duration: '1m', target: 0 },   // Ramp down
  ],
  thresholds: {
    http_req_duration: ['p(95)<200'],  // 95% of requests under 200ms
    http_req_failed: ['rate<0.01'],   // Error rate under 1%
    errors: ['rate<0.01'],
  },
};

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const API_TOKEN = __ENV.API_TOKEN || '';

function getHeaders() {
  const headers = {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
  };
  if (API_TOKEN) {
    headers['Authorization'] = `Bearer ${API_TOKEN}`;
  }
  return headers;
}

export default function () {
  group('Rankings API', () => {
    // Test speaker rankings endpoint
    const speakerResponse = http.get(
      `${BASE_URL}/api/analytics/rankings/speaker`,
      { headers: getHeaders() }
    );
    
    const speakerSuccess = check(speakerResponse, {
      'speaker rankings status is 200': (r) => r.status === 200,
      'speaker rankings response time < 200ms': (r) => r.timings.duration < 200,
    });
    
    errorRate.add(!speakerSuccess);
    latencyTrend.add(speakerResponse.timings.duration);
    if (speakerSuccess) successCounter.add(1);
    
    // Test team rankings endpoint
    const teamResponse = http.get(
      `${BASE_URL}/api/analytics/rankings/team`,
      { headers: getHeaders() }
    );
    
    const teamSuccess = check(teamResponse, {
      'team rankings status is 200': (r) => r.status === 200,
      'team rankings response time < 200ms': (r) => r.timings.duration < 200,
    });
    
    errorRate.add(!teamSuccess);
    latencyTrend.add(teamResponse.timings.duration);
    if (teamSuccess) successCounter.add(1);
  });
  
  sleep(0.2); // Think time between requests
}

export function handleSummary(data) {
  return {
    'artifacts/k6/rankings_summary.json': JSON.stringify(data, null, 2),
    stdout: textSummary(data, { indent: ' ', enableColors: true }),
  };
}

// Simple text summary function (k6 built-in)
function textSummary(data, options) {
  const indent = options.indent || '';
  const colors = options.enableColors ? {
    green: '\x1b[32m',
    red: '\x1b[31m',
    reset: '\x1b[0m',
  } : { green: '', red: '', reset: '' };
  
  let result = [];
  result.push(`${indent}=== k6 Load Test Summary ===\n`);
  result.push(`${indent}Checks: ${data.metrics.checks?.passes || 0}/${(data.metrics.checks?.passes || 0) + (data.metrics.checks?.fails || 0)}\n`);
  result.push(`${indent}HTTP Req Duration: avg=${data.metrics.http_req_duration?.avg?.toFixed(2) || 0}ms min=${data.metrics.http_req_duration?.min?.toFixed(2) || 0}ms med=${data.metrics.http_req_duration?.med?.toFixed(2) || 0}ms max=${data.metrics.http_req_duration?.max?.toFixed(2) || 0}ms p(95)=${data.metrics.http_req_duration?.['p(95)']?.toFixed(2) || 0}ms\n`);
  result.push(`${indent}HTTP Req Failed: ${((data.metrics.http_req_failed?.value || 0) * 100).toFixed(2)}%\n`);
  result.push(`${indent}Iterations: ${data.metrics.iterations?.count || 0}\n`);
  result.push(`${indent}${colors.green}✓ Test completed${colors.reset}\n`);
  
  return result.join('');
}
