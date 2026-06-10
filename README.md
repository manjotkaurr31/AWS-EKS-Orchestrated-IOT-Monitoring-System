# IOT Monitoring Platform on Amazon EKS

A cloud-native IOT Monitoring Platform built on Amazon EKS. The platform ingests telemetry from simulated factory devices, processes it asynchronously using Amazon SQS, persists historical records in PostgreSQL on Amazon RDS, and publishes threshold violations as custom metrics to Amazon CloudWatch - with SNS-driven email alerting.

---

## Overview

Factory environments generate continuous streams of sensor data, boiler temperatures, conveyor RPMs, storage humidity, that need to be captured reliably, processed without data loss, and surfaced as operational alerts when readings cross safety thresholds.

This platform addresses that problem with a decoupled, queue-based architecture. The ingestion layer accepts and acknowledges messages immediately, keeping response times low and isolating the HTTP surface from any downstream slowness. Workers consume from the queue at their own pace and handle persistence and alerting independently. A Dead Letter Queue catches any message that fails repeatedly, ensuring nothing is silently dropped.

The system demonstrates Kubernetes deployments on EKS, EKS Pod Identity for credential-free AWS access, queue-based asynchronous processing, Docker containerisation, and GitHub Actions CI/CD.

---

## Architecture

```
                      ┌────────────────────┐
                      │  Device Simulator  │
                      │     (Python)       │
                      └─────────┬──────────┘
                                │  POST /telemetry
                                ▼
                 ┌────────────────────────────┐
                 │   FastAPI Ingestion API    │
                 │  EKS Deployment (2 pods)   │
                 └──────────┬─────────────────┘
                            │  SQS SendMessage
                            ▼
               ┌───────────────────────────────┐
               │         Amazon SQS            │
               │   telemetry-queue + DLQ       │
               └──────────┬────────────────────┘
                          │  SQS ReceiveMessage
                          ▼
          ┌─────────────────────────────────────┐
          │        Telemetry Worker             │
          │      EKS Deployment (2 pods)        │
          └──────┬──────────────────┬───────────┘
                 │                  │
                 ▼                  ▼
  ┌──────────────────┐   ┌──────────────────────┐
  │  Amazon RDS      │   │  Amazon CloudWatch   │
  │  PostgreSQL      │   │  Custom Metrics      │
  └──────────────────┘   └──────────┬───────────┘
                                    │  SNS Alarm
                                    ▼
                          ┌──────────────────┐
                          │   Email Alert    │
                          │   (via SNS)      │
                          └──────────────────┘
```

### Ingestion Flow

1. The Python device simulator generates telemetry for 1,000 logical devices (boilers, conveyors, and storage units) and sends each reading to the FastAPI ingestion endpoint.
2. The API validates the payload and publishes it to the SQS main queue, returning `202 Accepted` immediately.
3. Worker pods poll the queue, persist each record to PostgreSQL, and evaluate readings against predefined thresholds.
4. Messages that fail processing after the maximum retry count are moved to the Dead Letter Queue.

### Alerting Flow

When a worker detects a threshold violation (e.g. boiler temperature exceeds threshold, conveyor RPM anomaly), it publishes a custom metric to CloudWatch. CloudWatch Alarms evaluate the metric and trigger SNS notifications, which deliver email alerts in real time.

---

## AWS Services Used

| Service | Purpose |
|---|---|
| **Amazon EKS** | Managed Kubernetes cluster running all application workloads |
| **Amazon ECR** | Private Docker image registry for `api` and `worker` images |
| **Amazon SQS** | Decouples ingestion from processing; main queue + Dead Letter Queue |
| **Amazon RDS (PostgreSQL)** | Persistent storage for all telemetry records |
| **Amazon CloudWatch** | Custom metrics and alarms for threshold violations |
| **Amazon SNS** | Fans out CloudWatch alarm notifications to email subscribers |
| **EKS Pod Identity** | Grants pods fine-grained AWS IAM permissions without static credentials |
| **Amazon EC2** | Worker nodes backing the EKS managed node group |
| **GitHub Actions** | CI/CD pipeline: build → ECR push → EKS rolling deploy |

---

## Repository Structure

```
telemetry/
├── .github/
│   └── workflows/
│       ├── api-deploy.yml          # CI/CD: build & deploy Ingestion API
│       └── worker-deploy.yml       # CI/CD: build & deploy Telemetry Worker
│
├── api/                            # FastAPI ingestion application
├── worker/                         # SQS consumer, RDS writer, CloudWatch publisher
├── k8s/                            # Kubernetes manifests
│
├── Dockerfile.api                  # API container definition
├── Dockerfile.worker               # Worker container definition
├── simulator.py                    # Factory device simulator (1000 devices)
├── requirements.txt
└── README.md
```

---

## Components

### Device Simulator

A Python script that generates telemetry for 1,000 simulated factory devices across three device types:

| Device Type | Metrics |
|---|---|
| `boiler` | `pressure`, `temperature` |
| `conveyor` | `rpm` |
| `storage` | `humidity`, `temperature` |

Each device posts its reading to the ingestion API. The simulator runs until all 1,000 messages are sent, then prints a completion summary:

```
Simulation complete.
Logical devices created: 1000
Messages sent: 1000
```

**Location:** `simulator.py`

