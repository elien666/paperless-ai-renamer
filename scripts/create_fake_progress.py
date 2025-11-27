#!/usr/bin/env python3
"""
Helper script to create fake running progress jobs for screenshots.
This calls the development API endpoint to inject fake progress into the running application.
"""

import requests
import sys

def create_fake_progress(base_url="http://localhost:8000"):
    """Create fake running progress jobs via API."""
    url = f"{base_url}/api/dev/fake-progress"
    
    try:
        response = requests.post(url, timeout=5)
        response.raise_for_status()
        data = response.json()
        
        print("✓ Fake progress jobs created successfully!")
        print(f"  Process job: {data['jobs']['process']}")
        print(f"  Index job: {data['jobs']['index']}")
        print()
        print("You should now see running progress indicators in the UI.")
        return True
    except requests.exceptions.ConnectionError:
        print("✗ Error: Could not connect to the server.")
        print(f"  Make sure the application is running at {base_url}")
        return False
    except requests.exceptions.HTTPError as e:
        print(f"✗ Error: HTTP {e.response.status_code}")
        print(f"  {e.response.text}")
        return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

if __name__ == "__main__":
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
    success = create_fake_progress(base_url)
    sys.exit(0 if success else 1)

