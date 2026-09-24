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

STEP 6 - DOCKER IMAGE

<img width="1312" height="1199" alt="ChatGPT Image Sep 24, 2026, 03_31_44 PM" src="https://github.com/user-attachments/assets/973d1c21-7042-4c75-a077-fc7a732a327c" />



After developing the FastAPI application, middleware, PostgreSQL integration, and anomaly-detection logic, the next step was to package the application into a Docker image.

PulseWatch uses **two separate container images**:

1. **Custom PulseWatch image** — contains FastAPI, middleware, ML code, dependencies, and frontend.
2. **Official PostgreSQL image** — contains the PostgreSQL database server.

PostgreSQL is **not packaged inside the PulseWatch image**.

## 4.1 What Is Inside the PulseWatch Docker Image?

```text
PulseWatch Docker Image
│
├── Python 3.11
├── FastAPI
├── Uvicorn
├── Application code
│   ├── API endpoints
│   ├── Middleware
│   ├── Database connection code
│   └── Anomaly detection code
│
├── ML dependencies
│   ├── NumPy
│   ├── Pandas
│   └── Scikit-learn
│
├── PostgreSQL Python driver
│   └── psycopg2
│
└── Frontend
    └── index.html
```

The following are **not** inside this image:

```text
PostgreSQL database server ❌
PostgreSQL database data ❌
request_metrics table data ❌
```

PostgreSQL runs separately using the official `postgres:16` image.

## 4.2 Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY backend/requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .

COPY frontend/index.html /app/index.html

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

## 4.3 Dockerfile — Line-by-Line Explanation

| Dockerfile instruction                                               | What it does                                                                                                                       |
| -------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| `FROM python:3.11-slim`                                              | Uses a lightweight Linux image that already contains Python 3.11 as the base environment.                                          |
| `WORKDIR /app`                                                       | Creates/sets `/app` as the working directory inside the image.                                                                     |
| `COPY backend/requirements.txt .`                                    | Copies the project's Python dependency file into `/app/requirements.txt`.                                                          |
| `RUN pip install --no-cache-dir -r requirements.txt`                 | Installs the required Python libraries such as FastAPI, Uvicorn, psycopg2, NumPy, Pandas, Scikit-learn, and the Kubernetes client. |
| `COPY backend/ .`                                                    | Copies the backend application code into `/app`, including the FastAPI application, middleware, database code, and ML logic.       |
| `COPY frontend/index.html /app/index.html`                           | Copies the dashboard HTML into `/app` so FastAPI can serve the frontend.                                                           |
| `EXPOSE 8000`                                                        | Documents that the application inside the container listens on port `8000`; it does not publish the port by itself.                |
| `CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]` | Starts the FastAPI application using Uvicorn when the container starts.                                                            |

## 4.4 Building the Docker Image

From the project root, the image was built using:

```powershell
docker build -f .\backend\Dockerfile -t keerlaksh/pulsewatch:latest .
```

The build process is:

```text
Project files
     │
     │ docker build
     ▼
Read Dockerfile
     │
     ▼
Start with Python 3.11
     │
     ▼
Create /app
     │
     ▼
Copy requirements.txt
     │
     ▼
Install dependencies
     │
     ▼
Copy backend code
     │
     ▼
Copy frontend
     │
     ▼
Define startup command
     │
     ▼
PulseWatch Docker Image
```

The resulting image is:

```text
keerlaksh/pulsewatch:latest
```

## 4.5 Image vs Container

An **image** is the packaged blueprint of the application.

A **container** is a running instance of that image.

```text
PulseWatch Image
       │
       │ run
       ▼
PulseWatch Container
```

Therefore:

> **Image = packaged application blueprint**
> **Container = running instance of that image**

## 4.6 Pushing the Image to Docker Hub

After building the image, it was pushed to Docker Hub:

```powershell
docker push keerlaksh/pulsewatch:latest
```

The flow is:

```text
Dockerfile
    │
    │ docker build
    ▼
Local Docker Image
    │
    │ docker push
    ▼
Docker Hub
    │
    ▼
keerlaksh/pulsewatch:latest
```

Docker Hub acts as the **image registry** from which Kubernetes can later pull the PulseWatch image.

## 4.7 PostgreSQL Runs Separately

PostgreSQL uses the official image:

```text
postgres:16
```

We do not build this image ourselves.

