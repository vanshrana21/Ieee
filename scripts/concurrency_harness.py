#!/usr/bin/env python3
"""
Windsurf Concurrency Test Harness

Executes parallel requests to test race conditions and concurrency safety.
Usage: python scripts/concurrency_harness.py --concurrency 50 --endpoint "/api/match/{id}/advance"
"""
import asyncio
import argparse
import json
import time
import sys
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from pathlib import Path

import aiohttp


@dataclass
class ConcurrencyResult:
    """Result from a single concurrent request."""
    request_id: int
    status_code: int
    response_time_ms: float
    success: bool
    error: Optional[str] = None
    response_body: Optional[Dict] = None


@dataclass
class ConcurrencyTestSummary:
    """Summary of concurrency test execution."""
    total_requests: int
    successful_requests: int
    failed_requests: int
    success_rate: float
    avg_response_time_ms: float
    min_response_time_ms: float
    max_response_time_ms: float
    status_code_distribution: Dict[int, int]
    errors: List[str]
    race_conditions_detected: bool
    timestamp: str


class ConcurrencyHarness:
    """Harness for executing concurrent API requests."""
    
    def __init__(self, base_url: str, token: Optional[str] = None):
        self.base_url = base_url.rstrip('/')
        self.token = token
        self.results: List[ConcurrencyResult] = []
    
    def _get_headers(self) -> Dict[str, str]:
        """Get request headers with auth if available."""
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'
        return headers
    
    async def _execute_request(
        self,
        session: aiohttp.ClientSession,
        request_id: int,
        endpoint: str,
        method: str = 'GET',
        payload: Optional[Dict] = None
    ) -> ConcurrencyResult:
        """Execute a single request and capture result."""
        start_time = time.time()
        
        try:
            url = f"{self.base_url}{endpoint}"
            
            async with session.request(
                method=method,
                url=url,
                headers=self._get_headers(),
                json=payload
            ) as response:
                response_time = (time.time() - start_time) * 1000
                
                try:
                    body = await response.json()
                except:
                    body = None
                
                # Success is 2xx or expected race condition codes (409, 423)
                success = response.status in [200, 201, 204, 409, 423]
                
                return ConcurrencyResult(
                    request_id=request_id,
                    status_code=response.status,
                    response_time_ms=response_time,
                    success=success,
                    error=None,
                    response_body=body
                )
                
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            return ConcurrencyResult(
                request_id=request_id,
                status_code=0,
                response_time_ms=response_time,
                success=False,
                error=str(e),
                response_body=None
            )
    
    async def run_concurrent_requests(
        self,
        endpoint: str,
        concurrency: int = 50,
        method: str = 'GET',
        payload: Optional[Dict] = None,
        delay_ms: float = 0
    ) -> ConcurrencyTestSummary:
        """Execute concurrent requests and return summary."""
        self.results = []
        
        async with aiohttp.ClientSession() as session:
            tasks = []
            for i in range(concurrency):
                task = self._execute_request(session, i, endpoint, method, payload)
                tasks.append(task)
                if delay_ms > 0:
                    await asyncio.sleep(delay_ms / 1000)
            
            self.results = await asyncio.gather(*tasks)
        
        return self._generate_summary()
    
    def _generate_summary(self) -> ConcurrencyTestSummary:
        """Generate summary from results."""
        total = len(self.results)
        successful = sum(1 for r in self.results if r.success)
        failed = total - successful
        
        response_times = [r.response_time_ms for r in self.results]
        
        # Status code distribution
        status_dist: Dict[int, int] = {}
        for r in self.results:
            status_dist[r.status_code] = status_dist.get(r.status_code, 0) + 1
        
        # Collect errors
        errors = [r.error for r in self.results if r.error]
        
        # Detect race conditions
        # Race conditions are detected if we see:
        # - Multiple successes where only one should succeed (e.g., advance)
        # - Database constraint violations
        race_detected = False
        if 200 in status_dist and status_dist[200] > 1:
            # Multiple 200s for operations that should be exclusive
            race_detected = True
        
        return ConcurrencyTestSummary(
            total_requests=total,
            successful_requests=successful,
            failed_requests=failed,
            success_rate=successful / total if total > 0 else 0,
            avg_response_time_ms=sum(response_times) / len(response_times) if response_times else 0,
            min_response_time_ms=min(response_times) if response_times else 0,
            max_response_time_ms=max(response_times) if response_times else 0,
            status_code_distribution=status_dist,
            errors=list(set(errors)),  # Unique errors
            race_conditions_detected=race_detected,
            timestamp=time.strftime('%Y-%m-%dT%H:%M:%SZ')
        )
    
    def save_results(self, output_dir: str, test_name: str):
        """Save results to JSON file."""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Save detailed results
        results_file = output_path / f"{test_name}_detailed.json"
        with open(results_file, 'w') as f:
            json.dump([asdict(r) for r in self.results], f, indent=2)
        
        # Save summary
        summary = self._generate_summary()
        summary_file = output_path / f"{test_name}_summary.json"
        with open(summary_file, 'w') as f:
            json.dump(asdict(summary), f, indent=2)
        
        return str(summary_file)


