"""Reproducible OFFLINE acceptance entrypoint. Synthetic timing is not production evidence."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from download_manager import download_unique


def synthetic_download_benchmark(count=24, delay=0.01):
    urls = ['synthetic://' + str(i) for i in range(count)]
    results = {}
    for workers in (1, 6):
        calls = []
        def downloader(url, target):
            time.sleep(delay)
            Path(target).write_bytes(url.encode())
            calls.append(url)
        with tempfile.TemporaryDirectory() as folder:
            start = time.perf_counter()
            rows = download_unique(urls + urls, folder, downloader, workers=workers)
            elapsed = (time.perf_counter() - start) * 1000
            assert len(calls) == count and len(rows) == count
            results[str(workers)] = {'elapsed_ms': elapsed, 'network_calls': len(calls), 'unique_urls': len(rows)}
    return {'kind': 'SYNTHETIC', 'scope': 'injected sleep downloader only; not v1/v2 product quality or actual token evidence', 'results': results}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    env = dict(os.environ, PYTHONPATH=str(root / 'scripts'))
    checks = []
    for command in ([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v'], [sys.executable, '-m', 'compileall', '-q', 'scripts', 'tests']):
        result = subprocess.run(command, cwd=root, env=env, capture_output=True, text=True)
        checks.append({'command': command, 'exit_code': result.returncode, 'output': result.stdout + result.stderr})
    report = {'schema': 'offline-acceptance/v2', 'offline_passed': all(c['exit_code'] == 0 for c in checks), 'checks': checks, 'synthetic_performance': synthetic_download_benchmark(), 'overall_phase_acceptance': 'BLOCKED_EXTERNAL', 'blockers': ['20-30 representative real products with frozen v1 measurements and human labels unavailable', 'real GLM/Kimi usage, OCR parity and shadow false-negative/false-positive measurements unavailable', 'independent service-account deployment and administrator isolation review unavailable', 'production write success and readback deliberately not exercised']}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'checks'}, ensure_ascii=False, indent=2))
    return 0 if report['offline_passed'] else 1

if __name__ == '__main__':
    raise SystemExit(main())
