#!/usr/bin/env python3
"""
Quick test script to verify pagination and performance optimizations work correctly.

Usage:
    python test_pagination.py
"""

import requests
import time
from typing import Dict, Any

# Configuration
API_URL = "http://localhost:8000"
API_KEY = "your-api-key-here"  # Replace with actual API key

def test_paginated_endpoint():
    """Test the new paginated linked accounts endpoint"""
    print("\n" + "="*80)
    print("Testing Paginated Linked Accounts Endpoint")
    print("="*80)

    headers = {"X-API-KEY": API_KEY}

    # Test 1: First page
    print("\n1. Fetching first page (limit=50)...")
    start = time.time()
    response = requests.get(
        f"{API_URL}/v1/linked-accounts",
        headers=headers,
        params={"limit": 50}
    )
    elapsed = time.time() - start

    if response.status_code == 200:
        data = response.json()
        print(f"   ✅ Success! ({elapsed:.2f}s)")
        print(f"   - Records returned: {len(data.get('data', []))}")
        print(f"   - Has more: {data.get('has_more', False)}")
        print(f"   - Response size: {len(response.content) / 1024:.2f} KB")

        # Test 2: Second page with cursor
        if data.get('next_cursor'):
            print("\n2. Fetching second page with cursor...")
            start = time.time()
            response2 = requests.get(
                f"{API_URL}/v1/linked-accounts",
                headers=headers,
                params={"limit": 50, "cursor": data['next_cursor']}
            )
            elapsed = time.time() - start

            if response2.status_code == 200:
                data2 = response2.json()
                print(f"   ✅ Success! ({elapsed:.2f}s)")
                print(f"   - Records returned: {len(data2.get('data', []))}")
                print(f"   - Response size: {len(response2.content) / 1024:.2f} KB")
            else:
                print(f"   ❌ Failed: {response2.status_code} - {response2.text}")

        # Test 3: Filter by app_name
        if data.get('data') and len(data['data']) > 0:
            app_name = data['data'][0]['app_name']
            print(f"\n3. Testing filter by app_name='{app_name}'...")
            start = time.time()
            response3 = requests.get(
                f"{API_URL}/v1/linked-accounts",
                headers=headers,
                params={"limit": 10, "app_name": app_name}
            )
            elapsed = time.time() - start

            if response3.status_code == 200:
                data3 = response3.json()
                print(f"   ✅ Success! ({elapsed:.2f}s)")
                print(f"   - Records returned: {len(data3.get('data', []))}")
                all_match = all(acc['app_name'] == app_name for acc in data3['data'])
                print(f"   - All records match filter: {all_match}")
            else:
                print(f"   ❌ Failed: {response3.status_code} - {response3.text}")
    else:
        print(f"   ❌ Failed: {response.status_code} - {response.text}")


def test_performance_comparison():
    """Compare performance metrics"""
    print("\n" + "="*80)
    print("Performance Metrics Summary")
    print("="*80)

    headers = {"X-API-KEY": API_KEY}

    # Measure paginated endpoint
    print("\nMeasuring paginated endpoint (50 records)...")
    times = []
    for i in range(3):
        start = time.time()
        response = requests.get(
            f"{API_URL}/v1/linked-accounts",
            headers=headers,
            params={"limit": 50}
        )
        elapsed = time.time() - start
        times.append(elapsed)
        print(f"   Request {i+1}: {elapsed:.3f}s")

    avg_time = sum(times) / len(times)
    print(f"\n   Average response time: {avg_time:.3f}s")

    if response.status_code == 200:
        data = response.json()
        print(f"   Response size: {len(response.content) / 1024:.2f} KB")
        print(f"   Records per page: {len(data.get('data', []))}")


def check_compression():
    """Check if GZip compression is working"""
    print("\n" + "="*80)
    print("Checking GZip Compression")
    print("="*80)

    headers_with_compression = {
        "X-API-KEY": API_KEY,
        "Accept-Encoding": "gzip"
    }

    headers_without_compression = {
        "X-API-KEY": API_KEY,
        "Accept-Encoding": "identity"
    }

    print("\nFetching with compression...")
    response_compressed = requests.get(
        f"{API_URL}/v1/linked-accounts",
        headers=headers_with_compression,
        params={"limit": 50}
    )

    print("Fetching without compression...")
    response_uncompressed = requests.get(
        f"{API_URL}/v1/linked-accounts",
        headers=headers_without_compression,
        params={"limit": 50}
    )

    if response_compressed.status_code == 200 and response_uncompressed.status_code == 200:
        compressed_size = len(response_compressed.content) / 1024
        uncompressed_size = len(response_uncompressed.content) / 1024
        compression_ratio = (1 - compressed_size / uncompressed_size) * 100

        print(f"\n   Compressed size: {compressed_size:.2f} KB")
        print(f"   Uncompressed size: {uncompressed_size:.2f} KB")
        print(f"   Compression ratio: {compression_ratio:.1f}%")

        if compression_ratio > 50:
            print("   ✅ GZip compression is working well!")
        else:
            print("   ⚠️  Compression seems low. Check middleware configuration.")


if __name__ == "__main__":
    print("\n🚀 ACI Performance Test Suite")
    print("="*80)

    # Update API_KEY before running
    if API_KEY == "your-api-key-here":
        print("\n❌ ERROR: Please update API_KEY in the script before running!")
        print("   Edit test_pagination.py and set your actual API key.")
        exit(1)

    try:
        test_paginated_endpoint()
        test_performance_comparison()
        check_compression()

        print("\n" + "="*80)
        print("✅ All tests completed!")
        print("="*80)
        print("\nNext steps:")
        print("1. Run the database migration: docker compose exec runner alembic upgrade head")
        print("2. Test the frontend at: http://localhost:3000/linked-accounts")
        print("3. Monitor performance in production")
        print()

    except requests.exceptions.ConnectionError:
        print("\n❌ ERROR: Could not connect to API server")
        print("   Make sure the backend is running: docker compose up")
    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