def main():
    parser = argparse.ArgumentParser(
        description='Windsurf Concurrency Test Harness'
    )
    parser.add_argument(
        '--concurrency', '-c',
        type=int,
        default=50,
        help='Number of concurrent requests (default: 50)'
    )
    parser.add_argument(
        '--endpoint', '-e',
        required=True,
        help='API endpoint to test'
    )
    parser.add_argument(
        '--method', '-m',
        default='GET',
        choices=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'],
        help='HTTP method (default: GET)'
    )
    parser.add_argument(
        '--payload', '-p',
        help='JSON payload for POST/PUT requests'
    )
    parser.add_argument(
        '--base-url', '-u',
        default='http://localhost:8000',
        help='Base URL for API (default: http://localhost:8000)'
    )
    parser.add_argument(
        '--token', '-t',
        help='Bearer token for authentication'
    )
    parser.add_argument(
        '--output-dir', '-o',
        default='./artifacts/concurrency',
        help='Output directory for results'
    )
    parser.add_argument(
        '--test-name',
        default='concurrency_test',
        help='Name for this test run'
    )
    parser.add_argument(
        '--delay-ms',
        type=float,
        default=0,
        help='Delay between starting requests (ms)'
    )
    
    args = parser.parse_args()
    
    # Parse payload if provided
    payload = None
    if args.payload:
        try:
            payload = json.loads(args.payload)
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON payload: {e}")
            sys.exit(1)
    
    # Create harness
    harness = ConcurrencyHarness(args.base_url, args.token)
    
    print(f"=== Windsurf Concurrency Test Harness ===")
    print(f"Endpoint: {args.endpoint}")
    print(f"Method: {args.method}")
    print(f"Concurrency: {args.concurrency}")
    print(f"Base URL: {args.base_url}")
    print("")
    
    # Run test
    print(f"Executing {args.concurrency} concurrent requests...")
    start_time = time.time()
    
    summary = asyncio.run(harness.run_concurrent_requests(
        endpoint=args.endpoint,
        concurrency=args.concurrency,
        method=args.method,
        payload=payload,
        delay_ms=args.delay_ms
    ))
    
    duration = time.time() - start_time
    
    print(f"\nCompleted in {duration:.2f}s")
    print("")
    
    # Display summary
    print("=== Results ===")
    print(f"Total requests: {summary.total_requests}")
    print(f"Successful: {summary.successful_requests}")
    print(f"Failed: {summary.failed_requests}")
    print(f"Success rate: {summary.success_rate:.1%}")
    print(f"Avg response time: {summary.avg_response_time_ms:.2f}ms")
    print(f"Min response time: {summary.min_response_time_ms:.2f}ms")
    print(f"Max response time: {summary.max_response_time_ms:.2f}ms")
    print("")
    print("Status code distribution:")
    for code, count in sorted(summary.status_code_distribution.items()):
        print(f"  {code}: {count}")
    
    if summary.race_conditions_detected:
        print("\n⚠️  RACE CONDITIONS DETECTED!")
    
    if summary.errors:
        print(f"\nErrors ({len(summary.errors)}):")
        for error in summary.errors[:5]:  # Show first 5
            print(f"  - {error}")
    
    # Save results
    results_path = harness.save_results(args.output_dir, args.test_name)
    print(f"\nResults saved: {results_path}")
    
    # Exit with error code if race conditions detected
    sys.exit(1 if summary.race_conditions_detected else 0)


if __name__ == "__main__":
    main()
