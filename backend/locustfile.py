from locust import HttpUser, task, between


class PulseWatchUser(HttpUser):

    wait_time = between(1, 3)

    @task(8)
    def home(self):
        self.client.get("/")

    @task(2)
    def health(self):
        self.client.get("/health")