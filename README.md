Step 1 - API LAYER
The first step of PulseWatch was to build a FastAPI-based application with controlled API endpoints that could generate different types of traffic and application behavior.
These endpoints act as simulation points for the rest of the project. They allow us to generate normal requests, slow responses, errors, requests handled by different pods, and high CPU usage. This traffic is later used for monitoring, Kubernetes load balancing and autoscaling, and anomaly detection.
<img width="1312" height="1199" alt="ChatGPT Image Sep 24, 2026, 02_26_25 PM" src="https://github.com/user-attachments/assets/0e2937b9-381b-4129-a7d0-8828484a8e7b" />

Step 2 — Add Middleware & Request Tracking
After creating the API endpoints, the next step was to make the application observe what happens when those endpoints receive traffic.
We added FastAPI middleware that runs around every request. It records information such as:
<img width="1312" height="1199" alt="ChatGPT Image Sep 24, 2026, 02_36_48 PM" src="https://github.com/user-attachments/assets/c7b80c6a-a0ef-4ebb-948a-6187056713d8" />

Step 3 — Add PostgreSQL for Persistent Request Metrics
<img width="859" height="514" alt="image" src="https://github.com/user-attachments/assets/8bc46bda-801f-45d8-8fee-3fcbde407070" />

Step 4  — Python converts the database data into ML features
<img width="498" height="711" alt="image" src="https://github.com/user-attachments/assets/06b88b18-74b2-44b0-a630-999cc001ecb8" />

Step 5 -  Isolation Forest analyzes those observations
<img width="1312" height="1199" alt="ChatGPT Image Sep 24, 2026, 03_04_55 PM" src="https://github.com/user-attachments/assets/4b360b49-8ea0-4ff5-9514-ad662b0f46db" />

