#!/usr/bin/env python3
"""
Create 20 load test jobs based on workflow-fbugos-test-job
"""

import requests
import json
import sys
import re

# Configuration
API_BASE_URL = "https://api.devel.dareg.biodata.ceitec.cz/api/v1"
AUTH_URL = "https://api.devel.dareg.biodata.ceitec.cz/api/auth/login/"
USERNAME = "...."
PASSWORD = "...."

# Specific configuration as requested
WORKFLOW_TEMPLATE_ID = "34c002bd-d394-40fc-a5b0-0265abad427f"
DATASET_ID = "f918fae3-ca52-436c-947c-ab247cf17a44"
DATASET_CONTENT_TYPE = 15  # Dataset enum value (17 is Experiment!)

class LoadTestJobCreator:
    def __init__(self):
        self.token = None
        self.session = requests.Session()

    def authenticate(self):
        """Authenticate using session-based login"""
        try:
            # Get CSRF token
            print("Getting CSRF token...")
            login_page = self.session.get(AUTH_URL)
            csrf_match = re.search(r'csrfmiddlewaretoken.*?value="([^"]+)"', login_page.text)
            if not csrf_match:
                print("✗ Failed to get CSRF token")
                return False

            csrf_token = csrf_match.group(1)
            print(f"✓ Got CSRF token")

            # Login
            print(f"Logging in as {USERNAME}...")
            login_data = {
                'csrfmiddlewaretoken': csrf_token,
                'username': USERNAME,
                'password': PASSWORD,
                'next': '/api/v1/',
            }

            response = self.session.post(
                AUTH_URL,
                data=login_data,
                headers={
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'Referer': AUTH_URL
                },
                allow_redirects=True
            )

            # Check if login page has error message
            if 'Please enter a correct' in response.text or 'invalid' in response.text.lower():
                print(f"✗ Login failed - incorrect credentials")
                print(f"Response snippet: {response.text[:500]}")
                return False

            # Update CSRF token from cookies
            csrf_cookie = self.session.cookies.get('csrftoken')
            session_cookie = self.session.cookies.get('sessionid')

            print(f"Debug - Response status: {response.status_code}")
            print(f"Debug - CSRF cookie: {csrf_cookie}")
            print(f"Debug - Session cookie: {session_cookie}")
            print(f"Debug - All cookies: {list(self.session.cookies.keys())}")

            if csrf_cookie:
                self.session.headers.update({'X-CSRFToken': csrf_cookie})

            if session_cookie or csrf_cookie:
                print(f"✓ Successfully authenticated")
                return True
            else:
                print(f"✗ Authentication failed - no cookies")
                return False

        except requests.exceptions.RequestException as e:
            print(f"✗ Authentication failed: {e}")
            return False

    def find_job_by_name(self, job_name):
        """Find a job by name"""
        try:
            # Try with search parameter
            response = self.session.get(f"{API_BASE_URL}/jobs/?search={job_name}")
            response.raise_for_status()

            jobs_data = response.json()
            if isinstance(jobs_data, dict) and "results" in jobs_data:
                all_jobs = jobs_data["results"]
            else:
                all_jobs = jobs_data

            # Find exact match
            for job in all_jobs:
                if job.get("name") == job_name:
                    print(f"✓ Found job: {job['name']} (ID: {job['id']})")
                    return job

            print(f"✗ Job '{job_name}' not found")
            return None

        except requests.exceptions.RequestException as e:
            print(f"✗ Failed to find job: {e}")
            return None

    def create_job(self, app_config, job_number):
        """Create a new job with specified configuration"""

        # Create a unique app_config for this job with different metadata key
        job_app_config = app_config.copy()
        job_app_config["metadataKey"] = f"hash_value_{job_number}"

        new_job_data = {
            "workflow_template": WORKFLOW_TEMPLATE_ID,
            "root_resource_content_type": DATASET_CONTENT_TYPE,
            "root_resource_id": DATASET_ID,
            "output_resource_content_type": DATASET_CONTENT_TYPE,
            "output_resource_id": DATASET_ID,
            "name": f"load-v7-test-job-{job_number}",
            "description": f"Load v7 test job {job_number} - using dataset {DATASET_ID}",
            "app_config": job_app_config,
            "log_level": "info"
        }

        try:
            headers = {
                'Referer': f"{API_BASE_URL}/jobs/"
            }
            response = self.session.post(f"{API_BASE_URL}/jobs/", json=new_job_data, headers=headers)

            if response.status_code == 201:
                created_job = response.json()
                print(f"✓ Created job {job_number}: {created_job['name']} (ID: {created_job['id']})")
                return created_job
            else:
                print(f"✗ Failed to create job {job_number} (HTTP {response.status_code}): {response.text[:200]}")
                return None

        except requests.exceptions.RequestException as e:
            print(f"✗ Error creating job {job_number}: {e}")
            return None

def main():
    print("=" * 60)
    print("Creating 1000 Load Test v7 Jobs")
    print("=" * 60)

    creator = LoadTestJobCreator()

    # Authenticate
    if not creator.authenticate():
        print("\nAuthentication failed!")
        sys.exit(1)

    # Get app_config from existing job
    print("\nGetting app configuration from existing jobs...")
    response = creator.session.get(f"{API_BASE_URL}/jobs/")
    response.raise_for_status()
    jobs_data = response.json()
    all_jobs = jobs_data.get('results', [])

    if all_jobs:
        app_config = all_jobs[0].get('app_config', {"algorithm": "sha256", "metadataKey": "example"})
        print(f"Using app_config: {json.dumps(app_config, indent=2)}")
    else:
        app_config = {"algorithm": "sha256", "metadataKey": "example"}
        print(f"No jobs found, using default app_config")

    print(f"\nConfiguration:")
    print(f"  Workflow Template: {WORKFLOW_TEMPLATE_ID}")
    print(f"  Dataset ID: {DATASET_ID}")
    print(f"  Content Type: {DATASET_CONTENT_TYPE} (Dataset)")

    # Create 1000 jobs (641-1640)
    print(f"\nCreating 1000 jobs (641-1640)...")
    print("-" * 60)

    created_count = 0
    failed_count = 0

    for i in range(641, 1641):
        result = creator.create_job(app_config, i)
        if result:
            created_count += 1
        else:
            failed_count += 1

        # Print progress every 50 jobs
        if i % 50 == 0:
            print(f"Progress: {created_count}/{i-640} jobs created...")

    print("-" * 60)
    print(f"\n=== Summary ===")
    print(f"Successfully created: {created_count} jobs")
    print(f"Failed: {failed_count} jobs")
    print(f"\nAll jobs created with names: load-v7-test-job-641 through load-v7-test-job-1640")
    print(f"Dataset: {DATASET_ID} (fbugos-test-dataset)")
    print(f"Workflow: {WORKFLOW_TEMPLATE_ID}")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\nOperation cancelled by user")
        sys.exit(0)
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