---

### Ingestion API

A **FastAPI** application running as a Kubernetes Deployment (2 replicas) on EKS. It receives telemetry from the simulator, validates the payload, and publishes to SQS — returning `202 Accepted` without waiting for any downstream processing.

**Endpoint:**

| Method | Path | Description |
|---|---|---|
| `POST` | `/telemetry` | Accepts a telemetry reading and enqueues it to SQS |

The API uses **EKS Pod Identity** to call SQS — no access keys are embedded in the container or configuration.

**Location:** `api/`

---

### Telemetry Worker

A Python consumer running as a Kubernetes Deployment (2 replicas) on EKS. It long-polls the SQS queue and for each message:

1. Persists the telemetry record to **PostgreSQL** on RDS
2. Evaluates the reading against configured thresholds
3. Publishes a **CloudWatch custom metric** if the threshold is exceeded
4. Deletes the message from the queue on success

The worker also uses **EKS Pod Identity** for AWS access — separate from the API role, scoped to SQS receive/delete, RDS connectivity, and CloudWatch PutMetricData.

**PostgreSQL schema:**

```
          Table "public.telemetry"
   Column    |            Type             | Nullable
-------------+-----------------------------+----------
 id          | uuid                        | not null
 device_id   | character varying(100)      | not null
 device_type | character varying(100)      | not null
 recorded_at | timestamp with time zone    | not null
 payload     | jsonb                       | not null
 created_at  | timestamp with time zone    |
```

**Location:** `worker/`

---

## Kubernetes Resources

| Resource | Purpose |
|---|---|
| Namespace | Logical isolation for all platform workloads |
| Deployment (API) | Runs 2 replicas of the FastAPI ingestion service |
| Deployment (Worker) | Runs 2 replicas of the SQS consumer worker |
| Service | Internal cluster networking for the API |
| ConfigMap | Non-sensitive configuration (queue URLs, thresholds) |
| Secret | Sensitive configuration (RDS credentials) |
| ServiceAccount | Binds pods to IAM roles via EKS Pod Identity |

**EKS Pod Identity** is used instead of node-level IAM roles or static credentials. Each pod receives short-lived AWS credentials scoped to exactly the permissions it needs.

---

## CI/CD Pipeline

Every push to `main` triggers GitHub Actions workflows that build, push, and deploy both services automatically.

```
git push to main
       │
       ▼
GitHub Actions
       │
       ├── Build API Docker image
       ├── Push API image to ECR (:latest)
       ├── kubectl rollout → EKS (API Deployment)
       │
       ├── Build Worker Docker image
       ├── Push Worker image to ECR (:latest)
       └── kubectl rollout → EKS (Worker Deployment)
```

EKS credentials are injected via GitHub Actions secrets. Rolling deployments ensure zero downtime — new pods start and pass health checks before old pods are terminated.

---

## Key Learnings

**Queue-based decoupling** - Separating ingestion from processing means the API never slows down due to database latency or CloudWatch API hiccups. The queue absorbs burst traffic naturally; workers process at their own pace.

**Dead Letter Queue as a safety net** - Without a DLQ, a malformed or unprocessable message could block the queue indefinitely. Configuring a maxReceiveCount and routing failures to the DLQ means bad messages are isolated and inspectable without affecting throughput.

**EKS Pod Identity over node-level roles** - Attaching broad IAM permissions to the EC2 node role gives every pod on that node the same access. Pod Identity scopes credentials per workload: the API can only send to SQS; the worker can only receive, delete, write to RDS, and publish metrics.

**CloudWatch custom metrics for operational alerting** - Pushing application-level signals (threshold violations) as custom metrics allows CloudWatch Alarms to trigger SNS notifications without any additional monitoring infrastructure. The full loop - device reading → processed → alert in inbox - runs end to end.

**Kubernetes Deployments for self-healing** - If a worker pod crashes, Kubernetes restarts it automatically. The SQS message visibility timeout ensures the unprocessed message becomes visible again and is picked up by another pod - no manual intervention, no data loss.

**jsonb in PostgreSQL for flexible payloads** - Different device types produce different metric shapes. Storing the payload as `jsonb` avoids schema migrations when new device types are added, while still allowing indexed queries on payload fields.

---

## Future Improvements

- **KEDA autoscaling** - Scale worker replica count automatically based on SQS queue depth, so the system handles burst ingestion without over-provisioning idle pods.
- **AWS Load Balancer Controller** - Expose the ingestion API through an Application Load Balancer with TLS termination, replacing internal cluster networking only.
- **Grafana dashboards** - Visualise telemetry trends and threshold violations with time-series dashboards sourced from CloudWatch or a Prometheus scrape target.
- **End-to-end integration tests in CI** - Add a pipeline stage that runs the simulator against a staging environment and asserts that records land in RDS and metrics appear in CloudWatch before deploying to production.
- **Helm charts** - Package the Kubernetes manifests into a Helm chart to make environment-specific configuration (staging vs production queue URLs, replica counts, thresholds) clean and repeatable.
- **Infrastructure as Code** - Replace manual AWS console setup with Terraform covering VPC, EKS cluster and node group, RDS, SQS, SNS, ECR, and IAM roles.

---

Lastly, take a look at `Demonstration.md` to see the platform running end to end!
