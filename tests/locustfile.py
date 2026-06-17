# Load test for the scan API
# Simulates multiple users triggering scans concurrently
# Usage: locust -f tests/locustfile.py --host https://app.bestfreeaifor.com
from locust import HttpUser, task, between


class CostDetectiveUser(HttpUser):
    """Simulates a user triggering cost analysis scans."""
    wait_time = between(5, 30)  # Users don't scan every second

    def on_start(self):
        """Login when the simulated user starts."""
        response = self.client.post("/api/auth/login", json={
            "email": "test@example.com",
            "password": "password123",
        })
        self.token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

    @task(3)
    def start_scan(self):
        """Trigger a cost analysis scan."""
        self.client.post(
            "/api/scans",
            headers=self.headers,
            json={"region": "us-east-1"},
        )

    @task(1)
    def get_scan_history(self):
        """Check scan history."""
        self.client.get("/api/scans", headers=self.headers)
