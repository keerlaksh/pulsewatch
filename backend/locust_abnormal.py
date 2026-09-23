from locust import HttpUser, task, between


class AbnormalTrafficUser(HttpUser):

    wait_time = between(0.2, 0.5)

    @task(6)
    def slow_requests(self):
        self.client.get("/slow")

    @task(3)
    def error_requests(self):
        self.client.get("/error")

    @task(1)
    def normal_requests(self):
        self.client.get("/")