The overall architecture contains two images:

```text
┌─────────────────────────────────┐
│       PulseWatch Image          │
│                                 │
│ keerlaksh/pulsewatch:latest     │
│                                 │
│ FastAPI                         │
│ Middleware                      │
│ ML / Isolation Forest           │
│ Python dependencies             │
│ Frontend                        │
│ psycopg2                        │
└───────────────┬─────────────────┘
                │
                │ SQL connection
                ▼
┌─────────────────────────────────┐
│       PostgreSQL Image          │
│                                 │
│ postgres:16                     │
│                                 │
│ PostgreSQL database server      │
└─────────────────────────────────┘
```

When Kubernetes runs them, they become separate running containers/Pods.

## 4.8 How Request Data Gets Into PostgreSQL

The application does **not** copy PostgreSQL data into the Docker image.

Instead, the running FastAPI container communicates with the running PostgreSQL container over the network.

When a request arrives:

```text
Client
  │
  ▼
FastAPI
  │
  ▼
Middleware
  │
  ├── endpoint
  ├── status code
  ├── latency
  ├── pod name
  └── timestamp
```

The middleware uses `psycopg2` to connect to PostgreSQL and executes an SQL `INSERT`:

```sql
INSERT INTO request_metrics
(endpoint, status_code, latency, pod_name)
VALUES (...);
```

PostgreSQL then stores the information in the `request_metrics` table.

Therefore:

```text
HTTP Request
     │
     ▼
FastAPI Middleware
     │
     │ collects metrics
     ▼
psycopg2
     │
     │ SQL INSERT
     ▼
PostgreSQL Container
     │
     ▼
request_metrics table
```

## 4.9 How the ML Part Gets the PostgreSQL Data

The ML code does not have the database data permanently packaged inside the Docker image.

When anomaly detection runs, the application retrieves the stored metrics from PostgreSQL:

```text
PostgreSQL
     │
     │ SQL SELECT
     ▼
FastAPI / Python
     │
     ▼
Feature preparation
     │
     ▼
Isolation Forest
     │
     ▼
Normal / Anomaly
```

Therefore:

> **PostgreSQL is the data source, while Python/Scikit-learn performs the anomaly detection.**

## 4.10 Complete PulseWatch Docker + Database Flow

```text
                       DOCKER HUB
                    /              \
                   /                \
                  ▼                  ▼
     keerlaksh/pulsewatch:latest   postgres:16
                  │                  │
                  ▼                  ▼
        FastAPI Container     PostgreSQL Container
                  │                  │
        ┌─────────┴───────┐          │
        │                 │          │
        ▼                 ▼          │
    API endpoints     ML code       │
        │                 │          │
        ▼                 │          │
    Middleware            │          │
        │                 │          │
        │    SQL INSERT   │          │
        └─────────────────┼─────────►│
                          │          │
                          │     request_metrics
                          │          │
                          │◄─────────┘
                          │
                    SQL SELECT
                          │
                          ▼
                   Isolation Forest
                          │
                          ▼
                     Anomaly result
                          │
                          ▼
                      Dashboard
```

## 4.11 Important Distinction

### 1. PulseWatch Docker Image

```text
keerlaksh/pulsewatch:latest
```

Contains:

> **FastAPI + middleware + ML + dependencies + frontend**

### 2. PostgreSQL Image

```text
postgres:16
```

Contains:

> **PostgreSQL database software**

### 3. Database Data

```text
request_metrics
```

Contains:

> **The actual request information collected by the middleware**

The data is **not baked into the PulseWatch image**. It is inserted into PostgreSQL while the application is running.

## 4.12 Final Architecture

```text
              ┌──────────────────────────┐
              │   PulseWatch Image       │
              │                          │
              │ FastAPI                  │
              │ Middleware               │
              │ ML / Isolation Forest    │
              │ Python dependencies      │
              │ Frontend                 │
              └────────────┬─────────────┘
                           │
                    Running container
                           │
                  SQL INSERT / SELECT
                           │
                           ▼
              ┌──────────────────────────┐
              │   PostgreSQL Container   │
              │                          │
              │ postgres:16              │
              │                          │
              │ request_metrics          │
              └──────────────────────────┘
                           │
                           │ stored metrics
                           ▼
                    ML reads metrics
                           │
                           ▼
                   Isolation Forest
                           │
                           ▼
                     Anomaly result
```

